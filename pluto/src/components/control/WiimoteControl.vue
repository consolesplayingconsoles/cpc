<script setup lang="ts">
// Wii Remote as a Control source. A Pi-native engine (:7750) drives the remote:
//   LINK     Pair scans for a remote in pairing mode (1+2 or the red Sync button),
//            connects + trusts it, and reports connected remotes + battery.
//   SESSION  Start reads the remote's buttons and IR dots and forwards them to the Pi's
//            drive service: buttons as the mapping file says, the AIM (the 4 IR dots
//            worked out into a screen position) as an analog axis. Like the Nokia
//            source: ControlLayout quadrants, status in NW, engine over HTTP, a ping
//            keeps the session alive, leaving the source ends it.
//   CALIBRATE  aim at the picture's 4 corners and press B at each (the LEDs sit on the
//            bezel, outside the picture), saved on the Pi.
import { ref, computed, onMounted, onUnmounted } from 'vue'
import ControlLayout from './ControlLayout.vue'
import UiButton from '../ui/UiButton.vue'
import UiStatusDot from '../ui/UiStatusDot.vue'
import UiBattery from '../ui/UiBattery.vue'

const props = defineProps<{
  active: boolean
  nodes?: Record<string, any>
  target?: string
  mapping?: string
  targetDev?: string
  roombaIp?: string
}>()
const emit = defineEmits<{ 'drive-error': [string] }>()

const ENGINE_PORT = 7750

interface Remote { addr: string; name: string; battery: number | null }
interface Status {
  ok?: boolean; error?: string
  pairing?: boolean; message?: string; wiimotes?: Remote[]
  session?: boolean; dots?: number; aim?: [number, number] | null
  calibrated?: boolean; cal_step?: number | null; cal_message?: string; drive_ok?: boolean
  aim_mode?: string; sensitivity?: number; invert_x?: boolean; invert_y?: boolean
}
type Action = 'pair' | 'stop' | 'disconnect' | 'session_start' | 'session_stop' | 'ping' | 'calibrate' | 'calibrate_reset' | 'aim_options'

const pairing = ref(false)
const message = ref('')
const remotes = ref<Remote[]>([])
const session = ref(false)
const dots = ref(0)
const aim = ref<[number, number] | null>(null)
const calibrated = ref(false)
const calStep = ref<number | null>(null)
const calMessage = ref('')
const driveOk = ref(true)
const aimMode = ref('relative')      // 'relative' (the dots' movement, no calibration) | 'absolute' (4 dots + corner calibration)
const sensitivity = ref(1)
const invertX = ref(false)
const invertY = ref(false)
const busy = ref(false)
const cancelling = ref(false)   // Cancel was pressed; the Pi is still winding the scan down
let poll: ReturnType<typeof setInterval> | null = null
let ping: ReturnType<typeof setInterval> | null = null

const connected = computed(() => remotes.value.length > 0)
const calibrating = computed(() => calStep.value !== null)
const noTarget = computed(() => !props.target || props.target === 'none')

function piIp(): string { return (props.nodes?.['pi'] as any)?.ip || '' }
function engineUrl(): string { return `http://${piIp()}:${ENGINE_PORT}/engine` }

function apply(s: Status | null) {
  if (!s || s.ok === false) return
  pairing.value = !!s.pairing
  if (!pairing.value) cancelling.value = false   // the scan is really over
  message.value = s.message || ''
  remotes.value = Array.isArray(s.wiimotes) ? s.wiimotes : []
  session.value = !!s.session
  dots.value = s.dots || 0
  aim.value = s.aim || null
  calibrated.value = !!s.calibrated
  calStep.value = s.cal_step === undefined ? null : s.cal_step
  calMessage.value = s.cal_message || ''
  driveOk.value = s.drive_ok !== false
  aimMode.value = s.aim_mode || 'relative'
  sensitivity.value = s.sensitivity ?? 1
  invertX.value = !!s.invert_x
  invertY.value = !!s.invert_y
  syncPing()
}

async function engine(action?: Action, extra: Record<string, unknown> = {}): Promise<Status | null> {
  const ip = piIp()
  if (!ip) { emit('drive-error', 'Wii Remote: no Pi node address'); return null }
  try {
    const r = action
      ? await fetch(engineUrl(), {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action, ...extra }), signal: AbortSignal.timeout(6000),
        })
      : await fetch(engineUrl(), { signal: AbortSignal.timeout(4000) })
    const j = (await r.json().catch(() => null)) as Status | null
    if (j && j.ok === false && j.error) emit('drive-error', 'Wii Remote: ' + j.error)
    return j
  } catch {
    emit('drive-error', 'Wii Remote engine unreachable (is the Pi hub running?)')
    return null
  }
}

async function refresh() { apply(await engine()) }

// A session needs a ping inside the Pi's watchdog window, or it ends itself.
function syncPing() {
  if (session.value && !ping) ping = setInterval(() => engine('ping'), 20000)
  if (!session.value && ping) { clearInterval(ping); ping = null }
}

async function onPair() {
  busy.value = true
  apply(await engine('pair'))
  busy.value = false
  emit('drive-error', '')
}
// The Pi only stops after its current connect attempt returns (a few seconds), so Cancel
// stays in its loading state until a status poll reports the scan is over.
async function onCancel() {
  cancelling.value = true
  const s = await engine('stop')
  if (!s) cancelling.value = false     // unreachable: let the button come back
  else apply(s)
}
async function onDisconnect() {
  busy.value = true
  apply(await engine('disconnect'))
  busy.value = false
}
async function onStart() {
  busy.value = true
  // The Pi bridge forwards buttons + aim to the local drive service, which does the
  // mapping; we only hand it the current mapping / target / dev selection.
  apply(await engine('session_start', {
    mapping: props.mapping || '', target: props.target || '', dev: props.targetDev || '',
    aim_axis: 'MAIN',
  }))
  busy.value = false
  emit('drive-error', '')
}
async function onStop() {
  busy.value = true
  apply(await engine('session_stop'))
  busy.value = false
}
async function onCalibrate() { apply(await engine('calibrate')) }
// Live aim options (relative mode): the pointer's speed and direction, no restart needed.
async function setAim(opts: Record<string, unknown>) { apply(await engine('aim_options', opts)) }
async function onClearCalibration() { apply(await engine('calibrate_reset')) }

function pct(v: number): string { return Math.round(v * 100) + '%' }

onMounted(() => {
  refresh()
  poll = setInterval(refresh, 1000)
})
onUnmounted(() => {
  if (poll) { clearInterval(poll); poll = null }
  if (ping) { clearInterval(ping); ping = null }
  if (pairing.value) engine('stop')           // leaving the source ends a running scan
  if (session.value) engine('session_stop')   // ... and the session
})
</script>

<template>
  <ControlLayout :active="active" :map-source="'wiimote'"
    :target="target || 'none'" :mapping="mapping || ''" :target-dev="targetDev || ''"
    :roomba-ip="roombaIp || ''"
    @drive-error="$emit('drive-error', $event)">
    <template #nw>
      <div class="wm">
        <div class="wm-head">
          <div class="wm-id">
            <span class="wm-name">Wii Remote</span>
            <span class="wm-sub mono">Bluetooth &rarr; Pi &rarr; {{ targetDev || 'Pico' }}</span>
          </div>
          <span class="wm-state">
            <UiStatusDot :state="session ? 'ok' : connected ? 'warn' : pairing ? 'warn' : 'off'" />
            <span>{{ session ? 'Playing' : connected ? 'Connected' : pairing ? 'Pairing' : 'Idle' }}</span>
          </span>
        </div>

        <ul v-if="remotes.length" class="wm-list">
          <li v-for="r in remotes" :key="r.addr" class="wm-row">
            <span class="mono">{{ r.addr }}</span>
            <UiBattery :pct="r.battery" />
          </li>
        </ul>

        <div class="wm-actions">
          <UiButton v-if="!pairing" variant="primary" :loading="busy" loading-text="Starting…"
            @click="onPair">
            Pair
          </UiButton>
          <UiButton v-else :loading="cancelling" loading-text="Cancelling…" @click="onCancel">
            Cancel
          </UiButton>
          <UiButton v-if="connected" :disabled="busy" @click="onDisconnect">Disconnect</UiButton>
          <span class="wm-hint">
            {{ message || 'Press Pair, then 1+2 (or the red Sync button) on the Wii Remote.' }}
          </span>
        </div>

        <div v-if="connected" class="wm-play">
          <div class="wm-actions">
            <UiButton v-if="!session" variant="primary" :loading="busy" loading-text="Starting…"
              :disabled="noTarget" @click="onStart">
              Start
            </UiButton>
            <UiButton v-else :disabled="busy" @click="onStop">Stop</UiButton>
            <UiButton v-if="session && aimMode === 'absolute' && !calibrating" :disabled="busy" @click="onCalibrate">Calibrate</UiButton>
            <UiButton v-if="session && aimMode === 'absolute' && calibrated && !calibrating" :disabled="busy" @click="onClearCalibration">
              Clear calibration
            </UiButton>
            <span class="wm-hint">
              {{ session ? (aimMode === 'relative' ? 'Playing. Move the remote to move the pointer.' : (calMessage || (calibrated ? 'Playing, calibrated.' : 'Playing. Calibrate first for an accurate aim.')))
                : noTarget ? 'Pick a Target and a Mapping above, then Start.'
                : 'Start sends the remote\'s buttons and aim to the target.' }}
            </span>
          </div>

          <dl v-if="session" class="wm-live mono">
            <div><dt>IR dots</dt><dd>{{ dots }} / 4</dd></div>
            <div><dt>Aim</dt><dd>{{ aim ? pct(aim[0]) + ' across, ' + pct(aim[1]) + ' up' : 'no aim yet (needs all 4 dots)' }}</dd></div>
            <div v-if="aimMode === 'absolute'"><dt>Calibration</dt><dd>{{ calibrating ? 'corner ' + ((calStep || 0) + 1) + ' of 4' : calibrated ? 'saved' : 'none' }}</dd></div>
            <div v-if="!driveOk"><dt>Drive</dt><dd>the Pi's drive service is not answering</dd></div>
          </dl>

          <div v-if="session && aimMode === 'relative'" class="wm-opts">
            <label class="wm-opt"><input type="checkbox" :checked="invertX" @change="setAim({ invert_x: ($event.target as HTMLInputElement).checked })"> Invert X</label>
            <label class="wm-opt"><input type="checkbox" :checked="invertY" @change="setAim({ invert_y: ($event.target as HTMLInputElement).checked })"> Invert Y</label>
            <label class="wm-opt">Speed
              <input type="range" min="0.25" max="4" step="0.25" :value="sensitivity"
                @change="setAim({ sensitivity: Number(($event.target as HTMLInputElement).value) })">
              <span class="mono">{{ sensitivity }}x</span>
            </label>
          </div>
        </div>
      </div>
    </template>
  </ControlLayout>
</template>

<style scoped>
.wm { display: flex; flex-direction: column; gap: 16px; width: 100%; height: 100%; padding: 18px; overflow: auto; }
.wm-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.wm-id { display: flex; flex-direction: column; gap: 3px; }
.wm-name { font-family: var(--font-sans); font-size: 15px; font-weight: 650; color: var(--text); }
.wm-sub { font-size: 11.5px; color: var(--text-muted); }
.wm-state { display: inline-flex; align-items: center; gap: 6px; font-family: var(--font-sans); font-size: 12px; color: var(--text-muted); white-space: nowrap; }
.wm-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.wm-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; font-size: 12px; color: var(--text); }
.wm-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.wm-hint { font-family: var(--font-sans); font-size: 12px; color: var(--text-muted); flex: 1 1 200px; min-width: 0; }
.wm-play { display: flex; flex-direction: column; gap: 12px; padding-top: 14px; border-top: 1px solid var(--line); }
.wm-live { margin: 0; display: flex; flex-direction: column; gap: 4px; font-size: 12px; }
.wm-live > div { display: flex; gap: 10px; }
.wm-live dt { min-width: 84px; color: var(--text-muted); }
.wm-live dd { margin: 0; color: var(--text); }
.wm-opts { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; font-family: var(--font-sans); font-size: 12px; color: var(--text); }
.wm-opt { display: inline-flex; align-items: center; gap: 6px; }
</style>
