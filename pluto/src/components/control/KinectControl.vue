<template>
  <ControlLayout :active="active" :map-source="'kinect'" :target="props.target || 'none'" :mapping="props.mapping || ''" :target-dev="props.targetDev || ''" :max-cells="['nw']" @drive-error="$emit('drive-error', $event)">
    <template #nw>
      <CapScreen :live="running && !paused && frameReceived" device="Xbox Kinect v1 RGB"
                 :timestamp="running && hasEverReceivedFrame ? lastFrame : ''"
                 controls :running="running" :busy="sending" @go="onGo" @wait="onWait" @stop="onStop">
        <template #actions>
          <!-- Movement (body-relative arm direction) vs Zone (3x3 screen regions). -->
          <UiToggle v-model="zoneMode" on-label="Zone" off-label="Movement"
                    title="Movement: arm direction. Zone: hand position in a 3x3 grid." />
        </template>
        <template #content>
          <canvas v-if="running && hasEverReceivedFrame" ref="canvas" :width="canvasW" :height="canvasH" class="cap-frame" />
          <div v-else class="cap-frame cap-frame-empty">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <rect x="3" y="4.5" width="18" height="12" rx="1.5" /><path d="M9 20h6M12 16.5V20" />
            </svg>
            <span>No signal</span>
          </div>
        </template>
      </CapScreen>
    </template>

    <!-- NE: live pose log (the text context that rides along with each /frame). -->
    <template #ne>
      <ControlFeed title="Pose Log" :lines="logLines" :show-input="false"
        :empty-text="running ? (paused ? 'Paused — press Play to resume reading.' : 'Reading your pose…') : 'Press Play to start reading your pose'" />
    </template>
  </ControlLayout>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import CapScreen from '../CapScreen.vue'
import ControlFeed, { type FeedLine } from './ControlFeed.vue'
import ControlLayout from './ControlLayout.vue'
import UiToggle from '../ui/UiToggle.vue'

const props = defineProps<{
  active: boolean
  nodes?: Record<string, any>
  target?: string
  mapping?: string
  targetDev?: string
  canvasWidth?: number
  canvasHeight?: number
}>()
const emit = defineEmits<{ 'drive-error': [string] }>()

const canvasW = props.canvasWidth ?? 640
const canvasH = props.canvasHeight ?? 480

const API = `http://${window.location.hostname}:7700`
const hasEverReceivedFrame = ref(false)
const frameReceived = ref(false)
const lastFrame = ref('')
const piIp = ref('')
const canvas = ref<HTMLCanvasElement | null>(null)
let pollInterval: ReturnType<typeof setInterval> | null = null

// Sensor runs only when Pluto asks it to. Same lifecycle as the HDMI capturer: GO starts
// the capture on the bridge (frames + hand detection), WAIT keeps the live preview but
// stops sending hand events to the pico (like HDMI recording continuing on WAIT), STOP
// ends the capture on the bridge. Idle by default -> "no signal", never spamming the pico.
const running = ref(false)   // capture started (GO), not yet ended (STOP)
const paused  = ref(false)   // WAIT: warm but the pose engine idles (cheap disable)
const sending = ref(false)   // a start/stop request is in flight (disables GO/WAIT)
let heartbeat: ReturnType<typeof setInterval> | null = null   // 30s engine keepalive while open

// NE pose log: the text context the bridge attaches to each /frame (PERSON/DIR/…),
// appended as it changes. Capped so the deep-watched feed stays small.
const logLines = ref<FeedLine[]>([])
let lastContext = ''
function pushContext(ctx: string) {
  if (!ctx || ctx === lastContext) return
  lastContext = ctx
  logLines.value = [...logLines.value.slice(-149), { state: ctx }]
}

// The Kinect bridge lives on the pi node itself (port 7730), same host the frames come
// from -- so the capture lifecycle POSTs go straight there, not through the Pluto API.
function piIpAddr() { return (props.nodes?.['pi'] as any)?.ip || '' }
async function postCapture(action: 'start' | 'pause' | 'stop') {
  const ip = piIpAddr()
  if (!ip) { emit('drive-error', 'Kinect: no pi node address'); return }
  sending.value = true
  try {
    await fetch(`http://${ip}:7730/capture`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action }), signal: AbortSignal.timeout(2000),
    })
    emit('drive-error', '')
  } catch {
    emit('drive-error', 'Kinect bridge unreachable')
  } finally {
    sending.value = false
  }
}

// Pose-engine lifecycle (on-demand, never a daemon). The bridge spawns it on start/Play and
// kills it on stop; the 30s ping is a keepalive so a forgotten-open engine (tab closed,
// laptop asleep) gets reaped by the bridge watchdog. Best-effort -- failures are non-fatal.
async function postEngine(action: 'start' | 'ping' | 'stop') {
  const ip = piIpAddr()
  if (!ip) return
  try {
    await fetch(`http://${ip}:7730/engine`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action }), signal: AbortSignal.timeout(2000),
    })
  } catch { /* bridge unreachable -- the watchdog will reap on its own */ }
}

function renderFrame(w: number, h: number, b64: string) {
  if (!canvas.value) return

  const ctx = canvas.value.getContext('2d')
  if (!ctx) return

  try {
    const binaryStr = atob(b64)
    const bytes = new Uint8Array(binaryStr.length)
    for (let i = 0; i < binaryStr.length; i++) {
      bytes[i] = binaryStr.charCodeAt(i)
    }

    const imgData = ctx.createImageData(w, h)
    for (let i = 0; i < bytes.length; i++) {
      imgData.data[i] = bytes[i]
    }
    ctx.putImageData(imgData, 0, 0)
  } catch (e) {
    console.error('[kinect] render error:', e)
  }
}

// ── driving: pose -> Dreamcast d-pad through the pico ───────────────────────
// Two modes (toggle in the control bar, persisted):
//   movement -- body-relative: the arm's extended DIRECTION (UP/DOWN/LEFT/RIGHT) from the
//               pose engine. Single d-pad button. Feels like you ARE the character.
//   zone     -- screen-absolute: the active wrist's position in the frame, quantised to a
//               3x3 grid (center=neutral, edges=cardinals, corners=diagonals -> two buttons).
// Both hold d-pad buttons over the SAME /control/drive `hold`+`keepalive` protocol the
// keyboard/gamepad use, so it rides the proven sink -> Pi-Hub -> Pico -> Maple path.
const DIR_BTN: Record<string, string> = { UP: 'D_UP', DOWN: 'D_DOWN', LEFT: 'D_LEFT', RIGHT: 'D_RIGHT' }
const MODE_KEY = 'cpc.kinect.mode'
const mode = ref<'movement' | 'zone'>(
  (localStorage.getItem(MODE_KEY) as 'movement' | 'zone') || 'movement')
watch(mode, (m) => { localStorage.setItem(MODE_KEY, m); releaseAll() })   // drop holds on switch
const zoneMode = computed({                                               // boolean proxy for UiToggle
  get: () => mode.value === 'zone',
  set: (v: boolean) => { mode.value = v ? 'zone' : 'movement' },
})

let held = new Set<string>()

function canDrive() { return !!(props.mapping && props.target) }

async function holdPost(btn: string, down: boolean) {
  if (!canDrive()) return
  try {
    const r = await fetch(`${API}/control/drive`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'hold', down, btn, target: props.target, source: 'kinect',
        mapping: props.mapping, ...(props.targetDev ? { dev: props.targetDev } : {}) }),
    })
    const j = await r.json().catch(() => null)
    emit('drive-error', j && j.ok === false ? (j.error || 'hold failed') : '')
  } catch { emit('drive-error', 'API unreachable') }
}

// Diff the desired held set against the current one, sending only transitions (new buttons
// DOWN before gone buttons UP, so a diagonal never flickers through an empty-held gap).
function setButtons(want: Set<string>) {
  for (const b of want) if (!held.has(b)) holdPost(b, true)
  for (const b of held) if (!want.has(b)) holdPost(b, false)
  held = want
}
function releaseAll() { for (const b of held) holdPost(b, false); held = new Set() }

// movement: DIR= -> one button (neutral/no-ref = none).
function movementButtons(ctx: string): Set<string> {
  const m = /DIR=(\w+)/.exec(ctx || '')
  const b = m ? DIR_BTN[m[1]] : undefined
  return new Set(b ? [b] : [])
}
// zone: active wrist WX/WY (0..1 screen-space) -> 3x3 cell. Center third each axis = neutral;
// a corner adds both a vertical and a horizontal button (diagonal). "WX=-" -> no wrist -> none.
const ZONE_LO = 0.33, ZONE_HI = 0.67
function zoneButtons(ctx: string): Set<string> {
  const mx = /WX=([+\-][\d.]+)/.exec(ctx || '')
  const my = /WY=([+\-][\d.]+)/.exec(ctx || '')
  const s = new Set<string>()
  if (!mx || !my) return s
  const wx = parseFloat(mx[1]), wy = parseFloat(my[1])
  if (wx < ZONE_LO) s.add('D_LEFT'); else if (wx > ZONE_HI) s.add('D_RIGHT')
  if (wy < ZONE_LO) s.add('D_UP');   else if (wy > ZONE_HI) s.add('D_DOWN')
  return s
}
function wantButtons(ctx: string): Set<string> {
  return mode.value === 'zone' ? zoneButtons(ctx) : movementButtons(ctx)
}

// keepalive: hold the live sink open the whole time we're capturing so direction changes are
// low-latency and a sustained hold doesn't idle-release (~6s) between polls. The backend
// watchdog releases everything if these stop (tab closed mid-hold). Mirrors the keyboard source.
let ka = 0
function startKeepalive() {
  if (ka || !canDrive()) return
  ka = window.setInterval(() => {
    fetch(`${API}/control/drive`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'keepalive' }),
    }).catch(() => {})
  }, 2000)
}
function stopKeepalive() { if (ka) { clearInterval(ka); ka = 0 } }
function drivePause() {
  if (!canDrive()) return
  fetch(`${API}/control/drive`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'pause' }),
  }).catch(() => {})
}

async function pollOnce() {
  try {
    const piNode = props.nodes?.['pi']
    if (!piNode) {
      frameReceived.value = false
      return
    }

    const ip = piNode.ip
    if (!ip) {
      frameReceived.value = false
      return
    }

    piIp.value = ip

    // Fetch frame metadata
    const statusResp = await fetch(`http://${ip}:7730/frame`, { signal: AbortSignal.timeout(2000) })
    if (!statusResp.ok) {
      frameReceived.value = false
      return
    }

    const statusData = await statusResp.json()
    if (statusData.context) pushContext(statusData.context)   // pose text -> NE log
    frameReceived.value = statusData.depth || statusData.rgb
    if (frameReceived.value) {
      hasEverReceivedFrame.value = true
      lastFrame.value = new Date(statusData.timestamp * 1000).toLocaleTimeString()

      // Drive the d-pad from the pose (movement or zone) -- only while GO'd (not paused), so
      // WAIT/STOP never let the sensor drive the pico. Neutral releases the held button(s).
      if (running.value && !paused.value) {
        setButtons(wantButtons(statusData.context))
      } else if (held.size) {
        releaseAll()
      }

      // Fetch and render image data
      const imgResp = await fetch(`http://${ip}:7730/image`, { signal: AbortSignal.timeout(2000) })
      if (imgResp.ok) {
        const imgData = await imgResp.json()
        renderFrame(imgData.w, imgData.h, imgData.data)
      }
    }
  } catch (e) {
    console.debug('[kinect] poll error:', e)
    frameReceived.value = false
  }
}

function startPoll() {
  if (pollInterval) return
  pollInterval = setInterval(pollOnce, 500)
}
function stopPoll() {
  if (pollInterval) { clearInterval(pollInterval); pollInterval = null }
}

// ── input-button handlers (emitted up from CapScreen) ──────────────────────
async function onGo() {                     // start the capture on the bridge, then stream
  await postCapture('start')
  running.value = true
  paused.value = false
  startKeepalive()                          // hold the drive sink open while we play
  startPoll()
}
async function onWait() {                    // cheap disable: bridge pauses, pose engine idles
  await postCapture('pause')
  paused.value = true
  releaseAll()                              // let go of any held direction on WAIT
}
async function onStop() {                   // end the capture on the bridge, back to idle
  await postCapture('stop')
  running.value = false
  paused.value = false
  stopPoll()
  releaseAll()                              // release the d-pad, close out the drive
  stopKeepalive()
  drivePause()
  frameReceived.value = false
  hasEverReceivedFrame.value = false        // clear the last frame -> "no signal"
  // Keep the pose log on Stop -- that's the moment to read back the session.
}

onMounted(() => {
  // Opening the Kinect source warms the pose engine (up but idle until Play), and starts the
  // 30s heartbeat that keeps it alive; miss the beats and the bridge watchdog reaps it.
  postEngine('start')
  heartbeat = setInterval(() => postEngine('ping'), 30000)
})

onUnmounted(() => {
  stopPoll()
  if (heartbeat) { clearInterval(heartbeat); heartbeat = null }
  releaseAll()                              // don't leave the d-pad held
  stopKeepalive()
  drivePause()
  // Leaving the source ends the capture and kills the engine so nothing streams/infers unattended.
  if (running.value) postCapture('stop')
  postEngine('stop')
})
</script>

<style scoped>
.cap-frame {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #0b0d10;
}

.cap-frame-empty {
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

.cap-frame-empty svg {
  width: 20px;
  height: 20px;
  opacity: 0.5;
}
</style>
