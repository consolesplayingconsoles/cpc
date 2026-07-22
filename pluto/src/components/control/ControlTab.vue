<script setup lang="ts">
// Control surface: parent of the source/target/(subtarget)/mapping rail. Owns the
// selections (all in the URL: /control/{source}/{target}/{mapping}) and renders
// the source child: Dreame Cloud (Robutek), Keyboard only (ControlKeyboard), or Claude
// (ClaudeControl). The on-screen keyboard is the one unified controller across all three.
import { computed, ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { NodeMap } from '../../composables/useNodes'
import ControlBody from './ControlBody.vue'

const props = defineProps<{ active: boolean; nodes?: NodeMap; name?: string; showOffline?: boolean }>()
const route  = useRoute()
const router = useRouter()
const API = `http://${window.location.hostname}:7700`
const isLab = import.meta.env.DEV

// ── HOST — Pluto Lab or Raspberry Pi, from config/control.json. Sources + targets are
// scoped to the picked host and shown in FULL (CPC: no hiding -- the drive API fails
// loudly if a picked one is missing/misconfigured). ──
interface ControlHost { id: string; label: string; sources: string[]; targets: string[] }
const hosts = ref<ControlHost[]>([])
onMounted(async () => {
  try { hosts.value = ((await (await fetch(`${API}/control/config`)).json())?.hosts) || [] }
  catch { hosts.value = [] }
})
// Host is the FIRST url segment (/control/{host}/{source}/{target}/{mapping}), like the
// rest of the selection, so a reload or deep link restores it and the scoped source/
// target lists stay consistent. Default: lab on the dev build, pi elsewhere.
const host = computed(() => (route.params.host as string) || (isLab ? 'lab' : 'pi'))
const curHost = computed(() => hosts.value.find(h => h.id === host.value) || hosts.value[0])
// Picking a host jumps straight to that host's first source (never the empty-source
// state) so the canon fills target/mapping for the new host.
function pickHost(h: string) {
  const first = (hosts.value.find(x => x.id === h)?.sources || [])
    .map(id => ({ id, label: SOURCE_LABELS[id] || id }))
    .sort((a, b) => a.label.localeCompare(b.label))[0]?.id || ''
  router.push(['/control', h, first].filter(Boolean).join('/'))
}

// ── SOURCE — the event producer, scoped to the host (config-driven, shown in full). ──
const SOURCE_LABELS: Record<string, string> = {
  claude: 'Claude', google: 'Google', keyboard: 'Keyboard only',
  dreampicoport: 'DreamPicoPort', kinect: 'Kinect', nokia: 'Nokia Phone', dreame: 'Dreame Cloud',
}
const sourceList = computed(() =>
  (curHost.value?.sources || [])
    .map(id => ({ id, label: SOURCE_LABELS[id] || id }))
    .sort((a, b) => a.label.localeCompare(b.label)))
const source = computed(() => (route.params.source as string) || '')

// ── TARGET — a FLAT output: the emulator, a specific Pico, or a specific roomba. No
// subtarget: each option carries the drive SINK it maps to (keyboard / pi / roomba) and
// its `dev` (the pico's UART dev, or the roomba node id). The label is what the device
// is/pretends to be -- a ps3 HID pico -> "Ps3 HID Pico", a roomba node -> its name. ──
interface FlatTarget {
  id: string
  label: string
  drive: 'none' | 'keyboard' | 'pi' | 'roomba' | 'megadrive'   // the sink the drive service opens
  dev: string                                     // pico dev (pi) | roomba node id (roomba)
  kind: 'none' | 'emulator' | 'console' | 'roomba'
  ip?: string                                     // roomba: host:port, for the telemetry panel
}
const roombaNodes = computed(() =>
  Object.values(props.nodes || {})
    .filter(n => n.controlTarget === 'roomba' && (n.status !== 'unconfigured' || props.showOffline)))

function picoLabel(p: { iface?: string; role?: string; alias?: string; chipid: string }): string {
  const iface = (p.iface || '').trim()
  if (iface && /hid/i.test(p.role || ''))          // "ps3" + Remote HID -> "PS3 HID Pico"
    return iface.charAt(0).toUpperCase() + iface.slice(1) + ' HID Pico'
  return p.alias || p.chipid
}
const targetOptions = computed<FlatTarget[]>(() => {
  // 'none' is client-side (maps to nothing), never in config. The rest expand from the
  // host's config targets: a category id -> the concrete FlatTarget(s) it resolves to.
  const out: FlatTarget[] = [{ id: 'none', label: 'No output', drive: 'none', dev: '', kind: 'none' }]
  const picos = ((props.nodes?.['pi'] as any)?.picos as Array<{ chipid: string; alias?: string; iface?: string; role?: string; dev?: string; conn?: string }> | undefined) || []
  for (const cat of (curHost.value?.targets || [])) {
    if (cat === 'emulator') {
      out.push({ id: 'emulator', label: 'Emulator', drive: 'keyboard', dev: '', kind: 'emulator' })
    } else if (cat === 'hid') {
      for (const p of picos)
        if ((p.conn || '').toLowerCase() === 'uart' && p.dev && /hid/i.test(p.role || ''))
          out.push({ id: p.alias || p.chipid, label: picoLabel(p), drive: 'pi', dev: p.dev, kind: 'console' })
    } else if (cat === 'roomba') {
      for (const n of roombaNodes.value)
        out.push({ id: n.id, label: n.name, drive: 'roomba', dev: n.id, kind: 'roomba', ip: n.ip })
    } else if (cat === 'megadrive') {
      // MD as a CONTROLLER target: the selected source's quadrant layout drives it via the
      // SE ControlKeyboard, same as any pad. The 'megadrive' drive sink (drive service ->
      // hub -> genesis pico controller mode) is the pending producer; until it lands, driving
      // it 404s like any unimplemented sink (show everything, let the API fail). Text is NOT
      // here -- that's the chat verb '@megadrive text'.
      out.push({ id: 'megadrive', label: 'Mega Drive', drive: 'megadrive', dev: '', kind: 'console' })
    }
  }
  return out
})
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

function path(s: string, t: string, m: string) {
  return ['/control', host.value, s, t, m].filter((x, i) => i === 0 || x).join('/')
}
// Each picker keeps the OTHER dimensions populated in the URL by pushing the resolved
// (effective) values, never the raw param -- otherwise changing the target drops the
// mapping from the path even though the dropdown still shows it.
function pick(level: 'source' | 'target' | 'mapping', v: string) {
  if (level === 'source')  router.push(path(v, '', ''))                                 // new source resets the rest (canon refills)
  else if (level === 'target')  router.push(path(source.value, v, effMapping.value))
  else router.push(path(source.value, effTarget.value, v))
}

// The selected flat target -> the first real output when the URL has none.
const effTarget = computed(() => target.value || (targetOptions.value.find(t => t.id !== 'none')?.id || 'none'))
const curTarget = computed<FlatTarget>(() => targetOptions.value.find(t => t.id === effTarget.value) || targetOptions.value[0])
// The mapping must MATCH the target's sink: a roomba mapping carries `actions` (button
// -> roomba verb) only the roomba sink understands; console mappings drive a pad and have
// no actions. So the dropdown only offers mappings compatible with the target KIND:
// roomba schemes for a roomba, console schemes everywhere else.
function isRoombaMapping(m: string) { return m === 'roomba' || m.startsWith('roomba-') }
const visibleMappings = computed(() =>
  curTarget.value.kind === 'roomba'
    ? mappings.value.filter(isRoombaMapping)
    : mappings.value.filter(m => !isRoombaMapping(m)))
const effMapping = computed(() =>
  (mapping.value && visibleMappings.value.includes(mapping.value)) ? mapping.value : (visibleMappings.value[0] || ''))

// Drive params derived from the flat target (subtarget gone): the sink, its dev (the
// pico's UART dev under pi / the roomba node id under roomba), and the roomba host:port
// for the telemetry panel.
const driveTarget = computed(() => curTarget.value.drive)
const driveDev = computed(() => curTarget.value.dev)
const roombaIp = computed(() => curTarget.value.kind === 'roomba' ? (curTarget.value.ip || '') : '')

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

watch([source, target, mapping, mappings, targetOptions, sourceList, host, () => props.active], () => {
  if (!props.active) return
  // Bad host segment (an old link, or none): once the roster's loaded, snap to the default
  // host so the URL always names a real host (the canon re-runs and fills the source).
  if (hosts.value.length && !hosts.value.some(h => h.id === host.value)) {
    const def = isLab ? 'lab' : 'pi'
    const dh = hosts.value.some(h => h.id === def) ? def : hosts.value[0].id
    router.replace(['/control', dh].join('/')); return
  }
  // Host changed / stale deep link: if the current source isn't in this host's list,
  // fall back to the host's first source.
  if (source.value && sourceList.value.length && !sourceList.value.some(s => s.id === source.value)) {
    router.replace(path(sourceList.value[0].id, '', '')); return
  }
  if (!source.value) {
    const last = localStorage.getItem(LAST_URL_KEY)
    const lastHost = last?.split('/')[2]   // /control/<host>/<source>/...
    if (last && last.startsWith('/control/') && last !== route.fullPath
        && hosts.value.some(h => h.id === lastHost)) { router.replace(last); return }
    if (sourceList.value.length) router.replace(path(sourceList.value[0].id, '', ''))
    return
  }
  // Claude is Lab-only (capture is local to the dev host). A deep link to /control/claude
  // on the C2 must not render it -> fall back to the first available source.
  if ((source.value === 'claude' || source.value === 'google') && !isLab) {
    router.replace(path(sourceList.value[0]?.id || 'keyboard', '', ''))
    return
  }
  const t = effTarget.value
  const m = effMapping.value
  if (t !== target.value || (m && m !== mapping.value)) router.replace(path(source.value, t, m))
  else if (m) localStorage.setItem(LAST_URL_KEY, route.fullPath)   // canon settled: remember it (incl ?host=)
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
        <label class="rail-ctl"><span>Host</span>
          <select :value="host" @change="pickHost(($event.target as HTMLSelectElement).value)">
            <option v-for="h in hosts" :key="h.id" :value="h.id">{{ h.label }}</option>
          </select>
        </label>
        <span class="rail-arrow" aria-hidden="true">›</span>
        <label class="rail-ctl"><span>Source</span>
          <select :value="source" @change="pick('source', ($event.target as HTMLSelectElement).value)">
            <option v-for="s in sourceList" :key="s.id" :value="s.id">{{ s.label }}</option>
          </select>
        </label>
        <span class="rail-arrow" aria-hidden="true">›</span>
        <label class="rail-ctl" :class="{ off: !source }"><span>Target</span>
          <select :value="effTarget" :disabled="!source" @change="pick('target', ($event.target as HTMLSelectElement).value)">
            <option v-for="t in targetOptions" :key="t.id" :value="t.id">{{ t.label }}</option>
          </select>
        </label>
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
        <ControlBody
          :active="active" :source="source" :target="driveTarget" :mapping="effMapping"
          :target-dev="driveDev" :roomba-ip="roombaIp" :nodes="nodes" :name="name"
          :show-offline="showOffline"
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
