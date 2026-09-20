<script setup lang="ts">
// Chat: a call between whoever is at Pluto and the handset riding the roomba.
// Your camera goes out as the handset's face, the handset's mic comes back here.
//
// Two independent conditions gate it (modules/fxos/listen.py): this explicit
// toggle, and a keepalive Pluto sends while the panel is up. Off is the resting
// state, and the keepalive means a closed tab, a crashed Pluto or dropped wifi
// all end the call without anyone switching it off. The handset polls the same
// state and stops on its own, so ending never depends on reaching it.
//
// AI mode is the same session with mode='ai', for when an agent is on this end
// instead of a person.
import { ref, computed, watch, onUnmounted, nextTick } from 'vue'
import { API_BASE } from '../../composables/useNodes'
import { useKeepalive } from '../../composables/useKeepalive'
import UiToggle from '../ui/UiToggle.vue'
import UiSelect from '../ui/UiSelect.vue'

// `talking` is the controller's X hold (verb 'listen'), relayed down by ControlLayout.
const props = defineProps<{ active: boolean; talking?: boolean; cameraNode?: string }>()

interface ListenState {
  live: boolean
  enabled: boolean
  mode: string
  timeout: number
  expires_in: number
  pending: number
  chunks_in: number
}

// Face frames: small and slow on purpose. The handset is a 3.5" HVGA panel on
// wifi, so 320x240 at 8fps costs almost nothing and still reads as live.
const FACE_W = 320
const FACE_H = 240
const FACE_FPS = 8

const state = ref<ListenState | null>(null)
const error = ref('')
const busy = ref(false)
const holding = ref(false)
const sharing = ref(false)
// Mute means what it means everywhere else: the other end stops hearing me.
// Nothing clever. You only hear yourself when both ends are in the SAME room,
// which is a property of testing on your desk, not something a mute should fix.
const muted = ref(false)

// What the handset is for this session. The device is a screen, a speaker and a
// mic; the mode says what drives them. AI and VLC are declared but not built, so
// they are listed and disabled rather than hidden -- the roster is the roadmap.
type Mode = 'chat' | 'ai' | 'openemu' | 'vlc'
const MODES: { id: Mode; label: string; ready: boolean }[] = [
  { id: 'chat',    label: 'Chat',    ready: true },
  { id: 'openemu', label: 'OpenEMU', ready: true },
  { id: 'ai',      label: 'AI',      ready: false },
  { id: 'vlc',     label: 'VLC',     ready: false },
]
const mode = ref<Mode>('chat')

// Which input feeds the handset's speaker. A mic for Chat; for OpenEMU it is a
// loopback device (BlackHole) carrying the emulator, or the capture card's
// "USB3 Digital Audio" carrying a real console. Labels only appear once audio
// permission has been granted at least once, so the list is refreshed after.
const inputs = ref<MediaDeviceInfo[]>([])
const inputId = ref('')

async function refreshInputs(): Promise<void> {
  try {
    const all = await navigator.mediaDevices.enumerateDevices()
    inputs.value = all.filter((d) => d.kind === 'audioinput')
  } catch { inputs.value = [] }
}
// Chat is the only mode that sends this machine's camera and mic.
const isChat = computed(() => mode.value === 'chat')
// A hold that switched the session on must switch it back off on release -- but
// only if the toggle was not already on, or push-to-talk would silently cancel a
// call the operator deliberately left running.
let heldOnly = false
let poll = 0

// Camera capture lives on this machine and streams to the handset over the LAN.
// Held in module scope so nothing here is collected mid-call.
let camStream: MediaStream | null = null
let canvas: HTMLCanvasElement | null = null
// The self-view IS the capture source: one <video> feeding both the preview and
// the canvas, so what you see is exactly what the handset gets.
const camVideo = ref<HTMLVideoElement | null>(null)
let faceTimer = 0

const enabled = computed({
  get: () => !!state.value?.enabled,
  set: (on: boolean) => { void setMode(on) },
})
const live = computed(() => !!state.value?.live)

const keepalive = useKeepalive({
  url: `${API_BASE}/control/listen`,
  body: { action: 'keepalive' },
  intervalMs: 2000,
  guard: () => props.active && !!state.value?.enabled,
})

async function call(action: string, extra: Record<string, unknown> = {}): Promise<void> {
  const res = await window.fetch(`${API_BASE}/control/listen`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, ...extra }),
  })
  if (!res.ok) throw new Error(`${action} failed (${res.status})`)
  state.value = await res.json()
}

// ── camera out ────────────────────────────────────────────────────────────
// Frames are drawn to a canvas and POSTed as JPEG rather than sent over WebRTC:
// the handset is Gecko 28, and an <img> on an MJPEG stream is the one video path
// it handles without argument.
async function startCamera(): Promise<void> {
  if (sharing.value) return
  try {
    camStream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: FACE_W }, height: { ideal: FACE_H } },
      audio: false,
    })
  } catch (e) {
    error.value = 'Camera unavailable'
    return
  }
  sharing.value = true
  await nextTick()               // the <video> only exists once `sharing` is true
  if (camVideo.value) {
    camVideo.value.srcObject = camStream
    await camVideo.value.play().catch(() => {})
  }
  canvas = document.createElement('canvas')
  canvas.width = FACE_W
  canvas.height = FACE_H
  faceTimer = window.setInterval(() => { void sendFace() }, Math.round(1000 / FACE_FPS))
}

function sendFace(): void {
  const v = camVideo.value
  if (!canvas || !v || !v.videoWidth || !state.value?.live) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.drawImage(v, 0, 0, FACE_W, FACE_H)
  canvas.toBlob((blob) => {
    if (!blob) return
    void window.fetch(`${API_BASE}/roomba-ai/face`, {
      method: 'POST', headers: { 'Content-Type': 'image/jpeg' }, body: blob,
    }).catch(() => { /* the session check on the server is the real gate */ })
  }, 'image/jpeg', 0.6)
}

function stopCamera(): void {
  if (faceTimer) { window.clearInterval(faceTimer); faceTimer = 0 }
  // Release the tracks, don't just stop sending: the machine's camera light
  // should go out the moment the call ends.
  if (camStream) { camStream.getTracks().forEach((t) => t.stop()); camStream = null }
  if (camVideo.value) { camVideo.value.srcObject = null }
  canvas = null
  sharing.value = false
}

// ── room audio in ─────────────────────────────────────────────────────────
// Scheduled with Web Audio rather than handed to an <audio> element. An element
// buffers and then plays what it buffered in order at 1x, so any backlog is a
// permanent lag; dragging its currentTime to the live edge only traded the lag
// for constant dropouts. Here we own the clock: blocks are scheduled directly,
// and if we ever fall behind the playhead jumps to now and the backlog is simply
// never played. Late audio in a conversation is worth nothing.
const PCM_RATE = 16000
const JITTER_S = 0.12        // deliberate cushion against network jitter
const MAX_AHEAD_S = 0.6      // scheduled further out than this means we are drifting

let ac: AudioContext | null = null
let playAt = 0
let streaming = false

function startAudio(): void {
  if (streaming) return
  streaming = true
  void pumpAudio()
}

async function pumpAudio(): Promise<void> {
  try {
    const Ctor = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    ac = new Ctor()
    // Started from the toggle click, so this is inside a gesture and allowed.
    if (ac.state === 'suspended') await ac.resume()
    playAt = 0

    const res = await window.fetch(`${API_BASE}/roomba-ai/audio/live?k=${Date.now()}`)
    if (!res.body) { error.value = 'Streaming not supported here'; return }
    const reader = res.body.getReader()
    let leftover = new Uint8Array(0)
    let header = false

    while (streaming) {
      const { done, value } = await reader.read()
      if (done || !value) break
      let buf = new Uint8Array(leftover.length + value.length)
      buf.set(leftover, 0); buf.set(value, leftover.length)

      if (!header) {
        if (buf.length < 44) { leftover = buf; continue }
        buf = buf.slice(44)          // WAV header: format is fixed and known
        header = true
      }
      const usable = buf.length - (buf.length % 2)
      leftover = buf.slice(usable)
      const samples = usable / 2
      if (!samples || !ac) continue

      const view = new DataView(buf.buffer, buf.byteOffset, usable)
      const ab = ac.createBuffer(1, samples, PCM_RATE)
      const ch = ab.getChannelData(0)
      for (let i = 0; i < samples; i++) ch[i] = view.getInt16(i * 2, true) / 32768

      const node = ac.createBufferSource()
      node.buffer = ab
      node.connect(ac.destination)

      const now = ac.currentTime
      // Behind: skip to live. Too far ahead: we are accumulating, pull back.
      if (playAt < now + 0.01 || playAt > now + MAX_AHEAD_S) playAt = now + JITTER_S
      node.start(playAt)
      playAt += ab.duration
    }
  } catch (e) {
    if (streaming) error.value = 'Audio stream dropped'
  } finally {
    streaming = false
  }
}

// ── my voice out ──────────────────────────────────────────────────────────
// Mirror of the uplink: mic -> 16k mono s16le -> POSTed in small blocks. A
// ScriptProcessor rather than an AudioWorklet, to match what the handset can do
// and keep one resampling path to reason about.
let micStream: MediaStream | null = null
let micCtx: AudioContext | null = null
let micProc: ScriptProcessorNode | null = null
let micSrc: MediaStreamAudioSourceNode | null = null
let micLp: BiquadFilterNode | null = null
let micBuf: number[] = []
// Same single-flight rule as the handset: one upload at a time, and drop the
// oldest rather than let a backlog build.
let voiceInflight = false
const VOICE_BLOCK = Math.round(PCM_RATE * 0.128)

async function startMic(): Promise<void> {
  if (micStream) return
  try {
    // Voice processing helps a person in a room and RUINS a line signal: echo
    // cancellation and noise suppression will chew holes in game audio, which is
    // exactly the steady tone they are built to remove. So they follow the mode,
    // not the device.
    const voice = isChat.value
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        deviceId: inputId.value ? { exact: inputId.value } : undefined,
        echoCancellation: voice,
        noiseSuppression: voice,
        autoGainControl: voice,
      },
      video: false,
    })
    void refreshInputs()      // labels are populated now that permission exists
  } catch {
    error.value = 'Microphone unavailable'
    micOn.value = false
    return
  }
  const Ctor = window.AudioContext
  micCtx = new Ctor()
  micSrc = micCtx.createMediaStreamSource(micStream)
  // Anti-alias BEFORE decimating. Dropping 48k to 16k without this folds
  // everything above 8kHz back down into the voice band as hash, which is what
  // made the handset's speaker sound like noise with a voice buried in it.
  // 7kHz leaves speech intact with margin under the 8kHz Nyquist limit.
  micLp = micCtx.createBiquadFilter()
  micLp.type = 'lowpass'
  micLp.frequency.value = 7000
  micProc = micCtx.createScriptProcessor(4096, 1, 1)
  micProc.onaudioprocess = (e) => {
    if ((muted.value && isChat.value) || !state.value?.live) { micBuf = []; return }
    const d = e.inputBuffer.getChannelData(0)
    const ratio = e.inputBuffer.sampleRate / PCM_RATE
    const out = Math.floor(d.length / ratio)
    for (let i = 0; i < out; i++) {
      const idx = i * ratio, lo = Math.floor(idx), hi = lo + 1, frac = idx - lo
      let v = hi < d.length ? d[lo] * (1 - frac) + d[hi] * frac : d[lo]
      v = Math.max(-1, Math.min(1, v))
      micBuf.push(v < 0 ? v * 32768 : v * 32767)
    }
    if (micBuf.length > PCM_RATE) micBuf = micBuf.slice(micBuf.length - PCM_RATE)
    if (!voiceInflight && micBuf.length >= VOICE_BLOCK) flushVoice()
  }
  // Zero-gain sink: the graph needs a path to the destination to be pulled, but
  // routing your own mic to your own speakers is a howl.
  const sink = micCtx.createGain()
  sink.gain.value = 0
  micSrc.connect(micLp); micLp.connect(micProc); micProc.connect(sink); sink.connect(micCtx.destination)
}

function flushVoice(): void {
  const n = micBuf.length
  if (!n || voiceInflight) return
  const ab = new ArrayBuffer(n * 2)
  const view = new DataView(ab)
  for (let i = 0; i < n; i++) view.setInt16(i * 2, micBuf[i] | 0, true)
  micBuf = []
  voiceInflight = true
  void window.fetch(`${API_BASE}/roomba-ai/voice/pcm`, {
    method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: ab,
  }).catch(() => { /* server-side session check is the real gate */ })
    .finally(() => { voiceInflight = false })
}

function stopMic(): void {
  micBuf = []
  if (micProc) { micProc.disconnect(); micProc.onaudioprocess = null; micProc = null }
  if (micLp) { micLp.disconnect(); micLp = null }
  if (micSrc) { micSrc.disconnect(); micSrc = null }
  if (micStream) { micStream.getTracks().forEach((t) => t.stop()); micStream = null }
  if (micCtx) { void micCtx.close().catch(() => {}); micCtx = null }
}

// The mic runs for the whole call: with the handset's speaker mutable at its own
// end, there is nothing to gain from gating the send side too.
// Chat sends a person's voice; OpenEMU sends whatever the chosen input carries.
// Either way the handset's speaker wants a stream, so the capture starts for both.
watch(live, (on) => { if (on && (isChat.value || mode.value === 'openemu')) void startMic() })

// Switching mode mid-session restarts it, so the handset picks the new one up on
// its next poll rather than staying in the old one's behaviour.
watch(mode, async () => {
  if (!state.value?.enabled) return
  await setMode(false)
  await setMode(true)
})

function stopAudio(): void {
  streaming = false
  if (ac) { void ac.close().catch(() => {}); ac = null }
  playAt = 0
}

// ── session ───────────────────────────────────────────────────────────────
async function setMode(on: boolean): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    // AR modes show the roomba's own camera (the handset's is not reachable from
    // web content), so the handset is told where to look.
    const video = (!isChat.value && props.cameraNode)
      ? `${API_BASE}/camera/${props.cameraNode}/stream`
      : undefined
    await call(on ? 'enable' : 'disable', on ? { mode: mode.value, video } : {})
    if (on) {
      keepalive.start()
      if (isChat.value) await startCamera()
      if (isChat.value) startAudio()
      // In AR modes the handset watches the roomba's camera, so nothing to send.
    } else {
      keepalive.stop()
      stopCamera()
      stopAudio()
      stopMic()
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}

async function hold(on: boolean): Promise<void> {
  if (on) {
    if (holding.value) return
    holding.value = true
    heldOnly = !state.value?.enabled
    if (heldOnly) await setMode(true)
    else keepalive.start()
  } else {
    if (!holding.value) return
    holding.value = false
    if (heldOnly) await setMode(false)
    heldOnly = false
  }
}

watch(() => props.talking, (on) => { void hold(!!on) })

async function refresh(): Promise<void> {
  try {
    const res = await window.fetch(`${API_BASE}/roomba-ai/state`)
    state.value = await res.json()
    error.value = ''
  } catch {
    error.value = 'No link to Pluto'
  }
}

// Everything follows the panel: leaving Control stops asserting that anyone is
// watching, the session lapses on the backend's clock, and the camera goes dark
// here rather than waiting for that.
watch(() => props.active, (on) => {
  if (on) {
    void refresh()
    void refreshInputs()
    poll = window.setInterval(() => { void refresh() }, 2000)
    if (state.value?.enabled) keepalive.start()
  } else {
    if (poll) { window.clearInterval(poll); poll = 0 }
    if (holding.value) void hold(false)
    keepalive.stop()
    stopCamera()
    stopAudio()
    stopMic()
  }
}, { immediate: true })

onUnmounted(() => {
  if (poll) window.clearInterval(poll)
  stopCamera()
  stopAudio()
  stopMic()
})
</script>

<template>
  <div class="ai">
    <div class="ai__head">
      <span class="ai__title">Handset</span>
      <span v-if="live" class="ai__live">&#9679; On Call</span>
      <span v-else-if="enabled" class="ai__stale">Session Lapsed</span>
    </div>

    <!-- Controls left, feed right. -->
    <div class="ai__body">
      <div class="ai__controls">
        <div class="ai__row">
          <UiSelect v-model="mode" :disabled="busy">
            <option v-for="m in MODES" :key="m.id" :value="m.id" :disabled="!m.ready">
              {{ m.label }}{{ m.ready ? '' : ' (soon)' }}
            </option>
          </UiSelect>
        </div>
        <div v-if="mode !== 'chat'" class="ai__row">
          <UiSelect v-model="inputId" :disabled="busy">
            <option value="">Default Input</option>
            <option v-for="d in inputs" :key="d.deviceId" :value="d.deviceId">
              {{ d.label || 'Input' }}
            </option>
          </UiSelect>
        </div>
        <div class="ai__row">
          <UiToggle v-model="enabled" :disabled="busy" on-label="On" off-label="Off"
                    title="Starts the session in the selected mode" />
          <span v-if="state && enabled" class="ai__meta mono">{{ state.expires_in }}s</span>
        </div>
        <div v-if="enabled && isChat" class="ai__row">
          <button type="button" class="ai__btn" :class="{ on: muted }"
                  @click="muted = !muted"
                  title="Mute your microphone: the handset stops hearing you.">
            {{ muted ? 'Muted' : 'Mute' }}
          </button>
        </div>

        <div v-if="state && state.chunks_in" class="ai__meta mono">
          {{ state.chunks_in }} Clips &middot; {{ state.pending }} Waiting
        </div>
        <div v-if="error" class="ai__err">{{ error }}</div>
      </div>

      <!-- Self-view: what the handset is showing. Muted, and mirrored the way any
           camera preview is, so it reads as a mirror rather than a monitor. -->
      <video v-show="sharing" ref="camVideo" class="ai__self" autoplay muted playsinline />
    </div>
  </div>
</template>

<style scoped>
.ai { display: flex; flex-direction: column; gap: var(--sp-2); height: 100%; padding: var(--sp-4);
  font-family: var(--font-sans); min-height: 0; }
.ai__head { display: flex; align-items: baseline; gap: 8px; flex: 0 0 auto; }
.ai__title { font-size: 13px; font-weight: 700; color: var(--text); }
.ai__live { margin-left: auto; font-size: 11px; font-weight: 700; color: var(--ok, #12a594); }
.ai__stale { margin-left: auto; font-size: 11px; color: var(--text-muted); }
.ai__body { display: flex; align-items: flex-start; gap: var(--sp-3); flex: 1 1 auto; min-height: 0; }
.ai__controls { display: flex; flex-direction: column; gap: var(--sp-2); flex: 1 1 auto; min-width: 0; }
.ai__row { display: flex; align-items: center; gap: 10px; }
.ai__meta { font-size: 11px; color: var(--text-muted); }
.ai__self { flex: 0 0 auto; width: 40%; max-width: 160px; margin-left: auto; border-radius: var(--radius-sm, 8px);
  background: #0b0d12; transform: scaleX(-1); display: block; }
.ai__btn { padding: 6px 10px; font: 700 11px/1 var(--font-sans); letter-spacing: .03em;
  color: var(--text-muted); background: var(--surface-2, #1b1e26); border: 1px solid var(--line);
  border-radius: var(--radius-sm, 8px); cursor: pointer; }
.ai__btn.on { color: #111; background: var(--accent, #FF9500); border-color: var(--accent, #FF9500); }
.ai__err { font-size: 11px; color: var(--danger, #e5484d); }
.mono { font-family: var(--font-mono); }
</style>
