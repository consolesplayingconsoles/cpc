<script setup lang="ts">
// Reusable capture panel: live video feed + session controls (GO/WAIT/STOP) +
// optional game-action buttons (watch/run/attach). Manages all capture state
// internally and exposes postLog / refreshLog so a parent can post coaching
// messages (ClaudeControl) or trigger scans (GoogleLensControl) after a signal.
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps<{
  active:          boolean
  mapSource:       string
  target:          string
  mapping:         string
  targetDev?:      string
  showGameActions?: boolean  // default false -- opt-in for game control buttons
}>()
const emit = defineEmits<{ 'drive-error': [string]; rumble: [] }>()

const API = `http://${window.location.hostname}:7700`
const SIGNAL_KEY = 'cpc.control.signal'

// ── WAIT / GO ──────────────────────────────────────────────────────────
const signal  = ref<'wait' | 'go'>((localStorage.getItem(SIGNAL_KEY) as 'wait' | 'go') || 'wait')
const sending = ref(false)

async function sendSignal(state: 'wait' | 'go') {
  signal.value = state
  localStorage.setItem(SIGNAL_KEY, state)
  sending.value = true
  let failMsg = ''
  try {
    const r = await fetch(`${API}/control/signal`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state, role: 'system', source: props.mapSource, target: props.target, mapping: props.mapping }),
    })
    const j = await r.json().catch(() => null)
    if (state === 'go' && j && j.capture && j.capture.error) failMsg = j.capture.error
    else emit('drive-error', '')
    await refreshCapture()
  } catch { emit('drive-error', 'API unreachable') }
  finally { sending.value = false }
  if (failMsg) {
    signal.value = 'wait'; localStorage.setItem(SIGNAL_KEY, 'wait')
    emit('drive-error', 'capture: ' + failMsg + ' — staying on WAIT')
  }
}

// ── capture status + lifecycle ──────────────────────────────────────────
interface Capture { running: boolean; device?: string | null; session?: string | null; recording?: boolean; frame_mtime?: number | null }
const capture = ref<Capture>({ running: false })
async function refreshCapture() {
  try { capture.value = await (await fetch(`${API}/control/capture`)).json() }
  catch { /* leave last known */ }
}
async function endCapture() {
  try {
    await fetch(`${API}/control/capture`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'stop' }),
    })
  } catch { /* ignore */ }
  signal.value = 'wait'; localStorage.setItem(SIGNAL_KEY, 'wait')
  await refreshCapture()
}

// ── live frame ──────────────────────────────────────────────────────────
const frameBust = ref(0)
const frameSrc  = computed(() =>
  capture.value.running ? `${API}/control/frame?t=${frameBust.value}` : '')
const frameAge  = computed(() => {
  const m = capture.value.frame_mtime
  if (!m) return null
  return Math.max(0, Math.round(Date.now() / 1000 - m))
})

// ── rumble detection — emits up so the parent can flash the full surface ─
// The first poll after activation only establishes the baseline: pre-existing rumble
// lines in the log must NOT flash on load, only rumbles that arrive while watching.
let _lastRumbleCount = 0
let _rumblePrimed = false
function _checkRumble(lines: { state: string }[]) {
  const n = lines.filter(l => l.state === 'rumble').length
  if (!_rumblePrimed) { _lastRumbleCount = n; _rumblePrimed = true; return }
  if (n > _lastRumbleCount) emit('rumble')
  _lastRumbleCount = n
}

// ── postLog / refreshLog exposed for parents ────────────────────────────
async function postLog(value: string, role: string = 'operator') {
  const v = value.trim()
  if (!v) return
  try {
    await fetch(`${API}/control/signal`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state: v, role, source: props.mapSource, target: props.target, mapping: props.mapping }),
    })
    emit('drive-error', '')
  } catch { emit('drive-error', 'API unreachable') }
}
async function refreshLog() {
  try {
    const j = await (await fetch(`${API}/control/log`)).json()
    _checkRumble(Array.isArray(j.lines) ? j.lines : [])
  } catch { /* ignore */ }
}

// ── game action shortcuts ───────────────────────────────────────────────
function cmdWatch()  { postLog('look',   'operator') }
function cmdRun()    { postLog('run',    'operator') }
function cmdAttach() { postLog('attack', 'operator') }

// ── polling loops ───────────────────────────────────────────────────────
let poll = 0, frameTick = 0
function startLoops() {
  if (!poll)      poll      = window.setInterval(() => { refreshCapture(); refreshLog() }, 2000)
  if (!frameTick) frameTick = window.setInterval(() => { if (capture.value.running) frameBust.value = Date.now() }, 1000)
}
function stopLoops() {
  if (poll)      { clearInterval(poll);      poll = 0 }
  if (frameTick) { clearInterval(frameTick); frameTick = 0 }
}

function activate() {
  signal.value = 'wait'; localStorage.setItem(SIGNAL_KEY, 'wait')
  _rumblePrimed = false          // re-baseline rumbles so a reload never flashes on old lines
  refreshCapture(); startLoops()
}
onMounted(() => { if (props.active) activate() })
onBeforeUnmount(stopLoops)
watch(() => props.active, (on) => { if (on) activate(); else stopLoops() })

defineExpose({ signal, capture, frameSrc, postLog, refreshLog, sendSignal })
</script>

<template>
  <div class="cap">

    <!-- video screen -->
    <div class="cap-screen">
      <div class="cap-screen-inner">
        <img v-if="frameSrc" :src="frameSrc" class="cap-frame" alt="live capture" />
        <div v-else class="cap-frame cap-frame-empty">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="3" y="4.5" width="18" height="12" rx="1.5" /><path d="M9 20h6M12 16.5V20" />
          </svg>
          <span>No signal</span>
        </div>
        <div v-if="capture.running" class="cap-screen-tag">
          <span class="cap-rec live" /> REC<span v-if="frameAge !== null"> · {{ frameAge }}s</span>
        </div>
      </div>
    </div>

    <!-- device meta -->
    <div v-if="capture.device" class="cap-meta">
      <span class="cap-rec" :class="{ live: capture.running }" />
      <span class="cap-meta-device">{{ capture.device }}</span>
    </div>

    <!-- session controls -->
    <div class="cap-controls">
      <button class="cap-btn cap-btn--go"   :disabled="sending" @click="sendSignal('go')"  title="Go — start capture and let the source run">▶</button>
      <button class="cap-btn cap-btn--wait" :disabled="sending" @click="sendSignal('wait')" title="Wait — pause (recording keeps running)">⏸</button>
      <button class="cap-btn cap-btn--stop" :disabled="!capture.running" @click="endCapture" title="Stop — end capture and save the take">⏹</button>

      <template v-if="showGameActions">
        <div class="cap-divider" />
        <button class="cap-btn cap-btn--action" @click="cmdWatch"  title="Watch — read the current frame">👁</button>
        <button class="cap-btn cap-btn--action" @click="cmdRun"    title="Run — analog forward">🏃</button>
        <button class="cap-btn cap-btn--action" @click="cmdAttach" title="Attach — engage">🔫</button>
      </template>

      <slot name="extra-actions" />
    </div>

  </div>
</template>

<style scoped>
.cap {
  display: flex;
  flex-direction: column;
  background: var(--surface);
  position: relative;
}
.cap-screen { padding: var(--sp-3); }
.cap-screen-inner {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  max-height: 260px;
  background: #0b0d10;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  overflow: hidden;
}
.cap-frame {
  display: block; width: 100%; height: 100%; object-fit: contain; background: #0b0d10;
}
.cap-frame-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 5px; width: 100%; height: 100%; color: var(--text-faint); font-size: 11px;
}
.cap-frame-empty svg { width: 20px; height: 20px; opacity: 0.5; }
.cap-screen-tag {
  position: absolute; top: 6px; left: 6px;
  display: inline-flex; align-items: center; gap: 5px;
  font-family: var(--font-mono); font-size: 10px; color: #fff;
  background: rgba(0,0,0,0.6); padding: 2px 7px; border-radius: 999px;
}
.cap-rec {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--text-faint); flex-shrink: 0; display: inline-block;
}
.cap-rec.live { background: var(--bad); animation: cap-pulse 1.4s ease-in-out infinite; }
@keyframes cap-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

.cap-meta {
  display: flex; align-items: center; gap: 5px;
  padding: 0 var(--sp-3) var(--sp-2);
}
.cap-meta-device {
  font-family: var(--font-mono); font-size: 10px; color: var(--text-muted);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.cap-controls {
  display: flex; align-items: center; gap: var(--sp-1);
  padding: var(--sp-2) var(--sp-3);
  border-top: 1px solid var(--line);
  background: var(--surface);
}
.cap-btn {
  flex: 1 1 0; display: flex; align-items: center; justify-content: center;
  height: 38px; font-size: 17px; line-height: 1;
  border: 1px solid transparent; border-radius: var(--r-sm);
  cursor: pointer; transition: background 0.1s, opacity 0.1s;
}
.cap-btn:disabled { opacity: 0.35; cursor: default; }
.cap-btn:active:not(:disabled) { transform: scale(0.94); }
.cap-btn--go   { background: var(--surface-3); color: var(--ok);        border-color: var(--ok); }
.cap-btn--go:hover:not(:disabled) { background: var(--ok); color: #fff; }
.cap-btn--wait { background: var(--surface-3); color: var(--text-muted); border-color: var(--line-strong); }
.cap-btn--wait:hover:not(:disabled) { background: var(--line-strong); }
.cap-btn--stop { background: var(--surface-3); color: var(--bad);        border-color: var(--bad); }
.cap-btn--stop:hover:not(:disabled) { background: var(--bad); color: #fff; }
.cap-divider { width: 1px; height: 26px; background: var(--line-strong); flex-shrink: 0; margin: 0 var(--sp-1); }
.cap-btn--action { background: var(--surface-3); color: var(--text-muted); border-color: var(--line-strong); }
.cap-btn--action:hover:not(:disabled) { background: var(--line-strong); }
</style>
