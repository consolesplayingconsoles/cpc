<script setup lang="ts">
// Shared on-screen keyboard for the manual sources (Keyboard + Claude). Renders ONLY
// the meaningful keys of the selected mapping, positioned by each entry's col/row to
// MIRROR the real controller (d-pad left, Start centre, face buttons in the console's
// diamond). Each cap is painted its real console colour and shows the keyboard key
// that fires it plus the button name.
//
// It is a real input device: physical keydown/keyup AND click press-and-HOLD the button
// (keydown = press, keyup = release) over /robutek/drive's `hold` action, so movement
// sustains while held. Pressed keys light up for feedback either way. The same component
// is the human's collaboration surface on the Claude screen.
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import Joystick from 'vue-joystick-component'

interface LayoutKey { key: string; btn: string; label: string; col: number; row: number }
interface Mapping { controller?: string; layout?: LayoutKey[]; colors?: Record<string, string> }

const props = defineProps<{
  active: boolean
  mapSource: string      // mapping dir to load from (the source: 'keyboard' | 'claude' | 'dreame')
  target: string         // none | keyboard (emulator) | pi
  mapping: string        // mapping stem, e.g. 'dreamcast'
  targetDev?: string     // when target === 'pi': which pico's UART dev to route to
  compact?: boolean      // smaller caps for an embedded side pane (Dreame)
  heading?: string       // eyebrow above the pad (e.g. "Manual Assistance") where the
                         // keyboard is a manual aid to another driver, not the player itself
}>()
const emit = defineEmits<{ 'drive-error': [string] }>()

const API = `http://${window.location.hostname}:7700`
const canDrive = computed(() => props.target === 'pi' || props.target === 'keyboard')
const fitEl = ref<HTMLElement | null>(null)   // the controller area; measured to size the pad to fit
const box = ref({ w: 0, h: 0 })               // its live content box
let resizeObs: ResizeObserver | null = null

// Held buttons (visual feedback + idempotent press/release). Declared up here because
// the immediate mapping watcher below calls releaseAll() during setup, which reads this
// ref -- a `const` would be in the temporal dead zone if declared later.
const pressed = ref<Set<string>>(new Set())
function isDown(btn: string) { return pressed.value.has(btn) }

// ── mapping: layout + colours ──────────────────────────────────────
const def = ref<Mapping | null>(null)
const layout = computed<LayoutKey[]>(() => def.value?.layout ?? [])
const colors = computed<Record<string, string>>(() => def.value?.colors ?? {})
const cols = computed(() => Math.max(1, ...layout.value.map(k => k.col)))
const rows = computed(() => Math.max(1, ...layout.value.map(k => k.row)))

// Analog sticks are a per-CONSOLE UI element (not mapping data): both have a main
// stick; the GameCube adds the yellow C-stick. Detected from the controller name.
const ctrl   = computed(() => (def.value?.controller || props.mapping || '').toLowerCase())
const isGC   = computed(() => ctrl.value.includes('gamecube'))
const isDC   = computed(() => ctrl.value.includes('dreamcast'))
const hasMain = computed(() => isGC.value || isDC.value)
const hasC    = computed(() => isGC.value)

// Dynamic size: the controller scales to FIT the box it is handed (the Claude page is
// often a narrow, short, half-screen portrait). We measure that box (`box`, from a
// ResizeObserver on the controller area) and solve for the largest cap size whose whole
// grid -- plus the corner analog sticks when present -- fits in BOTH width and height.
// That keeps every container scrollbar-free: the pad shrinks instead of overflowing.
const GAP = computed(() => (props.compact ? 6 : 8))
const CAP_MIN = 22
const CAP_MAX = computed(() => (props.compact ? 42 : 58))
// When sticks are present they sit in the corner padding (padX ~= stick, padY ~= 0.86*stick,
// stick ~= 1.4*cap); fold that footprint into the divisor so the fit accounts for it.
const cap = computed(() => {
  const max = CAP_MAX.value
  if (!box.value.w || !box.value.h) return max
  const g = GAP.value, c = cols.value, r = rows.value
  const wExtra = hasMain.value ? 2.8 : 0          // 2 * (stick/cap = 1.4)
  const hExtra = hasMain.value ? 2.41 : 0         // 2 * 0.86 * 1.4
  const padW = hasMain.value ? 0 : g * 2          // a little breathing room when no sticks
  const padH = hasMain.value ? 0 : g * 2
  const capW = (box.value.w - padW - (c - 1) * g) / (c + wExtra)
  const capH = (box.value.h - padH - (r - 1) * g) / (r + hExtra)
  return Math.max(CAP_MIN, Math.min(max, Math.floor(Math.min(capW, capH))))
})
const stickSize = computed(() => {
  if (!hasMain.value) return 0
  const base = props.compact ? 62 : 92
  return Math.max(38, Math.min(base, Math.round(cap.value * 1.4)))
})
const padStyle = computed(() => {
  if (!hasMain.value) return { padding: `${GAP.value}px` }
  const s = stickSize.value
  return { padding: `${Math.round(s * 0.86)}px ${s}px` }   // room for the corner sticks
})
const boardStyle = computed(() => ({
  gridTemplateColumns: `repeat(${cols.value}, var(--cap))`,
  gridTemplateRows: `repeat(${rows.value}, var(--cap))`,
  '--cap': `${cap.value}px`,
}))

async function fetchMapping() {
  if (!props.mapSource || !props.mapping) { def.value = null; return }
  try {
    const r = await fetch(`${API}/mappings/${props.mapSource}/${props.mapping}`)
    const j = await r.json().catch(() => null)
    def.value = (j && !j.error) ? j : null
  } catch { def.value = null }
}
watch(() => [props.mapSource, props.mapping], () => { releaseAll(); fetchMapping() }, { immediate: true })

// physical key -> layout entry. Single chars match case-insensitively; named keys
// ('Enter') match verbatim.
const keyMap = computed(() => {
  const m = new Map<string, LayoutKey>()
  for (const it of layout.value) m.set(it.key.length === 1 ? it.key.toLowerCase() : it.key, it)
  return m
})

// ── driving ────────────────────────────────────────────────────────
async function holdPost(btn: string, down: boolean) {
  if (!canDrive.value) return
  try {
    const r = await fetch(`${API}/robutek/drive`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'hold', down, btn, target: props.target, source: props.mapSource, mapping: props.mapping, ...(props.target === 'pi' && props.targetDev ? { dev: props.targetDev } : {}) }),
    })
    const j = await r.json().catch(() => null)
    emit('drive-error', j && j.ok === false ? (j.error || 'hold failed') : '')
  } catch { emit('drive-error', 'API unreachable') }
}
function press(btn: string) {
  if (pressed.value.has(btn)) return            // ignore key auto-repeat / re-entry
  const s = new Set(pressed.value); s.add(btn); pressed.value = s
  startKeepalive()
  holdPost(btn, true)
}
function release(btn: string) {
  if (!pressed.value.has(btn)) return
  const s = new Set(pressed.value); s.delete(btn); pressed.value = s
  holdPost(btn, false)
}
function releaseAll() { for (const b of Array.from(pressed.value)) release(b) }

// Analog: the joystick move event gives pixel offsets from centre; normalise to an
// axis op (0..1, 0.5 = centre; screen-up = axis-up, so y is inverted). Sent as an
// `axis` action by NAME (MAIN / C) -- no mapping needed, the Pico maps the axis.
async function axisPost(name: string, x: number, y: number) {
  if (!canDrive.value) return
  try {
    await fetch(`${API}/robutek/drive`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'axis', name, x, y, target: props.target, source: props.mapSource, mapping: props.mapping, ...(props.target === 'pi' && props.targetDev ? { dev: props.targetDev } : {}) }),
    })
    emit('drive-error', '')
  } catch { emit('drive-error', 'API unreachable') }
}
function stickMove(name: string, e: { x?: number; y?: number }) {
  const half = stickSize.value / 2
  const nx = Math.max(-1, Math.min(1, (e?.x ?? 0) / half))
  const ny = Math.max(-1, Math.min(1, (e?.y ?? 0) / half))
  startKeepalive()
  axisPost(name, +(0.5 + 0.5 * nx).toFixed(3), +(0.5 - 0.5 * ny).toFixed(3))
}
function stickStop(name: string) { axisPost(name, 0.5, 0.5) }   // recentre on release

// keepalive: hold the live sink open the whole time the board is active so each keypress
// is low-latency (no reconnect). The backend watchdog releases everything if these stop
// (tab closed mid-hold). Mirrors Robutek's drive keepalive.
let ka = 0
function startKeepalive() {
  if (ka || !canDrive.value) return
  ka = window.setInterval(() => {
    if (!canDrive.value) return
    fetch(`${API}/robutek/drive`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'keepalive' }),
    }).catch(() => {})
  }, 2000)
}
function stopKeepalive() { if (ka) { clearInterval(ka); ka = 0 } }

function teardown() {
  releaseAll()
  stopKeepalive()
  if (canDrive.value) {
    fetch(`${API}/robutek/drive`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'pause' }),
    }).catch(() => {})
  }
}

// ── input listeners ────────────────────────────────────────────────
function entryFor(e: KeyboardEvent): LayoutKey | undefined {
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key
  return keyMap.value.get(k)
}
function onKeyDown(e: KeyboardEvent) {
  if (!props.active) return
  const tag = (e.target as HTMLElement | null)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return     // don't hijack form typing
  const it = entryFor(e)
  if (!it) return
  e.preventDefault()
  if (e.repeat) return
  press(it.btn)
}
function onKeyUp(e: KeyboardEvent) {
  if (!props.active) return
  const it = entryFor(e)
  if (!it) return
  e.preventDefault()
  release(it.btn)
}
function onBlur() { releaseAll() }    // window lost focus: a keyup may never arrive

function onCapDown(e: PointerEvent, btn: string) {
  try { (e.currentTarget as Element).setPointerCapture(e.pointerId) } catch { /* unsupported */ }
  press(btn)
}
function onCapUp(_e: PointerEvent, btn: string) { release(btn) }

onMounted(() => {
  window.addEventListener('keydown', onKeyDown, true)
  window.addEventListener('keyup', onKeyUp, true)
  window.addEventListener('blur', onBlur)
  window.addEventListener('pagehide', teardown)
  if (fitEl.value && 'ResizeObserver' in window) {
    resizeObs = new ResizeObserver(([e]) => {
      box.value = { w: e.contentRect.width, h: e.contentRect.height }
    })
    resizeObs.observe(fitEl.value)
  }
  if (props.active && canDrive.value) startKeepalive()
})
onBeforeUnmount(() => {
  teardown()
  if (resizeObs) { resizeObs.disconnect(); resizeObs = null }
  window.removeEventListener('keydown', onKeyDown, true)
  window.removeEventListener('keyup', onKeyUp, true)
  window.removeEventListener('blur', onBlur)
  window.removeEventListener('pagehide', teardown)
})
watch(() => props.active, (on) => { if (on) { fetchMapping(); if (canDrive.value) startKeepalive() } else teardown() })
watch(canDrive, (ok) => { if (!ok) { releaseAll(); stopKeepalive() } else if (props.active) startKeepalive() })

// ── presentation ───────────────────────────────────────────────────
function keyGlyph(k: string) { return k.length === 1 ? k.toUpperCase() : k }
const FALLBACK = '#6b7280'
function colorOf(btn: string) { return colors.value[btn] || FALLBACK }
// readable text colour over a filled cap, by luminance.
function textOn(hex: string) {
  const c = hex.replace('#', '')
  if (c.length < 6) return '#fff'
  const r = parseInt(c.slice(0, 2), 16), g = parseInt(c.slice(2, 4), 16), b = parseInt(c.slice(4, 6), 16)
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.6 ? '#1a1a1a' : '#ffffff'
}
// Full-paint the cap in its console colour; position it on the controller grid.
function capStyle(it: LayoutKey) {
  const c = colorOf(it.btn)
  return { background: c, color: textOn(c), gridColumn: String(it.col), gridRow: String(it.row) }
}
</script>

<template>
  <div class="ck" :class="{ compact }">
    <div class="ck-head">
      <span class="ck-title">{{ def?.controller || mapping || 'Controller' }} - <span v-if="heading" class="ck-assist">{{ heading }}</span></span>
    </div>

    <div ref="fitEl" class="ck-fit">
    <div v-if="layout.length" class="ck-pad" :class="{ off: !canDrive }" :style="padStyle">
      <!-- main analog stick (grey): top-left, above the d-pad -->
      <div v-if="hasMain" class="ck-stick main">
        <Joystick :size="stickSize" base-color="#cdd0d4" stick-color="#5b6068" :throttle="80"
          :disabled="!canDrive" @move="stickMove('MAIN', $event)" @stop="stickStop('MAIN')" />
        <span class="ck-stick-tag">Analog</span>
      </div>

      <div class="ck-board" :style="boardStyle">
        <button
          v-for="it in layout" :key="it.btn"
          class="cap" :class="{ down: isDown(it.btn) }" :style="capStyle(it)"
          @pointerdown.prevent="onCapDown($event, it.btn)"
          @pointerup="onCapUp($event, it.btn)"
          @pointercancel="onCapUp($event, it.btn)"
          @pointerleave="onCapUp($event, it.btn)"
        >
          <span class="cap-key">{{ keyGlyph(it.key) }}</span>
          <span class="cap-btn">{{ it.label }}</span>
        </button>
      </div>

      <!-- GameCube C-stick (yellow): bottom-right -->
      <div v-if="hasC" class="ck-stick cstick">
        <Joystick :size="stickSize" base-color="#fbeca0" stick-color="#eab308" :throttle="80"
          :disabled="!canDrive" @move="stickMove('C', $event)" @stop="stickStop('C')" />
        <span class="ck-stick-tag c">C</span>
      </div>
    </div>
    </div>
  </div>
</template>

<style scoped>
.ck { display: flex; flex-direction: column; align-items: center; gap: var(--sp-3); height: 100%; padding: var(--sp-4); font-family: var(--font-sans); overflow: hidden; }
/* the controller area: the box the pad is measured against and scaled to fit (no scroll) */
.ck-fit { flex: 1 1 0; min-height: 0; min-width: 0; width: 100%; display: grid; place-items: center; }
.ck-head { display: flex; flex-direction: column; align-items: center; gap: 4px; text-align: center; }
.ck-assist { font-size: 12px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-muted); }
.ck-title { font-size: 15px; font-weight: 600; color: var(--text); }
.ck-hint { font-size: 12px; color: var(--text-muted); }
.ck.compact .ck-assist { font-size: 10px; }

/* the controller area: button grid centred, analog sticks in the corners
   (main upper-left above the d-pad, C-stick lower-right) -- positions are UI, not data */
.ck-pad { position: relative; display: flex; align-items: center; justify-content: center; padding: 78px 92px; }
.ck-pad.off { opacity: 0.5; }
.ck-stick { position: absolute; display: flex; flex-direction: column; align-items: center; gap: 4px; user-select: none; }
.ck-stick.main { top: 0; left: 0; }
.ck-stick.cstick { bottom: 0; right: 0; }
.ck-stick-tag { font-size: 10px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; color: var(--text-muted); }
.ck-stick-tag.c { color: #a9820a; }

/* --cap is computed in JS to fit the measured box; the grid + text scale off it */
.ck-board { display: grid; gap: 8px; }

/* compact = embedded side pane (Dreame): smaller caps so it fits beside the map */
.ck.compact { gap: var(--sp-3); padding: var(--sp-3); }
.ck.compact .ck-title { font-size: 12px; }
.ck.compact .ck-board { gap: 6px; }

.cap {
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;
  width: 100%; height: 100%; padding: 4px;
  border: 1px solid rgba(0, 0, 0, 0.14); border-bottom: 3px solid rgba(0, 0, 0, 0.26);
  border-radius: 10px; cursor: pointer; user-select: none;
  transition: transform 0.05s ease, filter 0.05s ease;
}
.cap-key { font-family: var(--font-mono); font-size: clamp(11px, calc(var(--cap) * 0.36), 13px); font-weight: 700; line-height: 1; color: inherit; overflow: hidden; max-width: 100%; text-overflow: clip; }
.cap-btn { font-size: clamp(7px, calc(var(--cap) * 0.2), 10px); font-weight: 600; letter-spacing: 0.02em; opacity: 0.82; color: inherit; line-height: 1; }
.cap:hover { filter: brightness(1.07); }
.cap.down { transform: translateY(2px); border-bottom-width: 1px; filter: brightness(0.82); }

.ck-empty { color: var(--text-muted); font-size: 13px; }
</style>
