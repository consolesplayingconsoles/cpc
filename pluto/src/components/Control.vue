<script setup lang="ts">
// Control surface: parent of the source/target/(subtarget)/mapping rail. Owns the
// selections (all in the URL: /control/{source}/{target}/{mapping}[/{pico}]) and renders
// the source child: Dreame Cloud (Robutek), Keyboard only (ControlKeyboard), or Claude
// (ClaudeControl). The on-screen keyboard is the one unified controller across all three.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { NodeMap } from '../composables/useNodes'
import Robutek from './Robutek.vue'
import ControlKeyboard from './ControlKeyboard.vue'
import ClaudeControl from './ClaudeControl.vue'
import GoogleLensControl from './GoogleLensControl.vue'

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
  return out
})
const source = computed(() => (route.params.source as string) || '')

// ── TARGET — output sink (nothing / emulator / pi), NOT the console itself. ──
const piPresent = computed(() => {
  const n = props.nodes?.['pi']
  return !!n && n.status !== 'unconfigured'
})
const targetOptions = computed(() => [
  { id: 'none', label: 'No output', disabled: false },
  ...(isLab ? [{ id: 'keyboard', label: 'Emulator (virtual keyboard)', disabled: false }] : []),
  { id: 'pi', label: 'Console (Raspberry Pi)', disabled: !piPresent.value },
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

function path(s: string, t: string, m: string, p = '') {
  const segs = ['/control', s, t, m]
  if (t === 'pi' && m && p) segs.push(p)   // pico = 4th positional param, only under target=pi (and needs mapping filled, since positional)
  return segs.filter((x, i) => i === 0 || x).join('/')
}
// Each picker keeps the OTHER two dimensions populated in the URL by pushing the
// resolved (effective) values, never the raw param -- otherwise changing the target
// drops the mapping from the path even though the dropdown still shows it.
function pick(level: 'source' | 'target' | 'mapping' | 'pico', v: string) {
  if (level === 'source')  router.push(path(v, '', '', ''))                                          // new source resets the rest (canon refills)
  else if (level === 'target')  router.push(path(source.value, v, effMapping.value, effPico.value))  // canon fills pico when v becomes pi
  else if (level === 'mapping') router.push(path(source.value, effTarget.value, v, effPico.value))
  else                          router.push(path(source.value, effTarget.value, effMapping.value, v)) // pico
}

const effTarget  = computed(() => target.value || defaultTarget.value)
// Only honour the URL's mapping if it's valid for THIS source's list; otherwise fall
// back to the first available. Kills the stale/invalid mapping that rendered blank.
const effMapping = computed(() =>
  (mapping.value && mappings.value.includes(mapping.value)) ? mapping.value : (mappings.value[0] || ''))

// ── PICO — shows ONLY when target === 'pi': which of the node's UART picos to drive.
// A 4th URL param appended AFTER mapping (the first three never move). Options are the
// pi node's declared picos, labelled by the alias earned off the wires; the resolved
// `dev` (ttyAMA4 / ttyAMA0) is what the drive actually routes on. ──
const picoList = computed(() => {
  const list = ((props.nodes?.['pi'] as any)?.picos as Array<{ chipid: string; alias?: string; dev?: string; conn?: string }> | undefined) || []
  return list.filter(p => (p.conn || '').toLowerCase() === 'uart' && p.dev)
             .map(p => ({ id: p.alias || p.chipid, label: p.alias || p.chipid, dev: p.dev as string }))
})
const pico     = computed(() => (route.params.pico as string) || '')
const showPico = computed(() => effTarget.value === 'pi' && picoList.value.length > 0)
const effPico  = computed(() => {
  if (!showPico.value) return ''
  const ids = picoList.value.map(p => p.id)
  return (pico.value && ids.includes(pico.value)) ? pico.value : (ids[0] || '')
})
const picoDev  = computed(() => picoList.value.find(p => p.id === effPico.value)?.dev || '')

// URL-canonicalization: write the resolved defaults INTO the url so the dropdowns and
// the path never disagree. replace() = no history entry. With no source in the path
// (bare /control), land on the first available source; only an empty roster leaves
// the pick-a-source state. Then fill target + mapping defaults.
watch([source, target, mapping, pico, mappings, picoList, sourceList, () => props.active], () => {
  if (!props.active) return
  if (!source.value) {
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
  const p = effPico.value   // '' unless target==='pi' with picos available
  // pico canon: under pi, the resolved pico must be in the URL; off pi, no pico segment may linger.
  const picoMismatch = (t === 'pi') ? (!!p && p !== pico.value) : (pico.value !== '')
  if (t !== target.value || (m && m !== mapping.value) || picoMismatch) router.replace(path(source.value, t, m, p))
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
        <template v-if="showPico">
          <span class="rail-arrow" aria-hidden="true">›</span>
          <label class="rail-ctl"><span>Subtarget</span>
            <select :value="effPico" @change="pick('pico', ($event.target as HTMLSelectElement).value)">
              <option v-for="pc in picoList" :key="pc.id" :value="pc.id">{{ pc.label }}</option>
            </select>
          </label>
        </template>
        <span class="rail-arrow" aria-hidden="true">›</span>
        <label class="rail-ctl" :class="{ off: !source || !mappings.length }"><span>Mapping</span>
          <select :value="effMapping" :disabled="!source || !mappings.length" @change="pick('mapping', ($event.target as HTMLSelectElement).value)">
            <option v-if="!mappings.length" value="">—</option>
            <option v-for="m in mappings" :key="m" :value="m">{{ m }}</option>
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
        <Robutek v-if="source === 'dreame'"
          :source="source" :target="effTarget" :mapping="effMapping" :target-dev="effTarget === 'pi' ? picoDev : ''"
          :active="active" :nodes="nodes" :name="name || 'dreame'"
          @drive-error="setError" />
        <ControlKeyboard v-else-if="source === 'keyboard'"
          :active="active" :map-source="source" :target="effTarget" :mapping="effMapping"
          :target-dev="effTarget === 'pi' ? picoDev : ''"
          @drive-error="setError" />
        <ClaudeControl v-else-if="source === 'claude'"
          :active="active" :nodes="nodes" :map-source="source" :target="effTarget" :mapping="effMapping"
          :target-dev="effTarget === 'pi' ? picoDev : ''"
          @drive-error="setError" />
        <GoogleLensControl v-else-if="source === 'google'"
          :active="active" :map-source="source" :target="effTarget" :mapping="effMapping"
          :target-dev="effTarget === 'pi' ? picoDev : ''"
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
