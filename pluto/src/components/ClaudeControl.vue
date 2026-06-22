<script setup lang="ts">
// Claude source screen. Viewed as a NARROW PORTRAIT half-screen most of the time (Pluto
// shares the monitor with Claude Code for the video), so it is portrait-first and the most
// responsive page in Pluto. Layout: a session bar on top (the play controls + a SMALL video
// reference window, top-right -- the feed is low-res, the hi-fi recording is composited in
// post), then the coaching channel and the controller, stacking in a narrow column and
// splitting side by side only when there's room.
//  - the video shows the live frame Claude reads (GET /control/frame).
//  - the COACHING CHANNEL is a two-way feed (GET /control/log) + a text input: the operator
//    coaches in plain language; Claude posts its status/questions back.
//  - GO opens a SESSION (timestamped dir under dist/capture/) + rolls the capture AND a
//    full-quality recording. WAIT only PAUSES Claude; the recording keeps running. End
//    capture is the explicit stop (GO means GO: no staleness).
// Claude is NEVER allowed to start the capture; Pluto owns it (the safety boundary).
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
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
// GO = let Claude play (also rolls capture). WAIT = ask Claude to PAUSE; the recording
// keeps running (ending the take is the separate End capture button).
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
      body: JSON.stringify({ state, role: 'system', source: 'claude', target: props.target, mapping: props.mapping }),
    })
    const j = await r.json().catch(() => null)
    // GO asks Pluto to roll the capture; if it couldn't, that's a "hold on, something's
    // wrong" -- don't pretend we're playing. Capture the error and fall back to WAIT.
    if (state === 'go' && j && j.capture && j.capture.error) failMsg = j.capture.error
    else emit('drive-error', '')
    await refreshCapture(); await refreshLog()
  } catch { emit('drive-error', 'API unreachable') }
  finally { sending.value = false }
  if (failMsg) {
    signal.value = 'wait'; localStorage.setItem(SIGNAL_KEY, 'wait')
    emit('drive-error', 'capture: ' + failMsg + ' — staying on WAIT')
  }
}
// The button shows the ACTION you can take (the opposite of the current state).
const nextState = computed<'wait' | 'go'>(() => (signal.value === 'go' ? 'wait' : 'go'))

// ── capture status + lifecycle ─────────────────────────────────────
interface Capture {
  running: boolean; device?: string | null; session?: string | null
  recording?: boolean; frame_mtime?: number | null
}
const capture = ref<Capture>({ running: false })
async function refreshCapture() {
  try { capture.value = await (await fetch(`${API}/control/capture`)).json() }
  catch { /* leave last known */ }
}
// End capture: the explicit stop that finalises the take (NOT WAIT, which only pauses).
async function endCapture() {
  try {
    await fetch(`${API}/control/capture`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'stop' }),
    })
  } catch { /* ignore */ }
  signal.value = 'wait'; localStorage.setItem(SIGNAL_KEY, 'wait')   // GO again offers a fresh take
  await refreshCapture()
}

// ── the video reference (the frame Claude reads) ───────────────────
const frameBust = ref(0)
const frameSrc = computed(() =>
  capture.value.running ? `${API}/control/frame?t=${frameBust.value}` : '')
const frameAge = computed(() => {
  const m = capture.value.frame_mtime
  if (!m) return null
  return Math.max(0, Math.round(Date.now() / 1000 - m))
})

// ── Guide Claude channel: the two-way feed + the input ────────────────
interface LogLine { ts: number; iso?: string; state: string; role?: string; by?: string | null }
const lines = ref<LogLine[]>([])
const feedEl = ref<HTMLElement | null>(null)
async function refreshLog() {
  try {
    const j = await (await fetch(`${API}/control/log`)).json()
    lines.value = Array.isArray(j.lines) ? j.lines : []
    await nextTick()
    if (feedEl.value) feedEl.value.scrollTop = feedEl.value.scrollHeight
  } catch { /* leave last known */ }
}
const cmd = ref('')
async function postLog(value: string, role = 'operator') {
  const v = value.trim()
  if (!v) return
  try {
    await fetch(`${API}/control/signal`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state: v, role, source: 'claude', target: props.target, mapping: props.mapping }),
    })
    emit('drive-error', '')
  } catch { emit('drive-error', 'API unreachable') }
  await refreshLog()
}
function sendCommand() { if (cmd.value.trim()) { postLog(cmd.value); cmd.value = '' } }
function takeLook() { postLog('look', 'system') }

// who sent a line: Claude, or the operator (including system signals like go/wait/look).
function lineKind(l: LogLine): 'operator' | 'claude' {
  return l.role === 'claude' ? 'claude' : 'operator'
}

// Claude's name colour, borrowed from its node (so the feed matches the chat); accent fallback.
const claudeColor = computed(() => props.nodes?.['claude']?.color ?? 'var(--accent)')

function feedTime(l: LogLine): string {
  const d = l.iso ? new Date(l.iso) : new Date((l.ts || 0) * 1000)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
}

// Flat feed: each line is "Name: text" inline. System signals (go/wait/look) show as "You: go".
interface FeedItem { key: number; name: string; color: string; text: string }
const feedItems = computed<FeedItem[]>(() =>
  lines.value.map((l, i) => {
    const k = lineKind(l)
    return {
      key: i,
      name: k === 'claude' ? 'Claude' : 'You',
      color: k === 'claude' ? claudeColor.value : 'var(--text-muted)',
      text: l.state,
    }
  })
)

// ── loops: poll status + log (2s) and bust the frame (1s) while open ───
let poll = 0, frameTick = 0
function startLoops() {
  if (!poll) poll = window.setInterval(() => { refreshCapture(); refreshLog() }, 2000)
  if (!frameTick) frameTick = window.setInterval(() => {
    if (capture.value.running) frameBust.value = Date.now()
  }, 1000)
}
function stopLoops() {
  if (poll) { clearInterval(poll); poll = 0 }
  if (frameTick) { clearInterval(frameTick); frameTick = 0 }
}

function activate() {
  // resting state is WAIT, set LOCALLY (no log write -- the take's log only begins at GO).
  signal.value = 'wait'; localStorage.setItem(SIGNAL_KEY, 'wait')
  refreshCapture(); refreshLog(); startLoops()
}
onMounted(() => { if (props.active) activate() })
onBeforeUnmount(stopLoops)
watch(() => props.active, (on) => { if (on) activate(); else stopLoops() })
</script>

<template>
  <div class="cc">
    <div class="cc-body">

      <!-- LEFT: Guide Dog — full-height coaching channel -->
      <section class="cc-guide">
        <div class="cc-guide-head">
          <span class="cc-guide-title">Guide Dog</span>
        </div>

        <div ref="feedEl" class="cc-feed">
          <p v-for="item in feedItems" :key="item.key" class="feed-line">
            <span class="feed-name" :style="{ color: item.color }">{{ item.name }}</span>: {{ item.text }}
          </p>
          <div v-if="feedItems.length === 0" class="feed-empty">
            Guide Dog appears here. Type to guide Claude as it plays.
          </div>
        </div>

        <!-- Action bar: session pills + text input + send -->
        <div class="cc-input-wrap">
          <button class="cc-pill" :class="'cc-pill--' + nextState" :disabled="sending"
            @click="sendSignal(nextState)"
            :title="nextState === 'go' ? 'Let Claude play — starts capture' : 'Pause Claude — recording keeps running'">
            <svg v-if="nextState === 'go'" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4.5l13 7.5-13 7.5z" /></svg>
            <svg v-else viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6.5" y="5" width="3.5" height="14" rx="1" /><rect x="14" y="5" width="3.5" height="14" rx="1" /></svg>
            {{ nextState.toUpperCase() }}
          </button>
          <button class="cc-pill cc-pill--look" @click="takeLook" title="Have Claude read the current frame">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M4 7h3l1.5-2h7L17 7h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1z" />
              <circle cx="12" cy="13" r="3.5" />
            </svg>
            Look
          </button>
          <button class="cc-pill cc-pill--end" :disabled="!capture.running" @click="endCapture"
            title="End capture and save the take — WAIT only pauses Claude">
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
            End
          </button>
          <div class="cc-input-divider" />
          <input class="cc-input" v-model="cmd" placeholder="Guide Dog…" @keydown.enter="sendCommand" />
          <button class="cc-send-btn" :disabled="!cmd.trim()" @click="sendCommand">Send</button>
        </div>
      </section>

      <!-- RIGHT: video full width + manual assistance -->
      <div class="cc-right">

        <div class="cc-deck">
          <div class="cc-screen">
            <div class="cc-screen-inner">
              <img v-if="frameSrc" :src="frameSrc" class="cc-frame" alt="live capture" />
              <div v-else class="cc-frame cc-frame-empty">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <rect x="3" y="4.5" width="18" height="12" rx="1.5" /><path d="M9 20h6M12 16.5V20" />
                </svg>
                <span>No signal</span>
              </div>
              <div v-if="capture.running" class="cc-screen-tag">
                <span class="cc-rec live" /> REC<span v-if="frameAge !== null"> · {{ frameAge }}s</span>
              </div>
            </div>
          </div>
          <div v-if="capture.device" class="cc-deck-meta">
            <span class="cc-rec" :class="{ live: capture.running }" />
            <span class="cc-deck-device">{{ capture.device }}</span>
          </div>
        </div>

        <!-- Manual Assistance (controller keyboard) -->
        <section class="cc-pad">
          <ControlKeyboard :active="active" :map-source="mapSource" :target="target" :mapping="mapping"
                           :target-dev="targetDev" heading="Manual Assistance"
                           @drive-error="emit('drive-error', $event)" />
        </section>
      </div>

    </div>
  </div>
</template>

<style scoped>
/* ── root: full height flex column, sans font baseline ── */
.cc {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--surface-2);
  font-family: var(--font-sans);
}

/* ── body: Guide Dog (left, 50%) + right column (50%) ── */
.cc-body {
  display: flex;
  flex: 1 1 0;
  min-height: 0;
  overflow: hidden;
}

.cc-guide {
  display: flex;
  flex-direction: column;
  flex: 0 0 50%;
  min-width: 0;
  min-height: 0;
  background: var(--surface);
  border-right: 1px solid var(--line);
}

.cc-guide-head {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  flex: 0 0 auto;
  padding: var(--sp-3) var(--sp-4);
  border-bottom: 1px solid var(--line);
}
.cc-guide-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.cc-guide-sub {
  font-size: 11px;
  color: var(--text-muted);
}

/* Feed: flat inline lines, gray background for contrast */
.cc-feed {
  flex: 1 1 0;
  min-height: 0;
  overflow-y: auto;
  padding: 14px 16px 10px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  scroll-behavior: smooth;
  background: var(--surface-2);
}
.feed-empty {
  margin: auto;
  color: var(--text-faint);
  font-size: 13px;
  text-align: center;
  line-height: 1.6;
}
.feed-line {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text);
  margin: 0;
  white-space: pre-wrap;
}
.feed-name {
  font-weight: 700;
  font-size: 13px;
}

/* Action bar: session pills + divider + text input + send */
.cc-input-wrap {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex: 0 0 auto;
  padding: var(--sp-3) var(--sp-4);
  border-top: 1px solid var(--line);
  background: var(--surface);
}
.cc-input-divider {
  width: 1px;
  height: 24px;
  background: var(--line-strong);
  flex-shrink: 0;
  margin: 0 var(--sp-1);
}
.cc-input {
  flex: 1 1 auto;
  min-width: 0;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text);
  padding: 8px 12px;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-sm);
  background: var(--surface);
}
.cc-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.cc-input::placeholder { color: var(--text-faint); }
.cc-send-btn {
  flex: 0 0 auto;
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 600;
  color: var(--accent-ink);
  cursor: pointer;
  padding: 9px 18px;
  border: 0;
  border-radius: var(--r-sm);
  background: var(--accent);
}
.cc-send-btn:hover:not(:disabled) { background: var(--accent-hover); }
.cc-send-btn:disabled { opacity: 0.5; cursor: default; }

/* ── Right column: video + manual assistance ── */
.cc-right {
  display: flex;
  flex-direction: column;
  flex: 0 0 50%;
  min-width: 0;
  min-height: 0;
  background: var(--surface-2);
}

/* Video deck: full width of right column */
.cc-deck {
  flex: 0 0 auto;
  background: var(--surface);
  border-bottom: 1px solid var(--line);
  padding: var(--sp-3);
}

.cc-screen {
  width: 100%;
  min-width: 0;
}
.cc-screen-inner {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  max-height: 260px;
  background: #0b0d10;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  overflow: hidden;
}
.cc-frame {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #0b0d10;
}
.cc-frame-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 5px;
  width: 100%;
  height: 100%;
  color: var(--text-faint);
  font-size: 11px;
}
.cc-frame-empty svg { width: 20px; height: 20px; opacity: 0.5; }
.cc-screen-tag {
  position: absolute;
  top: 6px;
  left: 6px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: #fff;
  background: rgba(0,0,0,0.6);
  padding: 2px 7px;
  border-radius: 999px;
}
.cc-rec {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-faint);
  flex-shrink: 0;
  display: inline-block;
}
.cc-rec.live { background: var(--bad); animation: cc-pulse 1.4s ease-in-out infinite; }
@keyframes cc-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

.cc-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 999px;
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 0.12s, border-color 0.12s, opacity 0.12s, transform 0.06s;
  white-space: nowrap;
}
.cc-pill svg { width: 13px; height: 13px; flex-shrink: 0; }
.cc-pill:disabled { opacity: 0.4; cursor: default; }
.cc-pill:active:not(:disabled) { transform: scale(0.96); }

.cc-pill--go   { background: var(--ok);   color: #fff; }
.cc-pill--go:hover:not(:disabled)   { background: #15803d; }
.cc-pill--wait { background: var(--warn); color: #fff; }
.cc-pill--wait:hover:not(:disabled) { background: #b45309; }
.cc-pill--look { background: var(--surface); color: var(--text-muted); border-color: var(--line-strong); }
.cc-pill--look:hover { color: var(--accent); border-color: var(--accent); background: var(--accent-soft); }
.cc-pill--end  { background: var(--surface); color: var(--bad); border-color: var(--line-strong); }
.cc-pill--end:hover:not(:disabled) { border-color: var(--bad); background: rgba(220,38,38,0.06); }

.cc-deck-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: var(--sp-2) 2px 0;
}
.cc-deck-device {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Manual Assistance */
.cc-pad {
  flex: 1 1 0;
  min-height: 0;
  min-width: 0;
  background: var(--surface);
  border-top: 1px solid var(--line);
}
</style>
