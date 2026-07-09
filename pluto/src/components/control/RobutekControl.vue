<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PetIcon from '../PetIcon.vue'
import CopyButton from '../ui/UiCopyButton.vue'
import ControlKeyboard from './ControlKeyboard.vue'
import QuadrantLayout from '../QuadrantLayout.vue'
import UiButton from '../ui/UiButton.vue'
import UiIconButton from '../ui/UiIconButton.vue'
import type { NodeMap } from '../../composables/useNodes'

interface Point { x: number; y: number }

interface Device {
  name: string | null
  model: string | null
  firmware: string | null
  activity: string
  status_label: string
  status_human?: string   // friendly label from the API (single source; see dreame_session.py)
  status_int: number | null
  battery: number | null
  online: boolean
}

interface Session {
  session_id: string
  date: string
  start_ts: number | null
  cleaning_min: number | null
  area_m2: number | null
  completed: boolean
  kind: string | null          // 'mop' (clean) | 'sweep' (sheared first pass) | null
  pet: boolean
  file_name: string
  route: Point[]
  origin_mm: [number, number] | null
  charger_mm: [number, number] | null
  grid_size_mm: number | null
  map_id: number | null
}

interface DreameData {
  authenticated?: boolean
  device: Device | null
  history: Session[]
  updated: string | null
  error?: string | null
}

// Demoted to the 'dreame' source-child of Control: source/target/mapping are owned
// by the parent rail and arrive as props (URL-driven). This component just reads
// them and drives the playback.
const props = defineProps<{
  name: string; active: boolean; nodes?: NodeMap
  source: string; target: string; mapping: string
  targetDev?: string   // when target === 'pi': which pico's UART dev to route to (ttyAMA4/ttyAMA0)
}>()
// Drive errors are OWNED by the Control parent (shown in the shared control bar),
// not here -- this child just reports them up. '' clears.
const emit = defineEmits<{ 'drive-error': [string] }>()

const API = `http://${window.location.hostname}:7700`
const router = useRouter()
const driveTarget  = computed<'none' | 'keyboard' | 'pi'>(() => (props.target || 'none') as 'none' | 'keyboard' | 'pi')
const driveMapping = computed(() => props.mapping || '')

// The dreame source depends on its .env: without it, dreame isn't offered in the
// Control source dropdown. If you still land on /control/dreame -- the case that
// confused things on every Vite hot reload -- bounce up to the /control parent so it
// auto-picks a usable source. This guard lives in the dreame child (where the .env
// dependency is), not the parent. Gated on the roster being loaded so the initial
// fetch doesn't fire a false redirect.
watch(() => props.nodes, (nodes) => {
  if (!nodes || Object.keys(nodes).length === 0) return   // roster not loaded yet
  const d = nodes['dreame']
  if (!d || d.status === 'unconfigured') router.replace('/control')
}, { immediate: true })

const data      = ref<DreameData | null>(null)
const loading   = ref(false)
const fetchedAt = ref('')

const dev       = computed(() => data.value?.device ?? null)
const status    = computed(() => dev.value?.online ? 'on' : 'off')
const connected = computed(() => !!dev.value)
const history   = computed(() => data.value?.history ?? [])

// ── filter: hide the sheared sweep pass by default ────────────────
const showSweep = ref(false)
const visible = computed(() =>
  showSweep.value ? history.value : history.value.filter(s => s.kind !== 'sweep'))
const sweepCount = computed(() => history.value.filter(s => s.kind === 'sweep').length)

const selIdx = ref(0)
watch(visible, () => { selIdx.value = 0 }, { flush: 'sync' })
const sel = computed<Session | null>(() => visible.value[selIdx.value] ?? null)

const collapsed = ref(false)   // table collapse-to-left

// ── status labels ─────────────────────────────────────────────────
// Defensive fallback only: the API now sends `status_human` (single source in
// dreame_session.py, shared with the @l40 chat status). Used if that's absent.
const STATUS_HUMAN: Record<string, string> = {
  SWEEPING: 'Sweeping', IDLE: 'Idle', PAUSED: 'Paused', ERROR: 'Error',
  RETURNING: 'Returning', CHARGING: 'Charging', MOPPING: 'Mopping',
  DRYING: 'Drying', WASHING: 'Washing', RETURNING_WASHING: 'Returning to wash',
  BUILDING_MAP: 'Building map', SWEEPING_AND_MOPPING: 'Sweep + mop',
  CHARGING_COMPLETED: 'Charged', UPGRADING: 'Updating', UNKNOWN: 'Unknown',
}
function humanStatus(label: string | undefined): string {
  if (!label) return '–'
  return STATUS_HUMAN[label] ??
    label.replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase())
}
const actClass = computed(() => {
  switch (dev.value?.activity) {
    case 'cleaning':  return 'is-clean'
    case 'returning': return 'is-return'
    case 'error':     return 'is-error'
    default:          return 'is-idle'
  }
})
const batColor = computed(() => {
  const p = dev.value?.battery ?? null
  if (p === null) return 'var(--text-muted)'
  return p > 50 ? 'var(--ok)' : p > 20 ? 'var(--warn)' : 'var(--bad)'
})

// ── playback clock (drives map, and later video + Pi) ─────────────
const currentTime = ref(0)        // seconds into the clean
const playing     = ref(false)
const speed       = ref(4)   // default 4x: below this the character looks too slow/boring; duty scales with speed so 4x stays coherent
const SPEEDS      = [1, 2, 4, 8, 16, 32]
// Speed as +/- buttons, NOT a <select>: on macOS a native select changes value on
// arrow keys and preventDefault can't stop it, so the synthetic stick keys walk it
// mid-drive (you couldn't set speed without pausing). Buttons ignore arrow keys.
const speedIdx    = computed(() => { const i = SPEEDS.indexOf(speed.value); return i < 0 ? 0 : i })
function stepSpeed(d: number) { speed.value = SPEEDS[Math.min(SPEEDS.length - 1, Math.max(0, speedIdx.value + d))] }
const duration    = computed(() => Math.max(1, (sel.value?.cleaning_min ?? 0) * 60))
const progress    = computed(() => Math.min(1, currentTime.value / duration.value))

let raf = 0
let lastTs = 0
function frame(ts: number) {
  if (!playing.value) return
  if (lastTs) {
    currentTime.value = Math.min(duration.value, currentTime.value + ((ts - lastTs) / 1000) * speed.value)
    if (currentTime.value >= duration.value) { playing.value = false; lastTs = 0; syncVideo(); return }
  }
  lastTs = ts
  syncVideo()
  raf = requestAnimationFrame(frame)
}
function play() {
  if (!sel.value?.route?.length) return
  if (progress.value >= 1) currentTime.value = 0
  playing.value = true; lastTs = 0; raf = requestAnimationFrame(frame)
  startDrive()
  syncVideo()
}
function pause() { playing.value = false; cancelAnimationFrame(raf); stopDriveOutput(); syncVideo() }
function togglePlay() { playing.value ? pause() : play() }

// Keyboard control of playback. Space = play/pause, so you don't have to mouse to
// the button (and fight for browser focus) while the synthetic keys are flying.
// While driving we also swallow the arrow keys at the window level so they can't
// scroll the page; the emulator still gets them via its background input.
function onPlaybackKey(e: KeyboardEvent) {
  if (!props.active) return
  const tag = (e.target as HTMLElement | null)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return   // don't hijack form typing
  if (e.code === 'Space') {
    e.preventDefault(); e.stopPropagation(); togglePlay(); return
  }
  // Start (and every other button) now lives on the on-screen keyboard's full mapping,
  // so there's no custom Enter hotkey here anymore. Arrow keys still get swallowed while
  // driving so they can't scroll the page.
  if (driveTarget.value !== 'none' && e.key.indexOf('Arrow') === 0) e.preventDefault()
}
onMounted(() => {
  window.addEventListener('keydown', onPlaybackKey, true)
  window.addEventListener('pagehide', stopBeacon)
})
function seek(e: Event) { pause(); currentTime.value = Number((e.target as HTMLInputElement).value); syncVideo() }
watch(sel, () => { pause(); currentTime.value = 0; svgScale.value = 1; emit('drive-error', ''); clearVideo() })
onBeforeUnmount(() => {
  cancelAnimationFrame(raf); stopDriveOutput(); clearVideo()
  window.removeEventListener('keydown', onPlaybackKey, true)
  window.removeEventListener('pagehide', stopBeacon)
})

// ── output drive: push the playback clock to the selected target ──────────────
// Backend-paced: each play/seek/speed/target change (re)starts a paced replay at
// the current clock offset, so the emulator/console stays in step with the map.
async function drivePost(payload: Record<string, unknown>) {
  // Route to the picked pico when driving the Pi: tag the batch with its dev (the API
  // forwards it onto the ops; the hub frames to bridges[dev]). No-op for non-pi payloads.
  const body = (payload.target === 'pi' && props.targetDev) ? { ...payload, dev: props.targetDev } : payload
  try {
    const r = await fetch(`${API}/control/drive`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const j = await r.json().catch(() => null)
    emit('drive-error', j && j.ok === false ? (j.error || 'drive error') : '')
  } catch {
    emit('drive-error', 'API unreachable')
  }
}
// Heartbeat while driving so the API knows we're still here. If it stops (tab
// closed/crashed before a 'pause' lands), the API's watchdog stops the drive and
// releases the keys -- otherwise the route keeps replaying and the character runs
// away. Fires while the page is visible (the side-by-side recording setup), which
// is exactly when it matters.
let keepaliveTimer = 0
function startKeepalive() {
  if (keepaliveTimer) return
  keepaliveTimer = window.setInterval(() => {
    if (driveTarget.value === 'none') return
    fetch(`${API}/control/drive`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'keepalive' }),
    }).catch(() => {})
  }, 2000)
}
function stopKeepalive() { if (keepaliveTimer) { clearInterval(keepaliveTimer); keepaliveTimer = 0 } }
function startDrive() {
  if (driveTarget.value === 'none' || !sel.value?.route?.length) return
  drivePost({ action: 'play', target: driveTarget.value, source: props.source, mapping: driveMapping.value, t: currentTime.value, speed: speed.value, session: sel.value })
  startKeepalive()
}
function stopDriveOutput() {
  stopKeepalive()
  if (driveTarget.value !== 'none') drivePost({ action: 'pause' })
}
// Best-effort stop when the tab/window goes away (close, refresh, navigate): a
// normal fetch can be cancelled mid-flight, so use sendBeacon to make sure the
// backend drive releases its keys instead of leaving the character walking.
function stopBeacon() {
  if (driveTarget.value === 'none') return
  try {
    navigator.sendBeacon(`${API}/control/drive`,
      new Blob([JSON.stringify({ action: 'pause' })], { type: 'application/json' }))
  } catch { /* tab is going away; best effort only */ }
}
watch(speed, () => { if (playing.value) startDrive() })
// target/mapping come from the parent rail (props); re-drive when they change.
watch(driveTarget, (t) => {
  emit('drive-error', '')
  if (t === 'none') { stopDriveOutput(); return }
  if (playing.value) startDrive()
})
watch(driveMapping, () => { if (playing.value && driveTarget.value !== 'none') startDrive() })
watch(() => props.active, (a) => { if (!a) pause() })

// ── route geometry + zoom ─────────────────────────────────────────
const svgScale = ref(1)
const svgCx = ref(0)
const svgCy = ref(0)
// The route's x-axis arrives mirrored vs the real room (left/right flipped), so the
// map was drawing the house backwards. Flip x through one isolated constant — applied
// to the path, bounds, charger, paw and head — so the map matches reality (and the
// un-mirrored video). The game (Sonic) needs no flip: its level isn't the room.
const MIRROR_X = -1

const baseBox = computed(() => {
  const s = sel.value
  if (!s?.route?.length) return null
  const pts = s.route
  const xs = pts.map(p => MIRROR_X * p.x), ys = pts.map(p => p.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const pad = Math.max(maxX - minX, maxY - minY) * 0.07
  const cx = s.charger_mm ? MIRROR_X * s.charger_mm[0] : null, cy = s.charger_mm?.[1] ?? null
  const bx0 = (cx !== null ? Math.min(minX, cx) : minX) - pad
  const by0 = (cy !== null ? Math.min(minY, cy) : minY) - pad
  const bx1 = (cx !== null ? Math.max(maxX, cx) : maxX) + pad
  const by1 = (cy !== null ? Math.max(maxY, cy) : maxY) + pad
  return { fullVB: [bx0, by0, bx1 - bx0, by1 - by0] as [number, number, number, number], cx, cy }
})
const viewBox = computed(() => {
  if (!baseBox.value) return '0 0 1 1'
  const [bx, by, bw, bh] = baseBox.value.fullVB
  if (svgScale.value <= 1) return `${bx} ${by} ${bw} ${bh}`
  const w = bw / svgScale.value, h = bh / svgScale.value
  return `${svgCx.value - w / 2} ${svgCy.value - h / 2} ${w} ${h}`
})
function onWheel(e: WheelEvent) {
  if (!baseBox.value) return
  e.preventDefault()
  const svg = e.currentTarget as SVGSVGElement
  const pt = svg.createSVGPoint()
  pt.x = e.clientX; pt.y = e.clientY
  const sp = pt.matrixTransform(svg.getScreenCTM()!.inverse())
  const factor = e.deltaY < 0 ? 1.18 : 1 / 1.18
  const ns = Math.max(1, Math.min(20, svgScale.value * factor))
  if (ns === svgScale.value) return
  const [bx, by, bw, bh] = baseBox.value.fullVB
  const curCx = svgScale.value <= 1 ? bx + bw / 2 : svgCx.value
  const curCy = svgScale.value <= 1 ? by + bh / 2 : svgCy.value
  svgScale.value = ns
  svgCx.value = sp.x + (curCx - sp.x) / factor
  svgCy.value = sp.y + (curCy - sp.y) / factor
}
function resetZoom() { svgScale.value = 1 }

// Pet "encounter" pin. The data is a per-clean boolean (no coords), so we mark one
// representative encounter at the route MIDPOINT -- a real path point, ~halfway --
// matching where the backend fires the A press. petPin.t uses the capture layer's
// linear time (i/(n-1) * duration); the paw appears as the replay reaches it.
const petPin = computed(() => {
  const r = sel.value?.route
  if (!sel.value?.pet || !r || !r.length) return null
  const mid = Math.floor(r.length / 2)
  const t = r.length > 1 ? (mid / (r.length - 1)) * duration.value : 0
  return { x: MIRROR_X * r[mid].x, y: r[mid].y, t }
})
const pawScale = computed(() => {
  const b = baseBox.value?.fullVB
  // ~5% of the VISIBLE map; dividing by svgScale keeps the marker a constant
  // on-screen size instead of ballooning as you zoom in. (glyph viewBox is 24u)
  return b ? (Math.max(b[2], b[3]) * 0.05) / (24 * svgScale.value) : 1
})

// ── click-drag pan (only once zoomed past the fit view) ───────────
const isPanning = ref(false)
let panSX = 0, panSY = 0, panCx0 = 0, panCy0 = 0
function onPanStart(e: PointerEvent) {
  if (svgScale.value <= 1 || !baseBox.value) return
  isPanning.value = true
  panSX = e.clientX; panSY = e.clientY
  panCx0 = svgCx.value; panCy0 = svgCy.value
  ;(e.currentTarget as Element).setPointerCapture(e.pointerId)
}
function onPanMove(e: PointerEvent) {
  if (!isPanning.value || !baseBox.value) return
  const rect = (e.currentTarget as Element).getBoundingClientRect()
  const [, , bw, bh] = baseBox.value.fullVB
  const w = bw / svgScale.value, h = bh / svgScale.value
  svgCx.value = panCx0 - (e.clientX - panSX) * (w / rect.width)
  svgCy.value = panCy0 - (e.clientY - panSY) * (h / rect.height)
}
function onPanEnd(e: PointerEvent) {
  if (!isPanning.value) return
  isPanning.value = false
  try { (e.currentTarget as Element).releasePointerCapture(e.pointerId) } catch { /* already released */ }
}

// progressive: the route drawn up to the clock
const drawnPoints = computed(() => {
  const r = sel.value?.route ?? []
  if (!r.length) return ''
  const n = Math.max(1, Math.floor(progress.value * r.length))
  return r.slice(0, n).map(p => `${MIRROR_X * p.x},${p.y}`).join(' ')
})
const head = computed<Point | null>(() => {
  const r = sel.value?.route ?? []
  if (!r.length) return null
  const n = Math.min(r.length - 1, Math.max(0, Math.floor(progress.value * r.length) - 1))
  const p = r[n]
  return p ? { x: MIRROR_X * p.x, y: p.y } : null
})

// ── layers / consumers ────────────────────────────────────────────
const videoOffset  = ref(0)       // s; the robot clip plays at currentTime + offset

// 3rd-person clip of the REAL robot, loaded from a local file (object-URL, no
// backend). Played on the same playback clock as the map + game, so one screen
// capture shows real robot -> abstract map -> typewriter game, all in step.
const videoUrl  = ref<string | null>(null)
const videoEl   = ref<HTMLVideoElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const hasVideo  = computed(() => !!videoUrl.value)
function pickVideo() { fileInput.value?.click() }
function onPickVideo(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (!f) return
  if (videoUrl.value) URL.revokeObjectURL(videoUrl.value)
  videoUrl.value = URL.createObjectURL(f)
}
function clearVideo() {
  if (videoUrl.value) URL.revokeObjectURL(videoUrl.value)
  videoUrl.value = null
}
// Keep the clip aligned: same rate as the map, seeked to currentTime+offset,
// played/paused together. Only reseat on real drift (>0.34s) so playback stays
// smooth instead of stuttering every frame.
function syncVideo() {
  const v = videoEl.value
  if (!v) return
  // Lock the clip's FULL length to the map's duration so they start AND end
  // together. The Dreame's reported cleaning_min rarely equals the clip's real
  // length, so without this they drift apart ("footage runs ahead"). `ratio`
  // gently time-stretches the clip to fit (imperceptible on a vacuum); it's ~1
  // when the lengths already match, so it does nothing in that case.
  const ratio = (Number.isFinite(v.duration) && v.duration > 0 && duration.value > 0)
    ? v.duration / duration.value : 1
  v.playbackRate = Math.min(speed.value * ratio, 16)   // browsers cap fast playback ~16x
  // If the offset puts the clip before its first frame (negative) or past its last,
  // it's "not started yet / already over" relative to the map -> HOLD it paused at
  // the nearest frame. Without this, a negative offset seeks back to 0 while it
  // plays forward, every frame -> the jumpy loop.
  let inRange = true
  if (Number.isFinite(v.duration)) {
    const raw = videoOffset.value + currentTime.value * ratio
    inRange = raw >= 0 && raw <= v.duration
    const t = Math.max(0, Math.min(raw, v.duration))
    if (Math.abs(v.currentTime - t) > 0.34) v.currentTime = t
  }
  if (playing.value && inRange) { if (v.paused) v.play().catch(() => {}) }
  else if (!v.paused) v.pause()
}
watch([speed, videoOffset], syncVideo)

// ── formatters ────────────────────────────────────────────────────
function fmt(min: number | null): string {
  if (min === null) return '–'
  return min < 60 ? `${min} min` : `${Math.floor(min / 60)}h ${(min % 60).toString().padStart(2, '0')}m`
}
function fmtArea(m2: number | null): string { return m2 !== null ? `${m2} m²` : '–' }
function fmtDate(d: string): string {
  const m = d.match(/(\d{4})-(\d{2})-(\d{2})\s+(\d{2}:\d{2})/)
  if (!m) return d
  const mo = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  return `${mo[+m[2]-1]} ${+m[3]} · ${m[4]}`
}
function fmtClock(sec: number): string {
  const m = Math.floor(sec / 60), s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

// ── cache-first load: history/map render without a session ────────
async function load(sync = false) {
  loading.value = true
  try {
    // ?sync=1 (the refresh button) re-pulls history live via the logged-in client
    // and refreshes the cache; a plain load reads the cache (fast tab switches).
    const r = await fetch(`${API}/dreame${sync ? '?sync=1' : ''}`)
    if (r.ok) {
      data.value = await r.json()
    } else {
      data.value = data.value ?? { device: null, history: [], updated: null, error: `HTTP ${r.status}` }
    }
    fetchedAt.value = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
  } catch {
    data.value = data.value ?? { device: null, history: [], updated: null, error: 'could not reach Pluto API' }
  } finally {
    loading.value = false
  }
}
watch(() => props.active, on => { if (on) load() }, { immediate: true })

// ── login: only when explicitly connecting, never a tab gate ──────
const showLogin   = ref(false)
const region      = ref('us')
const email       = ref('')
const password    = ref('')
const submitting  = ref(false)
const loginError  = ref('')
function openLogin() { loginError.value = ''; showLogin.value = true }
async function signIn() {
  if (submitting.value) return
  submitting.value = true; loginError.value = ''
  try {
    const r = await fetch(`${API}/dreame/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ region: region.value, username: email.value, password: password.value }),
    })
    const b = await r.json().catch(() => ({}))
    if (!r.ok || !b.authenticated) { loginError.value = b.error || `sign-in failed (HTTP ${r.status})`; return }
    password.value = ''; showLogin.value = false; await load()
  } catch {
    loginError.value = 'could not reach the Pluto API'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="rb">
    <QuadrantLayout>

    <!-- ── header: live tile (cache-first; needs session) + actions ── -->
    <template #header>
    <header class="rb-bar">
      <div class="rb-id">
        <span class="rb-dot" :class="status" :title="dev?.online ? 'online' : 'offline'"/>
        <span class="rb-id-name">{{ dev?.name ?? name ?? 'Robutek' }}</span>
        <span v-if="dev?.model" class="rb-id-model mono">{{ dev.model }}</span>
      </div>

      <div class="rb-status">
        <template v-if="connected && dev">
          <span class="rb-pill" :class="actClass">{{ dev.status_human ?? humanStatus(dev.status_label) }}</span>
          <span v-if="dev.battery !== null" class="rb-bat">
            <span class="rb-bat-shell"><span class="rb-bat-fill" :style="{ width: dev.battery + '%', background: batColor }" /></span>
            <span class="mono" :style="{ color: batColor }">{{ dev.battery }}%</span>
          </span>
        </template>
        <span v-else class="rb-offline"><span class="rb-offline-dot" />offline</span>
      </div>

      <div class="rb-bar-right">
        <span v-if="fetchedAt && !loading" class="rb-fetched mono">{{ fetchedAt }}</span>
        <button class="rb-ghost" :class="{ accent: !connected }" :disabled="loading"
          @click="connected ? load(true) : openLogin()">
          {{ loading ? 'Refreshing…' : connected ? 'Refresh' : 'Sign in' }}
        </button>
      </div>
    </header>
    </template>

    <!-- ── NW: Past Cleans list (slides) + route map ── -->
    <template #nw>
    <div class="rb-nw">

      <!-- collapsible session table -->
      <aside class="rb-table" :class="{ collapsed }">
        <div class="rb-table-head">
          <span class="rb-table-title">Past Cleans</span>
          <label v-if="sweepCount" class="rb-toggle">
            <input type="checkbox" v-model="showSweep" /><span>Show sweeps</span>
          </label>
        </div>
        <div class="rb-rows">
          <button
            v-for="(s, i) in visible" :key="s.session_id"
            class="rb-row" :class="{ on: i === selIdx }"
            @click="selIdx = i"
          >
            <span class="rb-row-main">
              <span class="rb-row-date">{{ fmtDate(s.date) }}</span>
              <span class="rb-row-meta mono">{{ fmt(s.cleaning_min) }} · {{ fmtArea(s.area_m2) }}</span>
              <span class="rb-row-id-line">
                <span class="rb-row-id mono" :title="s.session_id">{{ s.session_id }}</span>
                <CopyButton :text="s.session_id" :title="'copy session id\n' + s.session_id" />
              </span>
            </span>
            <span class="rb-row-tags">
              <span v-if="s.kind === 'sweep'" class="rb-tag sweep" title="sweep pass (map may be skewed)">sweep</span>
              <PetIcon v-if="s.pet" class="rb-pet" title="pet detected during this clean" />
            </span>
          </button>
          <div v-if="!visible.length" class="rb-empty">
            {{ history.length ? 'no cleans match the filter' : loading ? 'loading…' : 'no cleans cached' }}
          </div>
        </div>
      </aside>

      <!-- collapse toggle: rides the table edge, stays on-screen when collapsed -->
      <button class="rb-collapse" :style="{ left: collapsed ? '8px' : '268px' }"
        @click="collapsed = !collapsed" :title="collapsed ? 'expand list' : 'collapse list'">
        {{ collapsed ? '›' : '‹' }}
      </button>

      <!-- route map -->
      <div class="rb-map">
          <!-- the pet "encounter" is now a placed paw pin inside the route SVG
               (below), appearing as playback reaches the representative midpoint -->

          <template v-if="!sel">
            <div class="rb-map-empty">Select a clean to replay its route</div>
          </template>
          <template v-else-if="!baseBox">
            <div class="rb-map-empty">
              <div class="rb-map-empty-t">{{ fmtDate(sel.date) }}</div>
              <div class="rb-map-empty-s">No route recorded for this clean</div>
            </div>
          </template>
          <template v-else>
            <svg
              class="rb-svg"
              :viewBox="viewBox"
              preserveAspectRatio="xMidYMid meet"
              :style="{ cursor: svgScale > 1 ? (isPanning ? 'grabbing' : 'grab') : 'default' }"
              @wheel="onWheel"
              @pointerdown="onPanStart"
              @pointermove="onPanMove"
              @pointerup="onPanEnd"
              @pointercancel="onPanEnd"
            >
              <!-- full route preview ONLY before playback starts (progress 0), as a
                   "here's the session" overview. Once you play OR seek forward it's
                   progressive (drawn-so-far only) -- so a demo never reveals the whole
                   house when you scrub. (Was v-if=!playing, which leaked the full path
                   on every manual pause/seek.) -->
              <polyline
                v-if="progress === 0"
                :points="sel.route.map(p => (MIRROR_X * p.x) + ',' + p.y).join(' ')"
                fill="none" stroke="#9aa1ad" stroke-width="1.5"
                vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"
              />
              <!-- drawn-so-far (accent) -->
              <polyline
                :points="drawnPoints"
                fill="none" stroke="var(--accent)" stroke-width="2.5"
                vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"
              />
              <!-- charger -->
              <g v-if="baseBox.cx !== null && baseBox.cy !== null">
                <line :x1="baseBox.cx - 1" :y1="baseBox.cy ?? 0" :x2="baseBox.cx + 1" :y2="baseBox.cy ?? 0"
                  stroke="var(--text-muted)" stroke-width="6" vector-effect="non-scaling-stroke" />
                <line :x1="baseBox.cx" :y1="(baseBox.cy ?? 0) - 1" :x2="baseBox.cx" :y2="(baseBox.cy ?? 0) + 1"
                  stroke="var(--text-muted)" stroke-width="6" vector-effect="non-scaling-stroke" />
              </g>
              <!-- pet "encounter": a placed paw at the representative route midpoint,
                   persistent so it's visible the moment a pet clean is selected; the
                   drive still fires its A press when the replay reaches that point -->
              <g v-if="petPin" class="rb-map-paw"
                 :transform="`translate(${petPin.x},${petPin.y}) scale(${pawScale})`">
                <circle r="14" class="rb-paw-bg" vector-effect="non-scaling-stroke" />
                <g transform="translate(-12,-12.4)">
                  <ellipse cx="12" cy="16.5" rx="5.2" ry="4.3" />
                  <ellipse cx="5.6" cy="11" rx="2.1" ry="2.7" />
                  <ellipse cx="18.4" cy="11" rx="2.1" ry="2.7" />
                  <ellipse cx="9.4" cy="6.8" rx="2" ry="2.6" />
                  <ellipse cx="14.6" cy="6.8" rx="2" ry="2.6" />
                </g>
              </g>
              <!-- robot head -->
              <circle v-if="head" :cx="head.x" :cy="head.y" r="9" fill="var(--accent)" vector-effect="non-scaling-stroke" />
            </svg>

            <div class="rb-map-tools">
              <button v-if="svgScale > 1" class="rb-chip" @click="resetZoom">Reset zoom</button>
            </div>
          </template>
        </div>
    </div>
    </template>

    <!-- ── NE: 3rd-person robot clip, only when a clip is loaded ── -->
    <template #ne v-if="hasVideo">
      <div class="rb-video">
        <video ref="videoEl" :src="videoUrl || undefined" muted playsinline preload="auto"
               @loadedmetadata="syncVideo"></video>
        <button class="rb-video-x" @click="clearVideo" title="Remove clip" aria-label="Remove clip">×</button>
        <p class="rb-video-note"><strong>Actual footage:</strong> The game moves at the map's speed, which is constant because the robot stores the route but not the pace.</p>
      </div>
    </template>

    <!-- ── SE: controller (as usual) ── -->
    <template #se>
      <ControlKeyboard :active="active" :map-source="source" :target="target" :mapping="mapping"
                       :target-dev="targetDev" heading="Manual Assistance"
                       @drive-error="emit('drive-error', $event)" />
    </template>

    <!-- ── footer: transport / playback bar ── -->
    <template #footer>
    <footer class="rb-transport" :class="{ disabled: !sel?.route?.length }">
      <button class="rb-play" :disabled="!sel?.route?.length" @click="togglePlay" :title="playing ? 'Pause (Space)' : 'Play (Space)'">
        {{ playing ? '❚❚' : '▶' }}
      </button>
      <span class="rb-time mono">{{ fmtClock(currentTime) }} / {{ fmtClock(duration) }}</span>
      <input class="rb-scrub" type="range" min="0" :max="duration" step="1" :value="currentTime" @input="seek" :disabled="!sel?.route?.length" />
      <div class="rb-speed" title="Playback speed">
        <UiIconButton variant="bordered" @click="stepSpeed(-1)" :disabled="speedIdx <= 0" title="Slower" aria-label="Slower">−</UiIconButton>
        <span class="rb-speed-val mono">{{ speed }}×</span>
        <UiIconButton variant="bordered" @click="stepSpeed(1)" :disabled="speedIdx >= SPEEDS.length - 1" title="Faster" aria-label="Faster">+</UiIconButton>
      </div>

      <!-- Output + Mapping + any drive error live in the Control rail now. -->
      <span class="rb-tx-sep" />
      <input ref="fileInput" type="file" accept="video/*" class="rb-file" @change="onPickVideo" />
      <button v-if="!hasVideo" class="rb-tx-btn" @click="pickVideo" :disabled="!sel?.route?.length"
              title="Load a 3rd-person clip of the real robot, synced to playback">+ Robot Clip</button>
      <label v-else class="rb-tx-ctl" title="Nudge the clip's alignment vs the route (seconds)">
        <span>Clip</span>
        <input type="number" v-model.number="videoOffset" step="0.1" /><span class="mono">s</span>
      </label>
    </footer>
    </template>
    </QuadrantLayout>

    <!-- ── login (compact, only when connecting) — overlay, outside the layout ── -->
    <div v-if="showLogin" class="rb-login-scrim" @click.self="showLogin = false">
      <form class="rb-login" @submit.prevent="signIn" autocomplete="on">
        <div class="rb-login-title">Connect to DreameHome</div>
        <label class="rb-field"><span>Region</span>
          <select v-model="region" autocomplete="off" :disabled="submitting">
            <option value="us">United States</option><option value="eu">Europe</option>
            <option value="cn">China</option><option value="ru">Russia</option><option value="sg">Asia / Pacific</option>
          </select>
        </label>
        <label class="rb-field"><span>Email</span>
          <input v-model="email" name="username" type="email" autocomplete="username" placeholder="you@example.com" :disabled="submitting" required />
        </label>
        <label class="rb-field"><span>Password</span>
          <input v-model="password" name="password" type="password" autocomplete="current-password" placeholder="••••••••" :disabled="submitting" required />
        </label>
        <UiButton variant="primary" class="rb-primary" type="submit" :loading="submitting" loading-text="Signing in…" :disabled="!email || !password">Sign in</UiButton>
        <p v-if="loginError" class="rb-login-err">{{ loginError }}</p>
      </form>
    </div>
  </div>
</template>

<style scoped>
/* QuadrantLayout owns the header/grid/footer column now; .rb is just the positioning
   context that fills the stage and anchors the login overlay. */
.rb {
  position: relative; height: 100%;
  font-family: var(--font-sans); color: var(--text); background: var(--surface-2);
}
.mono { font-family: var(--font-mono); }

/* ── top bar ── */
.rb-bar {
  display: flex; align-items: center; gap: var(--sp-4);
  padding: var(--sp-3) var(--sp-4); background: var(--surface);
  border-bottom: 1px solid var(--line);
}
.rb-back {
  display: inline-flex; align-items: center; gap: 5px;
  font: inherit; font-size: 13px; font-weight: 600;
  padding: 5px 11px 5px 8px; margin: 0;
  border: 1px solid var(--line-strong); border-radius: var(--r-sm);
  background: var(--surface); color: var(--text-muted); cursor: pointer;
  transition: color 0.15s, background 0.15s, border-color 0.15s;
}
.rb-back:hover { color: var(--accent); border-color: var(--accent); background: var(--accent-soft); }
.rb-back:focus { outline: none; }
.rb-back:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.rb-back-sep { width: 1px; align-self: stretch; margin: 4px 0; background: var(--line); }
.rb-id { display: flex; align-items: baseline; gap: var(--sp-2); }
.rb-id-name { font-weight: 600; font-size: 15px; }
.rb-id-model { font-size: 11px; color: var(--text-muted); }
.rb-status { display: flex; align-items: center; gap: var(--sp-3); }
.rb-pill {
  font-size: 12px; font-weight: 600; padding: 3px 9px; border-radius: 999px;
  background: var(--surface-3); color: var(--text-muted);
}
.rb-pill.is-clean  { background: var(--accent-soft); color: var(--accent-hover); }
.rb-pill.is-return { background: #fef3c7; color: #92580a; }
.rb-pill.is-error  { background: #fee2e2; color: #b91c1c; }
.rb-bat { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.rb-bat-shell { width: 34px; height: 8px; border-radius: 999px; background: var(--surface-3); overflow: hidden; }
.rb-bat-fill { display: block; height: 100%; border-radius: 999px; }
.rb-dot { width: 8px; height: 8px; border-radius: 50%; }
.rb-dot.on { background: var(--ok); } .rb-dot.off { background: var(--text-faint); }
.rb-offline {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 500; color: var(--text-muted);
  padding: 3px 10px; border-radius: 999px; background: var(--surface-3);
}
.rb-offline-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); }
.rb-link { font: inherit; font-size: 13px; font-weight: 600; color: var(--accent); background: none; border: 0; cursor: pointer; padding: 0; }
.rb-bar-right { margin-left: auto; display: flex; align-items: center; gap: var(--sp-3); }
.rb-fetched { font-size: 11px; color: var(--text-faint); }
.rb-ghost {
  font: inherit; font-size: 13px; font-weight: 500; padding: 6px 12px;
  border: 1px solid var(--line-strong); border-radius: var(--r-sm);
  background: var(--surface); color: var(--text); cursor: pointer;
}
.rb-ghost:hover:not(:disabled) { background: var(--surface-2); }
.rb-ghost:disabled { opacity: 0.5; cursor: default; }
.rb-ghost.accent { border-color: var(--accent); color: var(--accent); }
.rb-ghost.accent:hover:not(:disabled) { background: var(--accent-soft); }

/* ── login scrim ── */
.rb-login-scrim {
  position: fixed; inset: 0; z-index: 1000; display: flex; align-items: center; justify-content: center;
  background: rgba(16,24,40,0.38);
}
.rb-login {
  width: 340px; display: flex; flex-direction: column; gap: var(--sp-3);
  padding: var(--sp-5); background: var(--surface);
  border-radius: var(--r-lg); box-shadow: var(--shadow-md);
}
.rb-login-title { font-weight: 600; font-size: 16px; }
.rb-field { display: flex; flex-direction: column; gap: 5px; font-size: 12px; font-weight: 500; color: var(--text-muted); }
.rb-field input, .rb-field select {
  font: inherit; font-size: 14px; font-weight: 400; color: var(--text);
  padding: 9px 11px; border: 1px solid var(--line-strong); border-radius: var(--r-sm); background: var(--surface);
}
.rb-field input:focus, .rb-field select:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
/* layout only — terracotta look, hover, disabled + the loading spinner come from UiButton */
.rb-primary { margin-top: 4px; }
.rb-login-err { font-size: 13px; color: var(--bad); margin: 0; }

/* ── NW: the sliding session list + the map, side by side (fills the quad) ── */
.rb-nw { position: relative; display: flex; width: 100%; height: 100%; min-width: 0; min-height: 0; }

/* table */
.rb-table {
  position: relative; width: 280px; flex-shrink: 0; display: flex; flex-direction: column;
  background: var(--surface); border-right: 1px solid var(--line);
  overflow: hidden; transition: width 0.18s ease;
}
.rb-table.collapsed { border-right: 0; }
.rb-table.collapsed { width: 0; }
.rb-table-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: var(--sp-3) var(--sp-4); border-bottom: 1px solid var(--line);
}
.rb-table-title { font-size: 11px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-muted); }
.rb-toggle { display: flex; align-items: center; gap: 5px; font-size: 12px; color: var(--text-muted); cursor: pointer; }
.rb-rows { flex: 1; overflow-y: auto; }
.rb-row {
  width: 100%; display: flex; align-items: center; justify-content: space-between; gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-4); border: 0; border-bottom: 1px solid var(--line);
  background: none; cursor: pointer; text-align: left; font: inherit;
}
.rb-row:hover { background: var(--surface-2); }
.rb-row.on { background: var(--accent-soft); box-shadow: inset 3px 0 0 var(--accent); }
.rb-row-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.rb-row-date { font-size: 13px; font-weight: 500; }
.rb-row-meta { font-size: 11px; color: var(--text-muted); }
.rb-row-tags { display: flex; align-items: center; gap: 5px; }
.rb-tag { font-size: 10px; font-weight: 600; padding: 1px 6px; border-radius: 999px; background: var(--surface-3); color: var(--text-muted); }
.rb-tag.sweep { background: #fef3c7; color: #92580a; }
.rb-pet { font-size: 14px; color: var(--accent); flex-shrink: 0; }
.rb-map-paw { fill: var(--accent); pointer-events: none; animation: rb-paw-in 0.25s ease-out; }
.rb-paw-bg { fill: var(--surface); stroke: var(--accent); stroke-width: 2; }
@keyframes rb-paw-in { from { opacity: 0; } to { opacity: 1; } }
.rb-row-id-line { display: flex; align-items: center; gap: 2px; min-width: 0; }
.rb-row-id { flex: 0 1 auto; min-width: 0; font-size: 10px; color: var(--text-faint); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rb-empty { padding: var(--sp-5) var(--sp-4); font-size: 13px; color: var(--text-muted); text-align: center; }
.rb-collapse {
  position: absolute; top: 12px; z-index: 5; width: 24px; height: 24px;
  display: grid; place-items: center; border: 1px solid var(--line); border-radius: 50%;
  background: var(--surface); color: var(--text-muted); cursor: pointer; box-shadow: var(--shadow-sm);
  font-size: 14px; transition: left 0.18s ease;
}
.rb-collapse:hover { color: var(--accent); border-color: var(--accent); }

/* map */
.rb-map { flex: 1; position: relative; display: grid; place-items: center; min-width: 0; min-height: 0; background: var(--surface); }
.rb-svg { width: 100%; height: 100%; }
.rb-map-empty { display: flex; flex-direction: column; gap: 4px; align-items: center; color: var(--text-muted); font-size: 14px; }
.rb-map-empty-t { font-weight: 600; color: var(--text); }
.rb-map-empty-s { font-size: 12px; }
.rb-map-tools { position: absolute; top: var(--sp-3); right: var(--sp-3); display: flex; gap: var(--sp-2); }
.rb-chip {
  display: flex; align-items: center; gap: 5px; font-size: 12px; color: var(--text-muted);
  padding: 4px 9px; border: 1px solid var(--line); border-radius: 999px; background: var(--surface); cursor: pointer;
}
.rb-chip.off { opacity: 0.7; }
/* NE: the robot clip fills its quad (only mounted when a clip is loaded) */
.rb-video { position: relative; height: 100%; min-height: 0; display: flex; flex-direction: column; gap: var(--sp-2); background: #000; padding: var(--sp-3); }
.rb-video video { flex: 1; min-height: 0; width: 100%; object-fit: contain; display: block; }
.rb-video-note {
  flex-shrink: 0; margin: 0; padding-top: var(--sp-2);
  border-top: 1px solid rgba(255, 255, 255, 0.12);   /* set apart from the footage */
  font-size: 11px; line-height: 1.45; text-align: left;
  color: rgba(255, 255, 255, 0.65);                  /* muted but legible, not hidden */
}
.rb-video-note strong { color: rgba(255, 255, 255, 0.9); font-weight: 600; }
.rb-video-x {
  position: absolute; top: var(--sp-2); right: var(--sp-2);
  width: 24px; height: 24px; display: grid; place-items: center;
  border: 0; border-radius: 50%; cursor: pointer; font-size: 15px; line-height: 1;
  color: #fff; background: rgba(0, 0, 0, 0.5);
}
.rb-video-x:hover { background: rgba(0, 0, 0, 0.8); }
.rb-file { display: none; }
.rb-tx-btn {
  font: inherit; font-size: 12px; color: var(--text); padding: 4px 8px; cursor: pointer;
  border: 1px solid var(--line-strong); border-radius: var(--r-sm); background: var(--surface);
}
.rb-tx-btn:hover:not(:disabled) { border-color: var(--accent); }
.rb-tx-btn:disabled { opacity: 0.5; cursor: default; }
.rb-tx-gear {
  display: grid; place-items: center; padding: 4px; cursor: pointer; flex-shrink: 0;
  border: 0; background: transparent; color: var(--text-muted); border-radius: var(--r-sm);
}
.rb-tx-gear.on { color: var(--text); }
.rb-tx-gear:hover { color: var(--accent); }
.rb-speed { display: flex; align-items: center; gap: 3px; flex-shrink: 0; }
.rb-speed-val { font-size: 12px; min-width: 30px; text-align: center; color: var(--text); }
/* the speed steppers are now UiIconButton bordered */

/* ── transport ── */
.rb-transport {
  display: flex; align-items: center; gap: var(--sp-3); flex-wrap: wrap; row-gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-4); background: var(--surface); border-top: 1px solid var(--line);
}
/* keep the scrubber greedy so it claims row 1 and pushes the drive/clip controls
   onto a second row when Pluto is docked narrow beside the emulator */
.rb-scrub { flex: 1 1 160px; }
.rb-transport.disabled { opacity: 0.55; }
.rb-play {
  width: 34px; height: 34px; display: grid; place-items: center; flex-shrink: 0;
  border: 0; border-radius: 50%; background: var(--accent); color: var(--accent-ink);
  cursor: pointer; font-size: 12px;
}
.rb-play:hover:not(:disabled) { background: var(--accent-hover); }
.rb-play:disabled { opacity: 0.5; cursor: default; }
.rb-time { font-size: 12px; color: var(--text-muted); white-space: nowrap; }
.rb-scrub { flex: 1; accent-color: var(--accent); cursor: pointer; min-width: 80px; }
.rb-tx-ctl {
  display: flex; align-items: center; gap: 5px; font-size: 12px; color: var(--text-muted);
}
.rb-tx-ctl.off { opacity: 0.55; }
.rb-tx-ctl select, .rb-tx-ctl input {
  font: inherit; font-size: 12px; color: var(--text); padding: 4px 6px;
  border: 1px solid var(--line-strong); border-radius: var(--r-sm); background: var(--surface);
}
.rb-tx-ctl input[type="number"] { width: 48px; }
.rb-tx-ctl select { max-width: 150px; }   /* truncate long options (the Output label) so they don't blow out the bar */
.rb-tx-sep { width: 1px; align-self: stretch; background: var(--line); margin: 0 var(--sp-1); }
</style>
