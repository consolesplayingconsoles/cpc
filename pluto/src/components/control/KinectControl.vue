<template>
  <ControlLayout :active="active" :map-source="'kinect'" :target="props.target || 'none'" :mapping="props.mapping || ''" :target-dev="props.targetDev || ''" @drive-error="$emit('drive-error', $event)">
    <template #nw>
      <CapScreen :live="running && !paused && frameReceived" device="Xbox Kinect v1 RGB"
                 :timestamp="running && hasEverReceivedFrame ? lastFrame : ''"
                 controls :running="running" :busy="sending" @go="onGo" @wait="onWait" @stop="onStop">
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
import { ref, onUnmounted } from 'vue'
import CapScreen from '../CapScreen.vue'
import ControlFeed, { type FeedLine } from './ControlFeed.vue'
import ControlLayout from './ControlLayout.vue'

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
let lastHandState = { left: false, right: false }

// Sensor runs only when Pluto asks it to. Same lifecycle as the HDMI capturer: GO starts
// the capture on the bridge (frames + hand detection), WAIT keeps the live preview but
// stops sending hand events to the pico (like HDMI recording continuing on WAIT), STOP
// ends the capture on the bridge. Idle by default -> "no signal", never spamming the pico.
const running = ref(false)   // capture started (GO), not yet ended (STOP)
const paused  = ref(false)   // WAIT: warm but the pose engine idles (cheap disable)
const sending = ref(false)   // a start/stop request is in flight (disables GO/WAIT)

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

async function sendHandEvent(hand: 'hand_left' | 'hand_right') {
  if (!props.mapping || !props.target) {
    console.debug('[kinect] sendHandEvent blocked: no mapping or target')
    return
  }

  console.debug(`[kinect] sending ${hand} to ${props.target}/${props.mapping}`)

  try {
    const resp = await fetch(`${API}/control/drive`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source: 'kinect',
        target: props.target,
        mapping: props.mapping,
        event: hand,
        role: 'kinect',
      }),
    })
    const data = await resp.json()
    console.debug('[kinect] drive response:', data)
  } catch (e) {
    console.debug('[kinect] drive error:', e)
  }
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

      // Send hand events on state change -- only while GO'd (not paused), so WAIT/STOP
      // never let the sensor drive the pico.
      if (running.value && !paused.value) {
        if (statusData.hand_left && !lastHandState.left) {
          await sendHandEvent('hand_left')
        }
        if (statusData.hand_right && !lastHandState.right) {
          await sendHandEvent('hand_right')
        }
      }
      lastHandState = { left: statusData.hand_left, right: statusData.hand_right }

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
  startPoll()
}
async function onWait() {                    // cheap disable: bridge pauses, pose engine idles
  await postCapture('pause')
  paused.value = true
}
async function onStop() {                   // end the capture on the bridge, back to idle
  await postCapture('stop')
  running.value = false
  paused.value = false
  stopPoll()
  frameReceived.value = false
  hasEverReceivedFrame.value = false        // clear the last frame -> "no signal"
  lastHandState = { left: false, right: false }
  // Keep the pose log on Stop -- that's the moment to read back the session.
}

onUnmounted(() => {
  stopPoll()
  // Leaving the source ends the capture so the sensor doesn't keep streaming unattended.
  if (running.value) postCapture('stop')
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
