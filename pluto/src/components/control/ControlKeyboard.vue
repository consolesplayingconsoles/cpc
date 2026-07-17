<script setup lang="ts">
// Shared on-screen keyboard for the manual sources (Keyboard + Claude). Renders ONLY
// the meaningful keys of the selected mapping, positioned by each entry's col/row to
// MIRROR the real controller (d-pad left, Start centre, face buttons in the console's
// diamond). Each cap is painted its real console colour and shows the keyboard key
// that fires it plus the button name.
//
// It is a real input device: physical keydown/keyup AND click press-and-HOLD the button
// (keydown = press, keyup = release) over /control/drive's `hold` action, so movement
// sustains while held. Pressed keys light up for feedback either way. The same component
// is the human's collaboration surface on the Claude screen.
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import Joystick from 'vue-joystick-component'
import UiToggle from '../ui/UiToggle.vue'
import { joystickToAxis, keysToAxis, isDirButton, AXIS_CENTER } from '../../lib/analog'
import { resolveDriveVerb } from '../../lib/driveVerb'

interface LayoutKey { key: string; btn: string; label: string; col: number; row: number }
interface Mapping {
  controller?: string; layout?: LayoutKey[]; colors?: Record<string, string>
  actions?: Record<string, string>          // btn -> verb
  combinations?: Record<string, string>     // "BTN1+BTN2" -> verb (fires when both held)
}

const props = defineProps<{
  active: boolean
  mapSource: string      // mapping dir to load from (the source: 'keyboard' | 'claude' | 'dreame')
  target: string         // none | keyboard (emulator) | pi | roomba
  mapping: string        // mapping stem, e.g. 'dreamcast'
  targetDev?: string     // subtarget selector: the pico's UART dev under 'pi', the roomba node id under 'roomba'
  compact?: boolean      // smaller caps for an embedded side pane (Dreame)
  narrow?: boolean       // phone: stick BELOW the board (not corner), big caps -- full-screen pad
  heading?: string       // eyebrow above the pad (e.g. "Manual Assistance") where the
                         // keyboard is a manual aid to another driver, not the player itself
}>()
const emit = defineEmits<{ 'drive-error': [string]; 'listen': [boolean] }>()

const API = `http://${window.location.hostname}:7700`
// The virtual keyboard is the local exception; every other real target (pi, roomba)
// drives a node. Only 'none' (and the empty pre-selection) don't drive.
const canDrive = computed(() => !!props.target && props.target !== 'none')
const fitEl = ref<HTMLElement | null>(null)   // the controller area; measured to size the pad to fit
const box = ref({ w: 0, h: 0 })               // its live content box
let resizeObs: ResizeObserver | null = null

// Held buttons (visual feedback + idempotent press/release). Declared up here because
// the immediate mapping watcher below calls releaseAll() during setup, which reads this
// ref -- a `const` would be in the temporal dead zone if declared later.
const pressed = ref<Set<string>>(new Set())
function isDown(btn: string) { return pressed.value.has(btn) }

// The verb currently HELD on the target (movement is a single sustained verb). Combinations
// mean the effective verb depends on the WHOLE held set, not the last key -- e.g. Fwd+Left
// held together fires one 'forward-left' arc instead of two fighting nudges. We recompute it
// on every press/release and only send a transition when it actually changes.
const activeAction = ref<string | null>(null)
// Held buttons -> one verb, via the SHARED resolver (same one the gamepad path uses), so
// combos (verb-pairs) blend into arcs identically. See lib/driveVerb.ts.
function computeEffectiveAction(): string | null {
  return resolveDriveVerb(pressed.value, def.value)
}

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
// Roomba-style mappings (an `actions` table) get an analog stick too -- it quantises to the
// SAME drive verbs as the d-pad (up->forward, diagonals->arcs), so you can steer with either.
const verbMode = computed(() => !!def.value?.actions)
const hasStick = computed(() => hasMain.value || verbMode.value)

// ── WASD -> analog (Guide Dog mode) ────────────────────────────────────────
// When on, the directional keys/caps steer the MAIN analog stick instead of tapping
// the d-pad -- smooth analog walking for nudging Claude. Only meaningful where the
// console actually has an analog stick (hasMain). Persisted per the cpc.<domain>.<leaf>
// localStorage convention.
const WASD_ANALOG_KEY = 'cpc.control.wasdAnalog'
const wasdAnalog = ref(localStorage.getItem(WASD_ANALOG_KEY) === '1')
watch(wasdAnalog, (v) => localStorage.setItem(WASD_ANALOG_KEY, v ? '1' : '0'))
const analogKeys = computed(() => wasdAnalog.value && hasMain.value)

// current key-driven stick position, tracked so the controlled stick display can follow
const keyAxis = ref({ ...AXIS_CENTER })
const stickKnobStyle = computed(() => {
  const s = stickSize.value
  const knob = Math.round(s * 0.44)          // match vue-joystick-component's knob proportion
  const r = (s - knob) / 2 * 0.72           // travel radius
  const dx = (keyAxis.value.x - 0.5) * 2 * r
  const dy = -(keyAxis.value.y - 0.5) * 2 * r   // flip Y: CSS down = op-space down
  return { width: knob + 'px', height: knob + 'px', transform: `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px))` }
})

// Dynamic size: the controller scales to FIT the box it is handed (the Claude page is
// often a narrow, short, half-screen portrait). We measure that box (`box`, from a
// ResizeObserver on the controller area) and solve for the largest cap size whose whole
// grid -- plus the corner analog sticks when present -- fits in BOTH width and height.
// That keeps every container scrollbar-free: the pad shrinks instead of overflowing.
const GAP = computed(() => (props.compact ? 6 : 8))
const CAP_MIN = 22
// Phone (narrow) wants BIG touch caps; embedded (compact) small; desktop medium.
const CAP_MAX = computed(() => (props.narrow ? 108 : props.compact ? 42 : 58))
// When sticks are present they sit in the corner padding (padX ~= stick, padY ~= 0.86*stick,
// stick ~= 1.4*cap); fold that footprint into the divisor so the fit accounts for it.
const cap = computed(() => {
  const max = CAP_MAX.value
  if (!box.value.w || !box.value.h) return max
  const g = GAP.value, c = cols.value, r = rows.value
  // Stick footprint in the fit: desktop corner-stick eats BOTH width and height; phone
  // (narrow) puts the stick BELOW the board so it eats only height -> board keeps full width.
  const wExtra = hasStick.value && !props.narrow ? 2.8 : 0     // 2 * (stick/cap = 1.4)
  const hExtra = hasStick.value ? (props.narrow ? 2.0 : 2.41) : 0
  const padW = hasStick.value && !props.narrow ? 0 : g * 2     // breathing room when no corner sticks
  const padH = hasStick.value && !props.narrow ? 0 : g * 2
  const capW = (box.value.w - padW - (c - 1) * g) / (c + wExtra)
  const capH = (box.value.h - padH - (r - 1) * g) / (r + hExtra)
  return Math.max(CAP_MIN, Math.min(max, Math.floor(Math.min(capW, capH))))
})
const stickSize = computed(() => {
  if (!hasStick.value) return 0
  const base = props.narrow ? 132 : props.compact ? 62 : 92
  return Math.max(38, Math.min(base, Math.round(cap.value * (props.narrow ? 1.9 : 1.4))))
})
const padStyle = computed(() => {
  if (!hasStick.value) return { padding: `${GAP.value}px` }
  if (props.narrow) return { padding: `${GAP.value}px` }        // stick is in-flow (below), no corner reserve
  const s = stickSize.value
  return { padding: `${Math.round(s * 0.86)}px ${s}px` }        // room for the corner sticks
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
    const r = await fetch(`${API}/control/drive`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'hold', down, btn, target: props.target, source: props.mapSource, mapping: props.mapping, ...(props.targetDev ? { dev: props.targetDev } : {}) }),
    })
    const j = await r.json().catch(() => null)
    emit('drive-error', j && j.ok === false ? (j.error || 'hold failed') : '')
  } catch { emit('drive-error', 'API unreachable') }
}
// Mappings with an `actions` table (the Roomba) resolve the held SET to one verb (so combos
// like Fwd+Left become a single 'forward-left' arc). Console mappings have no `actions` -- they
// stay on the classic per-button hold path, untouched. `verbMode`/`hasStick` are declared up
// with the other stick flags.

// Set the single held drive verb, sending only the transition. New verb goes DOWN before the
// old goes UP so the target never sees an empty-held gap (no drive-stop stutter between, e.g.,
// forward and forward-left). Shared by the d-pad (via computeEffectiveAction) and the stick.
function setDriveVerb(v: string | null) {
  if (v === activeAction.value) return
  if (v) holdPost(v, true)
  if (activeAction.value) holdPost(activeAction.value, false)
  activeAction.value = v
}
function syncActiveAction() { setDriveVerb(computeEffectiveAction()) }

// A button whose verb is 'listen' is a LOCAL hold control (hold-to-listen to the camera audio),
// not a target command -- so it emits up instead of driving anything.
function isListen(btn: string) { return def.value?.actions?.[btn] === 'listen' }

function press(btn: string) {
  if (pressed.value.has(btn)) return            // ignore key auto-repeat / re-entry
  const s = new Set(pressed.value); s.add(btn); pressed.value = s
  if (isListen(btn)) { emit('listen', true); return }
  startKeepalive()
  if (analogKeys.value && isDirButton(btn)) sendKeyAxis()
  else if (verbMode.value) syncActiveAction()
  else holdPost(btn, true)
}
function release(btn: string) {
  if (!pressed.value.has(btn)) return
  const s = new Set(pressed.value); s.delete(btn); pressed.value = s
  if (isListen(btn)) { emit('listen', false); return }
  if (analogKeys.value && isDirButton(btn)) sendKeyAxis()
  else if (verbMode.value) syncActiveAction()
  else holdPost(btn, false)
}
function releaseAll() {
  for (const b of Array.from(pressed.value)) release(b)
  if (activeAction.value) { holdPost(activeAction.value, false); activeAction.value = null }
}

// WASD->analog: recompute the stick from the currently-held directional keys and send it
// as one MAIN axis op (the pure vector math lives in lib/analog, unit-tested).
function sendKeyAxis() {
  const v = keysToAxis(Array.from(pressed.value).filter(isDirButton))
  keyAxis.value = v   // keep dot in sync
  axisPost('MAIN', v.x, v.y)
}
// Toggling mid-session: release everything, recentre stick and dot.
watch(analogKeys, (on) => {
  releaseAll()
  axisPost('MAIN', AXIS_CENTER.x, AXIS_CENTER.y)
  if (!on) keyAxis.value = { ...AXIS_CENTER }
})

// Analog: the joystick move event gives pixel offsets from centre; normalise to an
// axis op (0..1, 0.5 = centre; screen-up = axis-up, so y is inverted). Sent as an
// `axis` action by NAME (MAIN / C) -- no mapping needed, the Pico maps the axis.
async function axisPost(name: string, x: number, y: number) {
  if (!canDrive.value) return
  try {
    const r = await fetch(`${API}/control/drive`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'axis', name, x, y, target: props.target, source: props.mapSource, mapping: props.mapping, ...(props.targetDev ? { dev: props.targetDev } : {}) }),
    })
    const j = await r.json().catch(() => null)
    emit('drive-error', j && j.ok === false ? (j.error || 'axis failed') : '')
  } catch { emit('drive-error', 'API unreachable') }
}
function stickMove(name: string, e: { x?: number; y?: number }) {
  const v = joystickToAxis(e)   // normalise -> op-space (pure, unit-tested in lib/analog)
  startKeepalive()
  axisPost(name, v.x, v.y)
}
function stickStop(name: string) { axisPost(name, AXIS_CENTER.x, AXIS_CENTER.y) }   // recentre on release

// ── stick -> drive verb (verbMode / Roomba) ────────────────────────────────
// Quantise the stick position to one of the 8 drive verbs (or none near centre), resolved
// THROUGH the mapping so it's not Roomba-hardcoded: cardinals use `actions[D_*]`, diagonals
// use `combinations[...]` (the blended arcs). Same verb set the d-pad fires.
const STICK_DEAD = 0.28   // deflection (of the 0.5 half-range) before a direction registers
// Quantise the stick to the d-pad direction BUTTONS, then run them through the shared
// resolver -- so a diagonal becomes the same arc verb the keyboard/gamepad combos produce.
function stickToVerb(x: number, y: number): string | null {
  const dx = x - 0.5, dy = y - 0.5
  if (Math.abs(dx) < STICK_DEAD && Math.abs(dy) < STICK_DEAD) return null
  const btns = new Set<string>()
  if (dy > STICK_DEAD) btns.add('D_UP'); else if (dy < -STICK_DEAD) btns.add('D_DOWN')
  if (dx < -STICK_DEAD) btns.add('D_LEFT'); else if (dx > STICK_DEAD) btns.add('D_RIGHT')
  return resolveDriveVerb(btns, def.value)
}
function stickDrive(e: { x?: number; y?: number }) {
  const v = joystickToAxis(e)
  startKeepalive()
  setDriveVerb(stickToVerb(v.x, v.y))
}
function stickStopDrive() { setDriveVerb(null) }   // recentre -> stop

// keepalive: hold the live sink open the whole time the board is active so each keypress
// is low-latency (no reconnect). The backend watchdog releases everything if these stop
// (tab closed mid-hold). Mirrors Robutek's drive keepalive.
let ka = 0
function startKeepalive() {
  if (ka || !canDrive.value) return
  ka = window.setInterval(() => {
    if (!canDrive.value) return
    fetch(`${API}/control/drive`, {
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
    fetch(`${API}/control/drive`, {
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
      <span class="ck-title">{{ def?.controller || mapping || 'Controller' }}<span v-if="heading"> - <span class="ck-assist">{{ heading }}</span></span></span>
    </div>

    <div ref="fitEl" class="ck-fit">
    <div v-if="layout.length" class="ck-pad" :class="{ off: !canDrive, stacked: narrow }" :style="padStyle">
      <!-- main analog stick (grey): top-left. Toggle lives here so it's spatially linked. -->
      <div v-if="hasMain" class="ck-stick main">
        <div class="ck-stick-wrap" :style="{ width: stickSize + 'px', height: stickSize + 'px' }">
          <Joystick :size="stickSize" base-color="#cdd0d4" stick-color="#5b6068" :throttle="80"
            :disabled="!canDrive" @move="stickMove('MAIN', $event)" @stop="stickStop('MAIN')" />
          <!-- dot follows key presses in analog-keys mode -->
          <div v-if="analogKeys" class="key-dot" :style="stickKnobStyle" />
        </div>
        <UiToggle v-model="wasdAnalog" title="Guide Dog mode: direction keys steer the analog stick" />
        <span class="ck-stick-tag" :class="{ active: analogKeys }">{{ analogKeys ? 'Analog' : 'D-Pad' }}</span>
      </div>

      <!-- Roomba drive stick (grey): quantises to the d-pad's drive verbs. No Guide Dog toggle. -->
      <div v-else-if="verbMode" class="ck-stick main">
        <div class="ck-stick-wrap" :style="{ width: stickSize + 'px', height: stickSize + 'px' }">
          <Joystick :size="stickSize" base-color="#cdd0d4" stick-color="#5b6068" :throttle="80"
            :disabled="!canDrive" @move="stickDrive($event)" @stop="stickStopDrive()" />
        </div>
        <span class="ck-stick-tag active">Drive</span>
      </div>

      <div class="ck-board" :style="boardStyle">
        <button
          v-for="it in layout" :key="it.btn"
          class="cap" :class="{ down: isDown(it.btn), 'analog-dir': analogKeys && isDirButton(it.btn) }" :style="capStyle(it)"
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

/* Phone: board on top (big), stick in-flow below it -- a full-width thumb pad. */
.ck-pad.stacked { flex-direction: column; gap: 18px; }
.ck-pad.stacked .ck-board { order: 1; }
.ck-pad.stacked .ck-stick.main { position: static; order: 2; }
.ck-stick-wrap { position: relative; flex-shrink: 0; z-index: 5 }
.ck-stick-tag { font-size: 10px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; color: var(--text-muted); transition: color 0.18s; }
.ck-stick-tag.active { color: var(--accent); }
.ck-stick-tag.c { color: #a9820a; }

/* dot that follows key presses when analog-keys mode is on */
.key-dot {
  position: absolute; top: 50%; left: 50%;
  width: 20px; height: 20px; border-radius: 50%;
  background: var(--accent); opacity: 0.85;
  pointer-events: none; transition: transform 0.06s ease-out;
}

/* directional caps in analog-keys mode: accent ring so they're visually distinct */
.cap.analog-dir { outline: 2px solid var(--accent); outline-offset: -2px; }

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
