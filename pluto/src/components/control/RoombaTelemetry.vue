<script setup lang="ts">
// Output/telemetry panel for the SW quadrant: live Roomba data captured from the node's
// own /status (OI battery group + mode/bump/cliff sensors). Fetched DIRECTLY from the
// Pico (CORS open) -- LAN device, one less hop. Polls only while active + a node IP is
// known. Reuses UiBattery + the app's tokens (--ok/--warn/--bad/--surface/--line), no
// bespoke colours.
import { ref, watch, onBeforeUnmount, computed } from 'vue'
import UiBattery from '../ui/UiBattery.vue'
import UiStatusPill from '../ui/UiStatusPill.vue'

const props = defineProps<{ ip: string; active: boolean; name?: string }>()

interface Telemetry {
  charging_state?: number; voltage_mv?: number; current_ma?: number; temp_c?: number
  charge_mah?: number; capacity_mah?: number; battery_pct?: number | null
}
interface Sensors {
  mode?: string
  bump_left?: boolean; bump_right?: boolean; wheeldrop_left?: boolean; wheeldrop_right?: boolean
  cliff_left?: boolean; cliff_front_left?: boolean; cliff_front_right?: boolean; cliff_right?: boolean
}
interface Status {
  online?: boolean; active?: boolean; lights?: boolean; last_command?: string | null
  safety?: string   // 'full' (safeties off, free) | 'safe' (cliff/wheel-drop protection) -- Y toggle
  asleep?: boolean  // snapshot at poll START: it was auto-parked and this poll is waking it
  battery?: number | null; telemetry?: Telemetry; sensors?: Sensors
}

const POLL_MS = 4000
const data  = ref<Status | null>(null)
const error = ref('')
let timer = 0

async function poll() {
  if (!props.ip) return
  try {
    const r = await fetch(`http://${props.ip}/status`, { signal: AbortSignal.timeout(POLL_MS - 500) })
    data.value = await r.json(); error.value = ''
  } catch { error.value = 'unreachable' }
}
// Sleep/wake is fully AUTOMATIC (firmware: idle -> park, poll -> wake), so there are no manual
// buttons -- they'd be self-defeating (this very poll wakes it). We just surface the snapshot:
// `data.asleep` is the state at the START of the poll, so on the first poll back it reads true
// ("it was parked, now waking"), then clears.

// Poll only when the tab is BOTH active and visible. Pausing on hidden (switched apps / minimised)
// stops the throttled background poll that would otherwise keep resetting the firmware's idle
// timer and prevent auto-sleep -- so "away = no polls = it naps" actually holds.
function start() { stop(); if (props.active && props.ip && !document.hidden) { poll(); timer = window.setInterval(poll, POLL_MS) } }
function stop()  { if (timer) { clearInterval(timer); timer = 0 } }
function onVisibility() { start() }   // hidden -> stop (let it sleep); visible -> resume (wakes it)
watch(() => [props.active, props.ip], start, { immediate: true })
document.addEventListener('visibilitychange', onVisibility)
onBeforeUnmount(() => { stop(); document.removeEventListener('visibilitychange', onVisibility) })

const tel = computed<Telemetry>(() => data.value?.telemetry || {})
const sen = computed<Sensors>(() => data.value?.sensors || {})
const pct = computed(() => tel.value.battery_pct ?? data.value?.battery ?? null)
const charging = computed(() => { const s = tel.value.charging_state; return s !== undefined && s >= 1 && s <= 3 })
// Any bump / wheel-drop / cliff currently asserted (a "collision").
const collisions = computed(() => {
  const s = sen.value
  return [
    s.bump_left && 'Bump L', s.bump_right && 'Bump R',
    s.wheeldrop_left && 'Wheel L', s.wheeldrop_right && 'Wheel R',
    s.cliff_left && 'Cliff L', s.cliff_front_left && 'Cliff FL',
    s.cliff_front_right && 'Cliff FR', s.cliff_right && 'Cliff R',
  ].filter(Boolean) as string[]
})
const metrics = computed(() => {
  const t = tel.value
  return [
    { k: 'Voltage', v: t.voltage_mv != null ? (t.voltage_mv / 1000).toFixed(2) + ' V' : '—' },
    { k: 'Current', v: t.current_ma != null ? t.current_ma + ' mA' : '—', neg: (t.current_ma ?? 0) < 0 },
    { k: 'Temp',    v: t.temp_c != null ? t.temp_c + '°C' : '—' },
    { k: 'Charge',  v: t.charge_mah != null ? t.charge_mah + ' mAh' : '—' },
    { k: 'Capacity',v: t.capacity_mah != null ? t.capacity_mah + ' mAh' : '—' },
    { k: 'Last cmd',v: data.value?.last_command || '—' },
  ]
})
</script>

<template>
  <div class="tel">
    <div class="tel__head">
      <span class="tel__title">Telemetry</span>
      <span v-if="name" class="tel__node mono">{{ name }}</span>
      <UiStatusPill :state="error ? 'bad' : 'ok'" :title="error || 'online'" />
    </div>

    <div v-if="error && !data" class="tel__msg mono">Roomba Unreachable at {{ ip }}</div>

    <template v-else>
      <div class="tel__batt">
        <UiBattery :pct="pct" :charging="charging" />
        <span class="tel__pills">
          <span class="tel__pill" :class="data?.active ? 'is-ok' : 'is-warn'">{{ data?.active ? 'Playing' : 'Paused' }}</span>
          <!-- safety + lights are merged: lights follow the mode (on=Full, off=Safe), so one pill says both -->
          <span v-if="data?.safety" class="tel__pill" :class="data.safety === 'full' ? 'is-warn' : 'is-ok'" :title="data.safety === 'full' ? 'Full: safeties OFF, lights ON (drives off edges)' : 'Safe: cliff/wheel-drop protection ON, lights OFF'">{{ data.safety === 'full' ? 'Full · lights on' : 'Safe · lights off' }}</span>
          <!-- snapshot: it was auto-parked when this poll arrived (and this poll is waking it) -->
          <span v-if="data?.asleep" class="tel__pill is-idle" title="Was parked to save battery; this visit is waking it">💤 Was parked</span>
        </span>
      </div>

      <!-- collisions: green when clear, red pills per asserted sensor -->
      <div class="tel__coll">
        <span class="tel__coll-lbl">Collision</span>
        <span v-if="!collisions.length" class="tel__pill is-ok">Clear</span>
        <span v-for="c in collisions" :key="c" class="tel__pill is-bad">{{ c }}</span>
      </div>

      <dl class="tel__grid">
        <div v-for="m in metrics" :key="m.k" class="tel__cell">
          <dt class="tel__k">{{ m.k }}</dt>
          <dd class="tel__v mono" :class="{ neg: m.neg }">{{ m.v }}</dd>
        </div>
      </dl>
    </template>
  </div>
</template>

<style scoped>
.tel { display: flex; flex-direction: column; gap: var(--sp-3); height: 100%; padding: var(--sp-4); font-family: var(--font-sans); overflow: auto; }
.mono { font-family: var(--font-mono); }

.tel__head { display: flex; align-items: center; gap: 8px; }
.tel__title { font-size: 13px; font-weight: 700; color: var(--text); }
.tel__node { font-size: 11px; color: var(--text-muted); }
.tel__msg { font-size: 12px; color: var(--text-muted); padding: 8px 0; }

.tel__batt { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.tel__pills, .tel__coll { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.tel__coll-lbl { font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); }

/* pills follow the app's soft-badge convention (like RobutekControl's rb-pill) */
.tel__pill { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; padding: 2px 8px; border-radius: 999px; background: var(--surface-3); color: var(--text-muted); }
.tel__pill.is-ok { background: var(--ok-soft, var(--surface-3)); color: var(--ok); }
.tel__pill.is-warn { background: var(--warn-soft, var(--surface-3)); color: var(--warn); }
.tel__pill.is-bad { background: var(--bad-soft, var(--surface-3)); color: var(--bad); }
.tel__pill.is-accent { background: var(--accent-soft); color: var(--accent-hover); }
.tel__pill.is-idle { background: var(--surface-3); color: var(--text-muted); }

.tel__grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; margin: 0; background: var(--line); border: 1px solid var(--line); border-radius: var(--radius-sm, 8px); overflow: hidden; }
.tel__cell { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; background: var(--surface); }
.tel__k { font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }
.tel__v { font-size: 14px; font-weight: 600; color: var(--text); margin: 0; }
.tel__v.neg { color: var(--bad); }
</style>
