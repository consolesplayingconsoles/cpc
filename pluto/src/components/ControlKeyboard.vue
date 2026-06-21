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
const boardStyle = computed(() => ({
  gridTemplateColumns: `repeat(${cols.value}, var(--cap))`,
  gridTemplateRows: `repeat(${rows.value}, var(--cap))`,
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
  if (props.active && canDrive.value) startKeepalive()
})
onBeforeUnmount(() => {
  teardown()
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
      <span v-if="heading" class="ck-assist">{{ heading }}</span>
      <span class="ck-title">{{ def?.controller || mapping || 'Controller' }}</span>
    </div>

    <div v-if="layout.length" class="ck-board" :class="{ off: !canDrive }" :style="boardStyle">
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
  </div>
</template>

<style scoped>
.ck { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--sp-5); height: 100%; padding: var(--sp-5); font-family: var(--font-sans); overflow: auto; }
.ck-head { display: flex; flex-direction: column; align-items: center; gap: 4px; text-align: center; }
.ck-assist { font-size: 12px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-muted); }
.ck-title { font-size: 15px; font-weight: 600; color: var(--text); }
.ck-hint { font-size: 12px; color: var(--text-muted); }
.ck.compact .ck-assist { font-size: 10px; }

.ck-board { display: grid; gap: 8px; --cap: 58px; }
.ck-board.off { opacity: 0.5; }

/* compact = embedded side pane (Dreame): smaller caps so it fits beside the map */
.ck.compact { gap: var(--sp-3); padding: var(--sp-3); }
.ck.compact .ck-title { font-size: 12px; }
.ck.compact .ck-board { --cap: 42px; gap: 6px; }
.ck.compact .cap-key { font-size: 13px; }
.ck.compact .cap-btn { font-size: 8px; }

.cap {
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;
  width: 100%; height: 100%; padding: 4px;
  border: 1px solid rgba(0, 0, 0, 0.14); border-bottom: 3px solid rgba(0, 0, 0, 0.26);
  border-radius: 10px; cursor: pointer; user-select: none;
  transition: transform 0.05s ease, filter 0.05s ease;
}
.cap-key { font-family: var(--font-mono); font-size: 17px; font-weight: 700; line-height: 1; color: inherit; }
.cap-btn { font-size: 10px; font-weight: 600; letter-spacing: 0.02em; opacity: 0.82; color: inherit; }
.cap:hover { filter: brightness(1.07); }
.cap.down { transform: translateY(2px); border-bottom-width: 1px; filter: brightness(0.82); }

.ck-empty { color: var(--text-muted); font-size: 13px; }
</style>
