<script setup lang="ts">
// Wii Remote as a Control source. Only the LINK lives here for now: a Pi-native engine
// (:7750) drives bluetoothctl -- Pair scans for a remote in pairing mode (1+2 or the red
// Sync button), connects + trusts it, and reports which remotes are connected and their
// battery. Reading the remote (buttons, IR dots -> aim) is a later stage. Shape mirrors
// the Nokia source: ControlLayout quadrants, status in NW, same engine-over-HTTP pattern.
import { ref, onMounted, onUnmounted } from 'vue'
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
interface Status { ok?: boolean; error?: string; pairing?: boolean; message?: string; wiimotes?: Remote[] }

const pairing = ref(false)
const message = ref('')
const remotes = ref<Remote[]>([])
const busy = ref(false)
const cancelling = ref(false)   // Cancel was pressed; the Pi is still winding the scan down
let poll: ReturnType<typeof setInterval> | null = null

function piIp(): string { return (props.nodes?.['pi'] as any)?.ip || '' }
function engineUrl(): string { return `http://${piIp()}:${ENGINE_PORT}/engine` }

function apply(s: Status | null) {
  if (!s || s.ok === false) return
  pairing.value = !!s.pairing
  if (!pairing.value) cancelling.value = false   // the scan is really over
  message.value = s.message || ''
  remotes.value = Array.isArray(s.wiimotes) ? s.wiimotes : []
}

async function engine(action?: 'pair' | 'stop' | 'disconnect'): Promise<Status | null> {
  const ip = piIp()
  if (!ip) { emit('drive-error', 'Wii Remote: no Pi node address'); return null }
  try {
    const r = action
      ? await fetch(engineUrl(), {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action }), signal: AbortSignal.timeout(6000),
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

onMounted(() => {
  refresh()
  poll = setInterval(refresh, 2000)
})
onUnmounted(() => {
  if (poll) { clearInterval(poll); poll = null }
  if (pairing.value) engine('stop')   // leaving the source ends a running scan
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
            <span class="wm-sub mono">Bluetooth &rarr; Pi</span>
          </div>
          <span class="wm-state">
            <UiStatusDot :state="remotes.length ? 'ok' : pairing ? 'warn' : 'off'" />
            <span>{{ remotes.length ? 'Connected' : pairing ? 'Pairing' : 'Idle' }}</span>
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
          <UiButton v-if="remotes.length" :disabled="busy" @click="onDisconnect">Disconnect</UiButton>
          <span class="wm-hint">
            {{ message || 'Press Pair, then 1+2 (or the red Sync button) on the Wii Remote.' }}
          </span>
        </div>
      </div>
    </template>
  </ControlLayout>
</template>

<style scoped>
.wm { display: flex; flex-direction: column; gap: 16px; width: 100%; height: 100%; padding: 18px; overflow: auto; background: var(--surface); }
.wm-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.wm-id { display: flex; flex-direction: column; gap: 3px; }
.wm-name { font-family: var(--font-sans); font-size: 15px; font-weight: 650; color: var(--text); }
.wm-sub { font-size: 11.5px; color: var(--text-muted); }
.wm-state { display: inline-flex; align-items: center; gap: 6px; font-family: var(--font-sans); font-size: 12px; color: var(--text-muted); white-space: nowrap; }
.wm-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.wm-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; font-size: 12px; color: var(--text); }
.wm-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.wm-hint { font-family: var(--font-sans); font-size: 12px; color: var(--text-muted); flex: 1 1 200px; min-width: 0; }
</style>
