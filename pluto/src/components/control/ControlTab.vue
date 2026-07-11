<script setup lang="ts">
// Control surface: parent of the source/target/(subtarget)/mapping rail. Owns the
// selections (all in the URL: /control/{source}/{target}/{mapping}[/{sub}]) and renders
// the source child: Dreame Cloud (Robutek), Keyboard only (ControlKeyboard), or Claude
// (ClaudeControl). The on-screen keyboard is the one unified controller across all three.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { NodeMap } from '../../composables/useNodes'
import RobutekControl from './RobutekControl.vue'
import ControlKeyboard from './ControlKeyboard.vue'
import ClaudeControl from './ClaudeControl.vue'
import GoogleControl from './GoogleControl.vue'
import KinectControl from './KinectControl.vue'
import RoombaTelemetry from './RoombaTelemetry.vue'
import QuadrantLayout from '../QuadrantLayout.vue'

const props = defineProps<{ active: boolean; nodes?: NodeMap; name?: string; showOffline?: boolean }>()
const route  = useRoute()
const router = useRouter()
const API = `http://${window.location.hostname}:7700`
const isLab = import.meta.env.DEV

// ── SOURCE — the event producer. Dreame Cloud is a configured pinged node (hidden
// when unconfigured unless "Show unconfigured" is on). Keyboard is a manual input mode,
// always available. Claude (the capture-driven AI screen) is LAB-ONLY: capture and the
// LLM client must be co-located on the dev host to be fast, so it's hidden on the C2. ──
const sourceList = computed(() => {
  const out: { id: string; label: string }[] = []
  out.push({ id: 'keyboard', label: 'Keyboard only' })
  if (isLab) out.push({ id: 'claude',       label: 'Claude' })        // Lab only: capture is local to the dev host
  if (isLab) out.push({ id: 'google', label: 'Google' })             // Lab only: requires local capture device
  const d = props.nodes?.['dreame']
  if (d && (d.status !== 'unconfigured' || props.showOffline)) out.push({ id: 'dreame', label: 'Dreame Cloud' })
  const pi = props.nodes?.['pi']
  if (pi && (pi.status !== 'unconfigured' || props.showOffline)) out.push({ id: 'kinect', label: 'Kinect' })
  return out
})
const source = computed(() => (route.params.source as string) || '')

// ── TARGET — output sink (none / emulator / pi / roomba), NOT the console itself.
// Each sink may own a subtarget dimension (pi -> pico, roomba -> node). ──
const piPresent = computed(() => {
  const n = props.nodes?.['pi']
  return !!n && n.status !== 'unconfigured'
})
const roombaNodes = computed(() =>
  Object.values(props.nodes || {})
    .filter(n => n.controlTarget === 'roomba' && (n.status !== 'unconfigured' || props.showOffline)))
const roombaPresent = computed(() => roombaNodes.value.length > 0)
const targetOptions = computed(() => [
  { id: 'none', label: 'No output', disabled: false },
  ...(isLab ? [{ id: 'keyboard', label: 'Local Emulator (via Virtual Keyboard)', disabled: false }] : []),
  { id: 'pi', label: 'Console (via Raspberry Pi)', disabled: !piPresent.value },
  { id: 'roomba', label: 'Roomba', disabled: !roombaPresent.value },
])
const defaultTarget = computed(() => (piPresent.value ? 'pi' : isLab ? 'keyboard' : 'none'))
const target = computed(() => (route.params.target as string) || '')

// ── MAPPING — control scheme for the source (from the API). ──
const mappings = ref<string[]>([])
const mapping  = computed(() => (route.params.mapping as string) || '')
async function fetchMappings(src: string) {
  // Clear FIRST so the previous source's list can't be used while the new one loads
  // (a stale mapping would get written into this source's URL and 404 on fetch).
  mappings.value = []
  if (!src) return
  try {
    const r = await fetch(`${API}/mappings/${src}`)
    const j = await r.json().catch(() => null)
    mappings.value = (j && Array.isArray(j.targets)) ? j.targets : []
  } catch { mappings.value = [] }
}
watch(source, (s) => fetchMappings(s), { immediate: true })

// Which targets carry a subtarget dimension (a 4th URL segment). Keyed by target id
// alone so path() can decide from any target, not just the current one.
const TARGETS_WITH_SUBTARGET = new Set(['pi', 'roomba'])

function path(s: string, t: string, m: string, sb = '') {
  const segs = ['/control', s, t, m]
  if (TARGETS_WITH_SUBTARGET.has(t) && m && sb) segs.push(sb)   // subtarget = 4th positional param (needs mapping filled, since positional)
  return segs.filter((x, i) => i === 0 || x).join('/')
}
// Each picker keeps the OTHER two dimensions populated in the URL by pushing the
// resolved (effective) values, never the raw param -- otherwise changing the target
// drops the mapping from the path even though the dropdown still shows it.
function pick(level: 'source' | 'target' | 'mapping' | 'sub', v: string) {
  if (level === 'source')  router.push(path(v, '', '', ''))                                        // new source resets the rest (canon refills)
  else if (level === 'target')  router.push(path(source.value, v, effMapping.value, effSub.value)) // canon fills the subtarget when v gains one
  else if (level === 'mapping') router.push(path(source.value, effTarget.value, v, effSub.value))
  else                          router.push(path(source.value, effTarget.value, effMapping.value, v)) // subtarget
}

const effTarget  = computed(() => target.value || defaultTarget.value)
// The mapping must MATCH the target's sink: a roomba mapping carries `actions` (button
// -> roomba verb) that only the roomba sink understands, while console mappings (dreamcast,
// gamecube) drive a console pad and have no actions. Pairing the wrong one silently no-ops
// (a dreamcast mapping on the roomba sink finds no verb, fires nothing). So the dropdown
// only offers mappings compatible with the current target: roomba schemes under 'roomba',
// console schemes everywhere else.
function isRoombaMapping(m: string) { return m === 'roomba' || m.startsWith('roomba-') }
const visibleMappings = computed(() =>
  effTarget.value === 'roomba'
    ? mappings.value.filter(isRoombaMapping)
    : mappings.value.filter(m => !isRoombaMapping(m)))
// Only honour the URL's mapping if it's valid for THIS target's list; otherwise fall
// back to the first available. Kills the stale/invalid mapping that rendered blank.
const effMapping = computed(() =>
  (mapping.value && visibleMappings.value.includes(mapping.value)) ? mapping.value : (visibleMappings.value[0] || ''))

// ── SUBTARGET — a part of the chosen TARGET (the 4th URL param, appended after
// mapping; the first three never move). Its CONTENT is defined by the target: the
// 'pi' target's subtargets are the Pi's UART picos (each carrying the ttyAMA `dev`
// the drive routes on); the 'roomba' target's subtargets are the roomba nodes.
// Targets without a subtarget (none / emulator) show no picker. A subtarget only
// exists inside its target -- one slot, target-specific options. ──
interface SubOption { id: string; label: string; dev?: string }
const subList = computed<SubOption[]>(() => {
  if (effTarget.value === 'pi') {
    const list = ((props.nodes?.['pi'] as any)?.picos as Array<{ chipid: string; alias?: string; dev?: string; conn?: string }> | undefined) || []
    return list.filter(p => (p.conn || '').toLowerCase() === 'uart' && p.dev)
               .map(p => ({ id: p.alias || p.chipid, label: p.alias || p.chipid, dev: p.dev as string }))
  }
  if (effTarget.value === 'roomba') {
    return roombaNodes.value.map(n => ({ id: n.id, label: n.name }))
  }
  return []
})
const sub     = computed(() => (route.params.sub as string) || '')
const showSub = computed(() => subList.value.length > 0)
const effSub  = computed(() => {
  if (!showSub.value) return ''
  const ids = subList.value.map(s => s.id)
  return (sub.value && ids.includes(sub.value)) ? sub.value : (ids[0] || '')
})
// The Pi drive routes on the selected pico's ttyAMA dev; other targets don't use it.
const subDev  = computed(() => subList.value.find(s => s.id === effSub.value)?.dev || '')
// The subtarget selector handed to the drive: the pico's UART dev under 'pi', the
// roomba node id under 'roomba' (the backend interprets it per target). '' otherwise.
const driveSub = computed(() =>
  effTarget.value === 'pi' ? subDev.value : effTarget.value === 'roomba' ? effSub.value : '')
// The selected roomba node's host:port, for the SW telemetry panel to poll /status directly.
const roombaIp = computed(() =>
  (effTarget.value === 'roomba' && effSub.value) ? (props.nodes?.[effSub.value]?.ip || '') : '')

// URL-canonicalization: write the resolved defaults INTO the url so the dropdowns and
// the path never disagree. replace() = no history entry. With no source in the path
// (bare /control), land on the first available source; only an empty roster leaves
// the pick-a-source state. Then fill target + mapping defaults.
// Remember the last Control selection so a round-trip (deploy a node, come back) lands
// you where you were instead of the default dropdowns. The whole selection already lives
// in the URL, so we just persist/restore that path (cpc.<domain>.<leaf> key convention).
// Stale parts (a mapping/node since removed) self-heal via the canon below, so a stored
// URL never hard-fails -- worst case it falls back to defaults.
const LAST_URL_KEY = 'cpc.control.lastUrl'

watch([source, target, mapping, sub, mappings, subList, sourceList, () => props.active], () => {
  if (!props.active) return
  if (!source.value) {
    const last = localStorage.getItem(LAST_URL_KEY)
    if (last && last.startsWith('/control/') && last !== route.fullPath) { router.replace(last); return }
    if (sourceList.value.length) router.replace(path(sourceList.value[0].id, '', '', ''))
    return
  }
  // Claude is Lab-only (capture is local to the dev host). A deep link to /control/claude
  // on the C2 must not render it -> fall back to the first available source.
  if ((source.value === 'claude' || source.value === 'google') && !isLab) {
    router.replace(path(sourceList.value[0]?.id || 'keyboard', '', '', ''))
    return
  }
  const t = effTarget.value
  const m = effMapping.value
  const sb = effSub.value   // '' unless the target has subtargets available
  // subtarget canon: under a target that has one, the resolved subtarget must be in
  // the URL; under a target that doesn't, no subtarget segment may linger.
  const subMismatch = TARGETS_WITH_SUBTARGET.has(t) ? (!!sb && sb !== sub.value) : (sub.value !== '')
  if (t !== target.value || (m && m !== mapping.value) || subMismatch) router.replace(path(source.value, t, m, sb))
  else if (m) localStorage.setItem(LAST_URL_KEY, path(source.value, t, m, sb))   // canon settled: remember it
}, { immediate: true })

// Control OWNS the drive-error surface: the source children (Robutek / ControlKeyboard /
// ClaudeControl) report up via @drive-error, shown in the shared control bar rather than
// buried in a source. Auto-clears so a transient failure doesn't linger.
const controlError = ref('')
let errTimer = 0
function setError(msg: string) {
  controlError.value = msg
  if (errTimer) { clearTimeout(errTimer); errTimer = 0 }
  if (msg) errTimer = window.setTimeout(() => { controlError.value = '' }, 5000)
}

// Lab dev escape hatch: open this source's mapping folder in your IDE to edit schemes.
function openMappingDir() {
  fetch(`${API}/config/open`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sub: 'mappings/' + source.value }),
  }).catch(() => {})
}
</script>

<template>
  <div class="control">
    <div class="control-head">
      <div class="rail">
        <label class="rail-ctl"><span>Source</span>
          <select :value="source" @change="pick('source', ($event.target as HTMLSelectElement).value)">
            <option v-for="s in sourceList" :key="s.id" :value="s.id">{{ s.label }}</option>
          </select>
        </label>
        <span class="rail-arrow" aria-hidden="true">›</span>
        <label class="rail-ctl" :class="{ off: !source }"><span>Target</span>
          <select :value="effTarget" :disabled="!source" @change="pick('target', ($event.target as HTMLSelectElement).value)">
            <option v-for="t in targetOptions" :key="t.id" :value="t.id" :disabled="t.disabled">{{ t.label }}</option>
          </select>
        </label>
        <template v-if="showSub">
          <span class="rail-arrow" aria-hidden="true">›</span>
          <label class="rail-ctl"><span>Subtarget</span>
            <select :value="effSub" @change="pick('sub', ($event.target as HTMLSelectElement).value)">
              <option v-for="s in subList" :key="s.id" :value="s.id">{{ s.label }}</option>
            </select>
          </label>
        </template>
        <span class="rail-arrow" aria-hidden="true">›</span>
        <label class="rail-ctl" :class="{ off: !source || !visibleMappings.length }"><span>Mapping</span>
          <select :value="effMapping" :disabled="!source || !visibleMappings.length" @change="pick('mapping', ($event.target as HTMLSelectElement).value)">
            <option v-if="!visibleMappings.length" value="">—</option>
            <option v-for="m in visibleMappings" :key="m" :value="m">{{ m }}</option>
          </select>
        </label>
        <button v-if="isLab && source" class="rail-icon" title="Open this source's mapping folder in your disk" @click="openMappingDir">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3 6A1.5 1.5 0 0 1 4.5 4.5H7.5L9 6h3.5A1.5 1.5 0 0 1 14 7.5V9" /><path d="M3 6v8A1.5 1.5 0 0 0 4.5 15.5H8" />
            <circle cx="15.5" cy="15.5" r="4.6" /><circle cx="15.5" cy="15.5" r="1.4" fill="currentColor" stroke="none" />
            <path d="M15.5 9.3v1.6M15.5 20.1v1.6M21.7 15.5h-1.6M10.9 15.5H9.3M19.9 11.1l-1.1 1.1M12.2 18.8l-1.1 1.1M19.9 19.9l-1.1-1.1M12.2 12.2l-1.1-1.1" />
          </svg>
        </button>

        <span v-if="controlError" class="rail-err mono" :title="controlError">{{ controlError }}</span>
      </div>
    </div>

    <div class="control-body">
      <div class="control-stage">
        <RobutekControl v-if="source === 'dreame'"
          :source="source" :target="effTarget" :mapping="effMapping" :target-dev="driveSub"
          :active="active" :nodes="nodes" :name="name || 'dreame'"
          @drive-error="setError" />
        <QuadrantLayout v-else-if="source === 'keyboard'">
          <!-- SW quadrant = output/telemetry. Roomba battery capture when driving a roomba. -->
          <template v-if="roombaIp" #sw>
            <RoombaTelemetry :ip="roombaIp" :active="active" :name="effSub" />
          </template>
          <template #se>
            <ControlKeyboard
              :active="active" :map-source="source" :target="effTarget" :mapping="effMapping"
              :target-dev="driveSub"
              @drive-error="setError" />
          </template>
        </QuadrantLayout>
        <ClaudeControl v-else-if="source === 'claude'"
          :active="active" :nodes="nodes" :map-source="source" :target="effTarget" :mapping="effMapping"
          :target-dev="driveSub"
          @drive-error="setError" />
        <GoogleControl v-else-if="source === 'google'"
          :active="active" :map-source="source" :target="effTarget" :mapping="effMapping"
          :target-dev="driveSub"
          @drive-error="setError" />
        <KinectControl v-else-if="source === 'kinect'"
          :active="active" :nodes="nodes" :target="effTarget" :mapping="effMapping"
          :target-dev="driveSub"
          @drive-error="setError" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.control { display: flex; flex-direction: column; height: 100%; background: var(--surface-2); }
/* The control rail is a TOOLBAR under the global second header (App.vue), not another
   header -- it holds the source/target/mapping pickers + the virtual remote. */
.control-head { background: var(--surface); border-bottom: 1px solid var(--line); flex: 0 0 auto; }

/* responsive rail: wraps on narrow screens (portrait half-screen), stacks to 3 rows */
.rail { display: flex; align-items: center; gap: 10px; padding: 9px 16px; min-height: 58px; flex-wrap: wrap; }
/* drive errors are owned by Control and surfaced here in the shared bar. */
.rail-err { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; color: #c0392b; background: rgba(192, 57, 43, 0.10); border: 1px solid rgba(192, 57, 43, 0.28); border-radius: 6px; padding: 3px 8px; }
.rail-ctl { display: flex; align-items: center; gap: 7px; font-family: var(--font-sans); font-size: 12px; color: var(--text-muted); flex-wrap: nowrap; }
.rail-ctl > span { font-weight: 600; letter-spacing: 0.02em; min-width: fit-content; }
.rail-ctl.off { opacity: 0.5; }
.rail-ctl select { font-family: var(--font-sans); font-size: 12.5px; color: var(--text); background: var(--surface-2); border: 1px solid var(--line); border-radius: 6px; padding: 5px 8px; cursor: pointer; }
.rail-ctl select:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.rail-arrow { color: var(--text-faint); font-size: 14px; flex-shrink: 0; }
/* config icon sits right after Mapping — it opens that mapping's folder. */
.rail-icon { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; color: var(--text-muted); background: transparent; border: 1px solid var(--line); border-radius: 6px; cursor: pointer; transition: color .15s, border-color .15s, background .15s; }
.rail-icon:hover { color: var(--accent); border-color: var(--accent); background: var(--accent-soft); }

/* body = the source stage: Robutek / ControlKeyboard / ClaudeControl. */
.control-body { display: flex; flex: 1 1 auto; min-height: 0; }
.control-stage { flex: 1 1 auto; min-width: 0; min-height: 0; position: relative; }
</style>
