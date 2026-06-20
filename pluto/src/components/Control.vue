<script setup lang="ts">
// Control surface: parent of the source/target/mapping rail + a virtual remote down
// the right side. Owns the three selections (all in the URL:
// /control/{source}/{target}/{mapping}) and renders the source-specific child. Today
// the only source is Dreame Cloud (Robutek); the rail is the seam for a keyboard source.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { NodeMap } from '../composables/useNodes'
import Robutek from './Robutek.vue'

const props = defineProps<{ active: boolean; nodes?: NodeMap; name?: string; showOffline?: boolean }>()
const route  = useRoute()
const router = useRouter()
const API = `http://${window.location.hostname}:7700`
const isLab = import.meta.env.DEV

// ── SOURCE — configured producers appear; an unconfigured one (no .env) is hidden
// unless "Show unconfigured nodes" is on, matching the map/member-list behaviour. ──
const sourceList = computed(() => {
  const out: { id: string; label: string }[] = []
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
  { id: 'none', label: 'Nothing (map only)', disabled: false },
  ...(isLab ? [{ id: 'keyboard', label: 'Emulator (virtual keyboard)', disabled: false }] : []),
  { id: 'pi', label: 'Console (Raspberry Pi)', disabled: !piPresent.value },
])
const defaultTarget = computed(() => (piPresent.value ? 'pi' : isLab ? 'keyboard' : 'none'))
const target = computed(() => (route.params.target as string) || '')

// ── MAPPING — control scheme for the source (from the API). ──
const mappings = ref<string[]>([])
const mapping  = computed(() => (route.params.mapping as string) || '')
async function fetchMappings(src: string) {
  if (!src) { mappings.value = []; return }
  try {
    const r = await fetch(`${API}/mappings/${src}`)
    const j = await r.json().catch(() => null)
    mappings.value = (j && Array.isArray(j.targets)) ? j.targets : []
  } catch { mappings.value = [] }
}
watch(source, (s) => fetchMappings(s), { immediate: true })

function path(s: string, t: string, m: string) {
  return ['/control', s, t, m].filter((x, i) => i === 0 || x).join('/')
}
function pick(level: 'source' | 'target' | 'mapping', v: string) {
  if (level === 'source')  router.push(path(v, '', ''))            // new source resets t + m
  else if (level === 'target')  router.push(path(source.value, v, mapping.value))
  else                           router.push(path(source.value, target.value, v))
}

const effTarget  = computed(() => target.value || defaultTarget.value)
const effMapping = computed(() => mapping.value || mappings.value[0] || '')

// URL-canonicalization: write the resolved defaults INTO the url so the dropdowns and
// the path never disagree. replace() = no history entry. With no source in the path
// (bare /control), land on the first available source; only an empty roster leaves
// the pick-a-source state. Then fill target + mapping defaults.
watch([source, target, mapping, mappings, sourceList, () => props.active], () => {
  if (!props.active) return
  if (!source.value) {
    if (sourceList.value.length) router.replace(path(sourceList.value[0].id, '', ''))
    return
  }
  const t = target.value || defaultTarget.value
  const m = mapping.value || mappings.value[0] || ''
  if (t !== target.value || (m && m !== mapping.value)) router.replace(path(source.value, t, m))
}, { immediate: true })

// ── virtual remote: one-off button presses to the current target. Useful while a game
// is PAUSED (the route only steers) -- navigate a menu, hit Start/Action by hand. Reuses
// the backend `press` action; disabled when target = nothing (no output). ──
const canPress = computed(() => !!source.value && effTarget.value !== 'none')

// Control OWNS the drive-error surface: the Robutek child reports up via @drive-error,
// and the remote's own presses report here too -- all shown in the shared control bar
// rather than buried in a source. Auto-clears so a transient failure doesn't linger.
const controlError = ref('')
let errTimer = 0
function setError(msg: string) {
  controlError.value = msg
  if (errTimer) { clearTimeout(errTimer); errTimer = 0 }
  if (msg) errTimer = window.setTimeout(() => { controlError.value = '' }, 5000)
}

// `p` is {btn} for universal buttons (d-pad, START) or {key} for semantic ones
// (action/cancel) that the BACKEND resolves to the mapped console's main/secondary
// via the mapping's `controls` -- that's why the labels are generic, not "A"/"B".
async function press(p: { btn?: string; key?: string }) {
  if (!canPress.value) return
  try {
    const r = await fetch(`${API}/robutek/drive`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'press', target: effTarget.value, source: source.value, mapping: effMapping.value, ...p }),
    })
    const j = await r.json().catch(() => null)
    setError(j && j.ok === false ? (j.error || 'press failed') : '')
  } catch { setError('API unreachable') }
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
            <option value="" disabled>Pick a source…</option>
            <option v-for="s in sourceList" :key="s.id" :value="s.id">{{ s.label }}</option>
          </select>
        </label>
        <span class="rail-arrow" aria-hidden="true">›</span>
        <label class="rail-ctl" :class="{ off: !source }"><span>Target</span>
          <select :value="effTarget" :disabled="!source" @change="pick('target', ($event.target as HTMLSelectElement).value)">
            <option v-for="t in targetOptions" :key="t.id" :value="t.id" :disabled="t.disabled">{{ t.label }}</option>
          </select>
        </label>
        <span class="rail-arrow" aria-hidden="true">›</span>
        <label class="rail-ctl" :class="{ off: !source || !mappings.length }"><span>Mapping</span>
          <select :value="effMapping" :disabled="!source || !mappings.length" @change="pick('mapping', ($event.target as HTMLSelectElement).value)">
            <option v-if="!mappings.length" value="">—</option>
            <option v-for="m in mappings" :key="m" :value="m">{{ m }}</option>
          </select>
        </label>
        <button v-if="isLab && source" class="rail-icon" title="Open this source's mapping folder in your IDE" @click="openMappingDir">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3 6A1.5 1.5 0 0 1 4.5 4.5H7.5L9 6h3.5A1.5 1.5 0 0 1 14 7.5V9" /><path d="M3 6v8A1.5 1.5 0 0 0 4.5 15.5H8" />
            <circle cx="15.5" cy="15.5" r="4.6" /><circle cx="15.5" cy="15.5" r="1.4" fill="currentColor" stroke="none" />
            <path d="M15.5 9.3v1.6M15.5 20.1v1.6M21.7 15.5h-1.6M10.9 15.5H9.3M19.9 11.1l-1.1 1.1M12.2 18.8l-1.1 1.1M19.9 19.9l-1.1-1.1M12.2 12.2l-1.1-1.1" />
          </svg>
        </button>

        <span v-if="controlError" class="rail-err mono" :title="controlError">{{ controlError }}</span>

        <!-- virtual remote: right-aligned IN the control row (margin-left:auto),
             controller-shaped: D-pad | Start | Action/Cancel. Hand-driven for when
             the route is paused (it only steers). Sent to the current target;
             disabled when target = Nothing. -->
        <div class="remote" :class="{ off: !canPress }">
          <div class="dpad">
            <button class="pad-btn up"    :disabled="!canPress" @click="press({ btn: 'D_UP' })"    aria-label="D-pad up">▲</button>
            <button class="pad-btn left"  :disabled="!canPress" @click="press({ btn: 'D_LEFT' })"  aria-label="D-pad left">◀</button>
            <button class="pad-btn right" :disabled="!canPress" @click="press({ btn: 'D_RIGHT' })" aria-label="D-pad right">▶</button>
            <button class="pad-btn down"  :disabled="!canPress" @click="press({ btn: 'D_DOWN' })"  aria-label="D-pad down">▼</button>
          </div>
          <button class="rmt-start" :disabled="!canPress" @click="press({ btn: 'START' })" title="Start (also the Enter hotkey)">Start</button>
          <div class="faces">
            <button class="rmt-face" :disabled="!canPress" @click="press({ key: 'action' })" title="Main action — the mapped console's primary button">Action</button>
            <button class="rmt-face" :disabled="!canPress" @click="press({ key: 'cancel' })" title="Back / cancel — the mapped console's secondary button">Cancel</button>
          </div>
        </div>
      </div>
    </div>

    <div class="control-body">
      <div class="control-stage">
        <Robutek v-if="source === 'dreame'"
          :source="source" :target="effTarget" :mapping="effMapping"
          :active="active" :nodes="nodes" :name="name || 'dreame'"
          @drive-error="setError" />
        <div v-else class="control-empty">Pick a source to begin.</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.control { display: flex; flex-direction: column; height: 100%; background: var(--surface-2); }
/* The control rail is a TOOLBAR under the global second header (App.vue), not another
   header -- it holds the source/target/mapping pickers + the virtual remote. */
.control-head { background: var(--surface); border-bottom: 1px solid var(--line); flex: 0 0 auto; }

.rail { display: flex; align-items: center; gap: 10px; padding: 9px 20px; min-height: 58px; }
/* drive errors are owned by Control and surfaced here in the shared bar. */
.rail-err { flex: 0 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; color: #c0392b; background: rgba(192, 57, 43, 0.10); border: 1px solid rgba(192, 57, 43, 0.28); border-radius: 6px; padding: 3px 8px; }
.rail-ctl { display: flex; align-items: center; gap: 7px; font-family: var(--font-sans); font-size: 12px; color: var(--text-muted); }
.rail-ctl > span { font-weight: 600; letter-spacing: 0.02em; }
.rail-ctl.off { opacity: 0.5; }
.rail-ctl select { font-family: var(--font-sans); font-size: 12.5px; color: var(--text); background: var(--surface-2); border: 1px solid var(--line); border-radius: 6px; padding: 5px 8px; cursor: pointer; }
.rail-ctl select:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.rail-arrow { color: var(--text-faint); font-size: 14px; }
/* config icon sits right after Mapping — it opens that mapping's folder. */
.rail-icon { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; color: var(--text-muted); background: transparent; border: 1px solid var(--line); border-radius: 6px; cursor: pointer; transition: color .15s, border-color .15s, background .15s; }
.rail-icon:hover { color: var(--accent); border-color: var(--accent); background: var(--accent-soft); }

/* body = the source stage (Robutek); the remote rides up in the control row above. */
.control-body { display: flex; flex: 1 1 auto; min-height: 0; }
.control-stage { flex: 1 1 auto; min-width: 0; position: relative; }
.control-empty { display: grid; place-items: center; height: 100%; color: var(--text-muted); font-family: var(--font-sans); }

/* virtual remote: a controller-shaped cluster (D-pad | Start | Action/Cancel),
   right-aligned in the control row via margin-left:auto. */
.remote { margin-left: auto; display: flex; align-items: center; gap: 12px; }
.remote.off { opacity: 0.5; }
.dpad { display: grid; grid-template-columns: repeat(3, 24px); grid-template-rows: repeat(3, 24px); gap: 3px; }
.pad-btn { display: inline-flex; align-items: center; justify-content: center; font-size: 10px; color: var(--text); background: var(--surface-2); border: 1px solid var(--line); border-radius: 6px; cursor: pointer; padding: 0; }
.pad-btn.up { grid-column: 2; grid-row: 1; } .pad-btn.left { grid-column: 1; grid-row: 2; }
.pad-btn.right { grid-column: 3; grid-row: 2; } .pad-btn.down { grid-column: 2; grid-row: 3; }
.rmt-start { min-width: 48px; font-family: var(--font-sans); font-size: 11px; font-weight: 600; letter-spacing: 0.02em; color: var(--text); background: var(--surface-2); border: 1px solid var(--line); border-radius: 7px; padding: 7px 12px; cursor: pointer; }
.faces { display: flex; flex-direction: column; gap: 5px; }
.rmt-face { min-width: 76px; font-family: var(--font-sans); font-size: 11.5px; font-weight: 600; color: var(--text); background: var(--surface-2); border: 1px solid var(--line); border-radius: 7px; padding: 6px 0; cursor: pointer; }
.pad-btn:hover:not(:disabled), .rmt-start:hover:not(:disabled), .rmt-face:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.pad-btn:active:not(:disabled), .rmt-start:active:not(:disabled), .rmt-face:active:not(:disabled) { background: var(--accent-soft); }
.pad-btn:disabled, .rmt-start:disabled, .rmt-face:disabled { cursor: default; opacity: 0.4; }
</style>
