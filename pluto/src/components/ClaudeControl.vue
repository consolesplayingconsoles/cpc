<script setup lang="ts">
// Claude source screen: the shared on-screen keyboard (a collaboration surface — the
// human can nudge keys while Claude plays via its own SSH path) PLUS the big round
// WAIT/GO button and the HDMI-capture controls.
//
// The point of this screen: Claude is NOT allowed to start the capture — Pluto owns it.
// GO logs "go" to the collaboration log AND tells Pluto to roll the HDMI capture (a
// rolling frame at dist/capture/latest.jpg that Claude reads). WAIT logs "wait" and
// never touches the stream. The stream is governed by dist/capture/state.flag, a kill
// switch anyone may write (Pluto, the open page heartbeat, Claude on each frame read,
// or the Stop button); Pluto's watchdog stops ffmpeg on stop/stale.
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import type { NodeMap } from '../composables/useNodes'
import ControlKeyboard from './ControlKeyboard.vue'

const props = defineProps<{
  active: boolean
  nodes?: NodeMap
  mapSource: string
  target: string
  mapping: string
  targetDev?: string
}>()
const emit = defineEmits<{ 'drive-error': [string] }>()

const API = `http://${window.location.hostname}:7700`
const SIGNAL_KEY = 'cpc.control.signal'   // localStorage convention cpc.<domain>.<leaf>

// ── WAIT / GO ──────────────────────────────────────────────────────
const signal = ref<'wait' | 'go'>(
  (localStorage.getItem(SIGNAL_KEY) as 'wait' | 'go') || 'wait')
const sending = ref(false)

async function sendSignal(state: 'wait' | 'go') {
  signal.value = state
  localStorage.setItem(SIGNAL_KEY, state)
  sending.value = true
  let failMsg = ''
  try {
    const r = await fetch(`${API}/control/signal`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state, source: 'claude', target: props.target, mapping: props.mapping }),
    })
    const j = await r.json().catch(() => null)
    // GO asks Pluto to roll the capture; if it couldn't, that's a "hold on, something's
    // wrong" -- don't pretend we're playing. Capture the error and fall back to WAIT below.
    if (state === 'go' && j && j.capture && j.capture.error) failMsg = j.capture.error
    else emit('drive-error', '')
    await refreshCapture()
  } catch { emit('drive-error', 'API unreachable') }
  finally { sending.value = false }
  if (failMsg) {
    await sendSignal('wait')                                  // revert the signal so Claude holds
    emit('drive-error', 'capture: ' + failMsg + ' — staying on WAIT')
  }
}
// The button shows the ACTION you can take (the opposite of the current state): resting
// state is WAIT, so the button reads GO by default; while going it reads WAIT.
const nextState = computed<'wait' | 'go'>(() => (signal.value === 'go' ? 'wait' : 'go'))

// ── capture status + lifecycle ─────────────────────────────────────
interface Capture { running: boolean; device?: string | null; frame_mtime?: number | null }
const capture = ref<Capture>({ running: false })
async function refreshCapture() {
  try {
    const r = await fetch(`${API}/control/capture`)
    capture.value = await r.json()
  } catch { /* leave last known */ }
}
async function startCapture() {
  try {
    const r = await fetch(`${API}/control/capture`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'start' }),
    })
    const j = await r.json().catch(() => null)
    emit('drive-error', j && j.ok === false ? ('capture: ' + (j.error || 'start failed')) : '')
  } catch { emit('drive-error', 'API unreachable') }
  await refreshCapture()
}
async function stopCapture() {
  try {
    await fetch(`${API}/control/capture`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'stop' }),
    })
  } catch { /* ignore */ }
  await refreshCapture()
}
// Manage the capture independently of GO (GO already starts it -- one press; this is the
// stop / restart handle, never a second button you're forced to press).
function toggleCapture() { capture.value.running ? stopCapture() : startCapture() }

// ── operator -> Claude messages ──────────────────────────────────
// Free-text commands ("walk to the door", "left or right?") and the Look key go to the
// SAME control log Claude tails (no extra endpoint -- the signal endpoint takes free
// text now). They don't touch the GO/WAIT toggle; that stays sendSignal's job.
const cmd = ref('')
async function postLog(value: string) {
  const v = value.trim()
  if (!v) return
  try {
    await fetch(`${API}/control/signal`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state: v, source: 'claude', target: props.target, mapping: props.mapping }),
    })
    emit('drive-error', '')
  } catch { emit('drive-error', 'API unreachable') }
}
function sendCommand() { if (cmd.value.trim()) { postLog(cmd.value); cmd.value = '' } }
function takeLook() { postLog('look') }

// keep a running capture alive while this screen is open (one of several refreshers
// of the kill-switch flag; Claude bumps it too on each frame read).
let poll = 0, ka = 0
function startLoops() {
  if (!poll) poll = window.setInterval(refreshCapture, 4000)
  if (!ka) ka = window.setInterval(() => {
    fetch(`${API}/control/capture`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'keepalive' }),
    }).catch(() => {})
  }, 5000)
}
function stopLoops() {
  if (poll) { clearInterval(poll); poll = 0 }
  if (ka) { clearInterval(ka); ka = 0 }
}

const frameAge = computed(() => {
  const m = capture.value.frame_mtime
  if (!m) return null
  return Math.max(0, Math.round(Date.now() / 1000 - m))
})

function activate() {
  // start the session in the resting WAIT state and log it (the baseline the agent
  // sees when it begins tailing). Does not start capture.
  sendSignal('wait')
  refreshCapture()
  startLoops()
}
onMounted(() => { if (props.active) activate() })
onBeforeUnmount(stopLoops)
watch(() => props.active, (on) => { if (on) activate(); else stopLoops() })
</script>

<template>
  <div class="cc">
    <!-- LEFT: Claude is the core of this screen, not a side rail -->
    <aside class="cc-claude">
      <!-- one framed body (TV-remote vibe) instead of divider lines -->
      <div class="cc-remote">
      <div class="cc-sig">
        <div class="cc-go-wrap">
          <button class="cc-go" :class="nextState" :disabled="sending" @click="sendSignal(nextState)"
            :title="nextState === 'go' ? 'Let Claude play (also starts capture)' : 'Tell Claude to wait'">
            {{ nextState.toUpperCase() }}
          </button>
          <!-- camera satellite (the "B" to GO's "A"): one-off "read this frame now" -->
          <button class="cc-look" @click="takeLook" aria-label="Take a look"
            title="Take a look — have Claude read the current frame now">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M4 7h3l1.5-2h7L17 7h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1z" />
              <circle cx="12" cy="13" r="3.5" />
            </svg>
          </button>
        </div>
      </div>

      <div class="cc-cap">
        <button class="cc-cap-btn" :class="{ live: capture.running }" @click="toggleCapture">
          <span class="cc-rec" :class="{ live: capture.running }" />
          {{ capture.running ? 'Stop capture' : 'Start video capture' }}
        </button>
        <div class="cc-cap-meta mono">
          <div v-if="capture.device">{{ capture.device }}</div>
          <div v-if="capture.running && frameAge !== null">frame {{ frameAge }}s ago</div>
        </div>
      </div>

      <!-- operator -> Claude: free-text command (the Look key is the camera satellite by GO) -->
      <div class="cc-msg">
        <div class="cc-cmd">
          <input class="cc-cmd-in" v-model="cmd" placeholder="Tell Claude…" @keydown.enter="sendCommand" />
          <button class="cc-cmd-send" :disabled="!cmd.trim()" @click="sendCommand">Send</button>
        </div>
      </div>
      </div>
    </aside>

    <!-- RIGHT: the controller (centred within its own half, not the whole stage) -->
    <div class="cc-board">
      <ControlKeyboard :active="active" :map-source="mapSource" :target="target" :mapping="mapping"
                       :target-dev="targetDev" heading="Manual Assistance"
                       @drive-error="emit('drive-error', $event)" />
    </div>
  </div>
</template>

<style scoped>
.cc { display: flex; height: 100%; min-height: 0; background: var(--surface-2); }
/* Claude (left) is the core panel, equal billing with the controller (right). */
.cc-claude {
  flex: 1 1 0; min-width: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: var(--sp-6);
  padding: var(--sp-5); border-right: 1px solid var(--line); background: var(--surface);
}
/* the framed body -- TV-remote vibe; replaces the divider lines */
.cc-remote {
  display: flex; flex-direction: column; align-items: center; gap: var(--sp-5);
  padding: var(--sp-6) var(--sp-6) var(--sp-5);
  background: var(--surface-2); border: 1px solid var(--line); border-radius: 22px;
  box-shadow: var(--shadow-sm);
}
.cc-board { flex: 1 1 0; min-width: 0; }
.mono { font-family: var(--font-mono); }

/* big round WAIT/GO ("A") + the camera satellite ("B") */
.cc-sig { display: flex; flex-direction: column; align-items: center; gap: var(--sp-3); }
.cc-go-wrap { position: relative; display: inline-flex; }
.cc-go {
  width: 132px; height: 132px; border-radius: 50%; border: 0; cursor: pointer;
  font-family: var(--font-sans); font-size: 26px; font-weight: 800; letter-spacing: 0.06em; color: #fff;
  transition: transform 0.08s ease, box-shadow 0.15s ease, background 0.15s ease;
}
.cc-go.wait { background: var(--bad); box-shadow: 0 0 0 6px rgba(220, 38, 38, 0.16), var(--shadow-md); }
.cc-go.go   { background: var(--ok);  box-shadow: 0 0 0 6px rgba(22, 163, 74, 0.18), var(--shadow-md); }
.cc-go:hover:not(:disabled) { transform: translateY(-1px); }
.cc-go:active:not(:disabled) { transform: scale(0.97); }
.cc-go:disabled { opacity: 0.7; cursor: default; }

/* capture: a manage button (start/stop) + status meta */
.cc-cap { display: flex; flex-direction: column; gap: var(--sp-2); }
.cc-cap-btn {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  font: inherit; font-size: 13px; font-weight: 600; color: var(--text); cursor: pointer;
  padding: 8px 12px; border: 1px solid var(--line-strong); border-radius: var(--r-sm); background: var(--surface);
}
.cc-cap-btn:hover { border-color: var(--accent); color: var(--accent); }
.cc-cap-btn.live { border-color: var(--bad); color: var(--bad); }
.cc-cap-btn.live:hover { background: rgba(220, 38, 38, 0.06); }
.cc-rec { width: 9px; height: 9px; border-radius: 50%; background: var(--text-faint); flex-shrink: 0; }
.cc-rec.live { background: var(--bad); animation: cc-pulse 1.4s ease-in-out infinite; }
@keyframes cc-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
.cc-cap-meta { display: flex; flex-direction: column; gap: 3px; font-size: 11px; color: var(--text-muted); text-align: center; }

/* operator -> Claude: free-text command + Look */
.cc-msg { display: flex; flex-direction: column; gap: var(--sp-2); width: 232px; }
.cc-cmd { display: flex; gap: var(--sp-2); }
.cc-cmd-in {
  flex: 1 1 auto; min-width: 0; font: inherit; font-size: 13px; color: var(--text);
  padding: 8px 10px; border: 1px solid var(--line-strong); border-radius: var(--r-sm); background: var(--surface);
}
.cc-cmd-in:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.cc-cmd-send {
  flex: 0 0 auto; font: inherit; font-size: 13px; font-weight: 600; color: var(--accent-ink); cursor: pointer;
  padding: 8px 12px; border: 0; border-radius: var(--r-sm); background: var(--accent);
}
.cc-cmd-send:hover:not(:disabled) { background: var(--accent-hover); }
.cc-cmd-send:disabled { opacity: 0.5; cursor: default; }
/* camera satellite: small round button to GO's RIGHT (left = the important side),
   not overlapping, and BLUE so it reads distinct from GO/WAIT/capture/send */
.cc-look {
  position: absolute; right: -10px; bottom: -8px;
  width: 66px; height: 66px; border-radius: 50%; display: grid; place-items: center;
  color: #fff; background: #2f74c0; border: 3px solid var(--surface-2); cursor: pointer;
  box-shadow: 0 0 0 4px rgba(47, 116, 192, 0.16), var(--shadow-sm);
  transition: background 0.15s, transform 0.08s;
}
.cc-look:hover { background: #2861a6; }
.cc-look:active { transform: scale(0.92); }
</style>
