<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'

interface Point { x: number; y: number }

interface Device {
  name: string | null
  model: string | null
  firmware: string | null
  activity: string
  status_label: string
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

const props = defineProps<{ name: string; active: boolean }>()
const API = `http://${window.location.hostname}:7700`

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
const speed       = ref(8)
const SPEEDS      = [1, 2, 4, 8, 16, 32]
const duration    = computed(() => Math.max(1, (sel.value?.cleaning_min ?? 0) * 60))
const progress    = computed(() => Math.min(1, currentTime.value / duration.value))

let raf = 0
let lastTs = 0
function frame(ts: number) {
  if (!playing.value) return
  if (lastTs) {
    currentTime.value = Math.min(duration.value, currentTime.value + ((ts - lastTs) / 1000) * speed.value)
    if (currentTime.value >= duration.value) { playing.value = false; lastTs = 0; return }
  }
  lastTs = ts
  raf = requestAnimationFrame(frame)
}
function play() {
  if (!sel.value?.route?.length) return
  if (progress.value >= 1) currentTime.value = 0
  playing.value = true; lastTs = 0; raf = requestAnimationFrame(frame)
}
function pause() { playing.value = false; cancelAnimationFrame(raf) }
function togglePlay() { playing.value ? pause() : play() }
function seek(e: Event) { pause(); currentTime.value = Number((e.target as HTMLInputElement).value) }
watch(sel, () => { pause(); currentTime.value = 0; svgScale.value = 1 })
onBeforeUnmount(() => cancelAnimationFrame(raf))

// ── route geometry + zoom ─────────────────────────────────────────
const svgScale = ref(1)
const svgCx = ref(0)
const svgCy = ref(0)

const baseBox = computed(() => {
  const s = sel.value
  if (!s?.route?.length) return null
  const pts = s.route
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const pad = Math.max(maxX - minX, maxY - minY) * 0.07
  const cx = s.charger_mm?.[0] ?? null, cy = s.charger_mm?.[1] ?? null
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
  return r.slice(0, n).map(p => `${p.x},${p.y}`).join(' ')
})
const head = computed<Point | null>(() => {
  const r = sel.value?.route ?? []
  if (!r.length) return null
  const n = Math.min(r.length - 1, Math.max(0, Math.floor(progress.value * r.length) - 1))
  return r[n] ?? null
})

// ── layers / consumers (placeholders, wired later) ────────────────
const showFloor    = ref(false)   // floor-plan background layer (follow-up)
const videoOffset  = ref(0)       // s; video plays at currentTime + offset
const hasVideo     = computed(() => false)  // per-clean: true once a video exists for the open clean
const piAvailable  = ref(false)   // true once the Pi-forward feature is wired/reachable
const piEnabled    = ref(false)   // opt-in, decoupled from network presence
const piHeadstart  = ref(0)       // ms lead to compensate Pi/Wii lag

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
const copied = ref('')
function copyId(id: string) {
  navigator.clipboard?.writeText(id).then(() => {
    copied.value = id; setTimeout(() => { if (copied.value === id) copied.value = '' }, 1200)
  }).catch(() => {})
}

// ── cache-first load: history/map render without a session ────────
async function load() {
  loading.value = true
  try {
    const r = await fetch(`${API}/dreame`)
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

    <!-- ── top bar: live tile (cache-first; needs session) + actions ── -->
    <header class="rb-bar">
      <div class="rb-id">
        <span class="rb-dot" :class="status" :title="dev?.online ? 'online' : 'offline'"/>
        <span class="rb-id-name">{{ dev?.name ?? name ?? 'Robutek' }}</span>
        <span v-if="dev?.model" class="rb-id-model mono">{{ dev.model }}</span>
      </div>

      <div class="rb-status">
        <template v-if="connected && dev">
          <span class="rb-pill" :class="actClass">{{ humanStatus(dev.status_label) }}</span>
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
          @click="connected ? load() : openLogin()">
          {{ loading ? 'refreshing…' : connected ? 'refresh' : 'sign in' }}
        </button>
      </div>
    </header>

    <!-- ── login (compact, only when connecting) ── -->
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
        <button class="rb-primary" type="submit" :disabled="submitting || !email || !password">{{ submitting ? 'signing in…' : 'Sign in' }}</button>
        <p v-if="loginError" class="rb-login-err">{{ loginError }}</p>
      </form>
    </div>

    <!-- ── main: table | stage ── -->
    <div class="rb-main">

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
            </span>
            <span class="rb-row-tags">
              <span v-if="s.kind === 'sweep'" class="rb-tag sweep" title="sweep pass (map may be skewed)">sweep</span>
              <button class="rb-id-copy" :title="'copy session id\n' + s.session_id" @click.stop="copyId(s.session_id)">
                <svg v-if="copied !== s.session_id" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>
              </button>
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

      <!-- stage: map (+ video when present) -->
      <section class="rb-stage">
        <div class="rb-map" :class="{ wide: !hasVideo }">
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
              <!-- full route preview: only when paused (while playing, reveal progressively) -->
              <polyline
                v-if="!playing"
                :points="sel.route.map(p => p.x + ',' + p.y).join(' ')"
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
              <!-- robot head -->
              <circle v-if="head" :cx="head.x" :cy="head.y" r="9" fill="var(--accent)" vector-effect="non-scaling-stroke" />
            </svg>

            <div class="rb-map-tools">
              <label class="rb-chip" :class="{ off: !showFloor }" title="floor-plan layer (coming soon)">
                <input type="checkbox" v-model="showFloor" disabled /><span>floor plan</span>
              </label>
              <button v-if="svgScale > 1" class="rb-chip" @click="resetZoom">reset zoom</button>
            </div>
          </template>
        </div>

        <div v-if="hasVideo" class="rb-video"><!-- real <video> wired later --></div>
      </section>
    </div>

    <!-- ── transport / playback bar ── -->
    <footer class="rb-transport" :class="{ disabled: !sel?.route?.length }">
      <button class="rb-play" :disabled="!sel?.route?.length" @click="togglePlay" :title="playing ? 'pause' : 'play'">
        {{ playing ? '❚❚' : '▶' }}
      </button>
      <span class="rb-time mono">{{ fmtClock(currentTime) }} / {{ fmtClock(duration) }}</span>
      <input class="rb-scrub" type="range" min="0" :max="duration" step="1" :value="currentTime" @input="seek" :disabled="!sel?.route?.length" />
      <label class="rb-tx-ctl" title="playback speed">
        <select v-model.number="speed"><option v-for="x in SPEEDS" :key="x" :value="x">{{ x }}×</option></select>
      </label>

      <!-- video / Pi: appear only once the feature is actually available -->
      <template v-if="hasVideo || piAvailable">
        <span class="rb-tx-sep" />
        <label v-if="hasVideo" class="rb-tx-ctl" title="video start offset">
          <span>video</span>
          <input type="number" v-model.number="videoOffset" step="1" /><span class="mono">s</span>
        </label>
        <label v-if="piAvailable" class="rb-tx-ctl" :class="{ off: !piEnabled }" title="forward playback to the Raspberry Pi (opt-in)">
          <input type="checkbox" v-model="piEnabled" /><span>Pi</span>
          <input type="number" v-model.number="piHeadstart" step="50" :disabled="!piEnabled" title="head-start (ms)" /><span class="mono">ms</span>
        </label>
      </template>
    </footer>
  </div>
</template>

<style scoped>
.rb {
  display: flex; flex-direction: column; height: 100%;
  font-family: var(--font-sans); color: var(--text); background: var(--surface-2);
}
.mono { font-family: var(--font-mono); }

/* ── top bar ── */
.rb-bar {
  display: flex; align-items: center; gap: var(--sp-4);
  padding: var(--sp-3) var(--sp-4); background: var(--surface);
  border-bottom: 1px solid var(--line);
}
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
.rb-primary {
  margin-top: 4px; padding: 10px; font: inherit; font-weight: 600; font-size: 14px;
  border: 0; border-radius: var(--r-sm); background: var(--accent); color: var(--accent-ink); cursor: pointer;
}
.rb-primary:hover:not(:disabled) { background: var(--accent-hover); }
.rb-primary:disabled { opacity: 0.5; cursor: default; }
.rb-login-err { font-size: 13px; color: var(--bad); margin: 0; }

/* ── main ── */
.rb-main { position: relative; flex: 1; display: flex; min-height: 0; }

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
.rb-id-copy {
  display: grid; place-items: center; width: 26px; height: 26px; padding: 0;
  border: 0; background: none; color: var(--text-faint); cursor: pointer; border-radius: var(--r-sm);
}
.rb-id-copy:hover { color: var(--accent); background: var(--accent-soft); }
.rb-empty { padding: var(--sp-5) var(--sp-4); font-size: 13px; color: var(--text-muted); text-align: center; }
.rb-collapse {
  position: absolute; top: 12px; z-index: 5; width: 24px; height: 24px;
  display: grid; place-items: center; border: 1px solid var(--line); border-radius: 50%;
  background: var(--surface); color: var(--text-muted); cursor: pointer; box-shadow: var(--shadow-sm);
  font-size: 14px; transition: left 0.18s ease;
}
.rb-collapse:hover { color: var(--accent); border-color: var(--accent); }

/* stage */
.rb-stage { flex: 1; display: flex; min-width: 0; background: var(--surface-2); }
.rb-map { flex: 1; position: relative; display: grid; place-items: center; min-width: 0; background: var(--surface); }
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
.rb-video { width: 42%; border-left: 1px solid var(--line); background: #000; }

/* ── transport ── */
.rb-transport {
  display: flex; align-items: center; gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4); background: var(--surface); border-top: 1px solid var(--line);
}
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
.rb-tx-sep { width: 1px; align-self: stretch; background: var(--line); margin: 0 var(--sp-1); }
</style>
