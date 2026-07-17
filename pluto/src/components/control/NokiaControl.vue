<script setup lang="ts">
// Nokia 6103 phone as a Control source. The phone pairs to the Pi (Bluetooth); a
// Pi-native engine (:7740) owns the link -- it binds rfcomm, receives THIS mapping,
// and drives the local hub -> Pico -> Maple directly, so keypresses never round-trip
// to Pluto (only the mapping + start/stop do). Lifecycle mirrors the Kinect source:
// CONNECT starts the engine (and triggers the phone's accept prompt so you can sync
// it), a 30s ping keeps it alive, leaving the source / STOP tears it down.
import { ref, onUnmounted } from 'vue'
import ControlLayout from './ControlLayout.vue'
import UiButton from '../ui/UiButton.vue'
import UiStatusDot from '../ui/UiStatusDot.vue'

const props = defineProps<{
  active: boolean
  nodes?: Record<string, any>
  target?: string
  mapping?: string
  targetDev?: string
  roombaIp?: string
}>()
const emit = defineEmits<{ 'drive-error': [string] }>()

const ENGINE_PORT = 7740

const running = ref(false)
const busy = ref(false)
let ping: ReturnType<typeof setInterval> | null = null
let poll: ReturnType<typeof setInterval> | null = null

function piIp(): string { return (props.nodes?.['pi'] as any)?.ip || '' }
function engineUrl(): string { return `http://${piIp()}:${ENGINE_PORT}/engine` }

async function engine(action: 'start' | 'stop' | 'ping', extra: Record<string, unknown> = {}) {
  const ip = piIp()
  if (!ip) { emit('drive-error', 'Nokia: no Pi node address'); return null }
  try {
    const r = await fetch(engineUrl(), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, ...extra }), signal: AbortSignal.timeout(4000),
    })
    return await r.json().catch(() => null)
  } catch {
    emit('drive-error', 'Nokia engine unreachable (is it running on the Pi?)')
    return null
  }
}

async function onGo() {
  busy.value = true
  // The Pi bridge forwards keys to the local drive service, which does the mapping;
  // we just hand it the current source/mapping/target selection.
  const res = await engine('start', {
    source: 'nokia', mapping: props.mapping || '',
    target: props.target || '', dev: props.targetDev || '',
  })
  busy.value = false
  if (res && res.ok) {
    running.value = true
    emit('drive-error', '')
    if (!ping) ping = setInterval(() => engine('ping'), 30000)
    if (!poll) poll = setInterval(refresh, 5000)
  } else if (res && res.error) {
    emit('drive-error', 'Nokia: ' + res.error)
  }
}

async function onStop() {
  busy.value = true
  await engine('stop')
  busy.value = false
  running.value = false
  if (ping) { clearInterval(ping); ping = null }
  if (poll) { clearInterval(poll); poll = null }
}

// Detect a watchdog reap (session died on the Pi) so the button reflects reality.
async function refresh() {
  const ip = piIp()
  if (!ip) return
  try {
    const r = await fetch(engineUrl(), { signal: AbortSignal.timeout(3000) })
    const j = await r.json().catch(() => null)
    if (j && j.running === false && running.value) {
      running.value = false
      if (ping) { clearInterval(ping); ping = null }
      if (poll) { clearInterval(poll); poll = null }
    }
  } catch { /* transient */ }
}

onUnmounted(() => {
  if (ping) { clearInterval(ping); ping = null }
  if (poll) { clearInterval(poll); poll = null }
  if (running.value) engine('stop')   // leaving the source ends the phone link
})
</script>

<template>
  <!-- Quadrant layout like the other sources: our status/Connect lives in NW, the
       virtual keyboard is always rendered in SE by ControlLayout. -->
  <ControlLayout :active="active" :map-source="'nokia'"
    :target="target || 'none'" :mapping="mapping || ''" :target-dev="targetDev || ''"
    :roomba-ip="roombaIp || ''"
    @drive-error="$emit('drive-error', $event)">
    <template #nw>
      <div class="nk">
        <div class="nk-head">
          <div class="nk-id">
            <span class="nk-name">Nokia 6103</span>
            <span class="nk-sub mono">Bluetooth &rarr; Pi &rarr; {{ targetDev || 'Pico' }}</span>
          </div>
          <span class="nk-state">
            <UiStatusDot :state="running ? 'ok' : 'bad'" />
            <span>{{ running ? 'Linked' : 'Idle' }}</span>
          </span>
        </div>

        <div class="nk-actions">
          <UiButton :variant="running ? 'secondary' : 'primary'" :loading="busy"
            :loading-text="running ? 'Stopping…' : 'Connecting…'"
            @click="running ? onStop() : onGo()">
            {{ running ? 'Stop' : 'Connect' }}
          </UiButton>
          <span class="nk-hint">
            {{ running
              ? 'Linked. Accept the connection on the phone if it prompts, then play.'
              : 'Open CPC Pad on the phone, then press Connect and accept the prompt.' }}
          </span>
        </div>
      </div>
    </template>
  </ControlLayout>
</template>

<style scoped>
.nk { display: flex; flex-direction: column; gap: 16px; width: 100%; height: 100%; padding: 18px; overflow: auto; background: var(--surface); }
.nk-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.nk-id { display: flex; flex-direction: column; gap: 3px; }
.nk-name { font-family: var(--font-sans); font-size: 15px; font-weight: 650; color: var(--text); }
.nk-sub { font-size: 11.5px; color: var(--text-muted); }
.nk-state { display: inline-flex; align-items: center; gap: 6px; font-family: var(--font-sans); font-size: 12px; color: var(--text-muted); white-space: nowrap; }
.nk-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.nk-hint { font-family: var(--font-sans); font-size: 12px; color: var(--text-muted); flex: 1 1 200px; min-width: 0; }
</style>
