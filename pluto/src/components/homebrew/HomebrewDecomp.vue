<script setup lang="ts">
// A decomp's (or disassembly's) progress, in the Decomp / Disasm tab: what the project's
// tools/progress.py prints. The item names itself as its decomp, and GET /homebrew/decomp
// answers with that printout, cached by the API until the decomp's commit changes. The printout has one layout across projects (a heading per section,
// then rows of label, percentage or "-", detail), so it is drawn as a table with a bar on each
// percentage. The text is parsed here and anything that does not fit the layout falls back to the
// printout exactly as printed, in a monospace block: a changed progress.py degrades, never breaks.
import { computed, ref, watch } from 'vue'
import { getDecomp, type HomebrewDecomp, type HomebrewItem } from '../../api/homebrew'
import UiButton from '../ui/UiButton.vue'
import UiState from '../ui/UiState.vue'
import { mainMetric } from './decompMetric'

const props = defineProps<{ item: HomebrewItem }>()

// the decomp is the item's sibling: its folder's parent + the name in config.json
const path = computed(() => props.item.decomp ? props.item.path.replace(/\/[^/]+$/, '/') + props.item.decomp : null)

const levels = ref<HomebrewDecomp | null>(null)
const failed = ref('')
const loading = ref(false)
const cache = new Map<string, HomebrewDecomp>()        // switching items back and forth asks once

async function load(refresh = false) {
  const p = path.value
  if (!p) { levels.value = null; return }
  if (!refresh && cache.has(p)) { levels.value = cache.get(p)!; failed.value = ''; return }
  loading.value = true; failed.value = ''
  try {
    const r = await getDecomp(p, refresh)
    cache.set(p, r)
    if (p === path.value) levels.value = r               // the pick may have moved on meanwhile
  } catch (e) {
    if (p === path.value) { levels.value = null; failed.value = (e as Error).message }
  } finally {
    if (p === path.value) loading.value = false
  }
}
watch(path, () => { levels.value = null; load() }, { immediate: true })

// ── the printout as a table ──────────────────────────────────────────────────
interface Row { level: number; label: string; pct: string; detail: string }
interface Section { title: string; detail: string; rows: Row[] }
function parseProgress(text: string): Section[] | null {
  const sections: Section[] = []
  for (const line of text.split('\n')) {
    if (!line.trim()) continue
    const indent = line.length - line.trimStart().length
    if (indent === 0) {
      const [title, ...rest] = line.split(/\s{2,}/)
      sections.push({ title, detail: rest.join('  '), rows: [] })
      continue
    }
    const cur = sections[sections.length - 1]
    if (!cur) return null                              // a row before any heading: not the layout we know
    const m = /^(.+?)(?:\s{2,}(\d+(?:\.\d+)?%|-))?(?:\s{2,}(.*))?$/.exec(line.trim())
    if (!m) return null
    cur.rows.push({ level: Math.max(0, Math.floor((indent - 2) / 2)), label: m[1], pct: m[2] ?? '', detail: m[3] ?? '' })
  }
  return sections.length && sections.some(sec => sec.rows.length) ? sections : null
}
const table = computed(() => levels.value?.progress ? parseProgress(levels.value.progress) : null)
const width = (pct: string) => Math.min(100, parseFloat(pct)) + '%'
// the main metric's row is bold, the same number the list shows in its pill
const main = computed(() => levels.value?.progress ? mainMetric(levels.value.progress) : null)
const isMain = (r: Row) => !!main.value && r.label === main.value.label && r.pct === main.value.pct

const stamp = (s: number) => new Date(s * 1000).toLocaleString('sv-SE').slice(0, 16)   // 2026-10-12 23:09
</script>

<template>
  <section v-if="item.decomp" class="hbd">
    <div class="hbd__head">
      <h3 class="hbd__title">Decomp</h3>
      <code class="hbd__name">{{ item.decomp }}</code>
      <span v-if="levels?.commit" class="hbd__hint" title="Commit the progress was read at">{{ levels.commit.slice(0, 8) }}</span>
      <span v-if="levels?.updated" class="hbd__hint">read {{ stamp(levels.updated) }}</span>
      <UiButton
        v-if="levels?.progress" class="hbd__refresh" variant="secondary" :loading="loading" loading-text="Reading"
        title="Run progress.py again (skips the cache)" @click="load(true)"
      >Refresh</UiButton>
    </div>

    <UiState v-if="loading && !levels" loading>Reading progress…</UiState>
    <UiState v-else-if="failed" tone="bad">{{ failed }}</UiState>
    <UiState v-else-if="levels?.error" tone="bad">{{ levels.error }}</UiState>
    <div v-else-if="table" class="hbd__sections">
      <div v-for="sec in table" :key="sec.title" class="hbd__sec">
        <div class="hbd__sec-head">
          <span class="hbd__sec-title">{{ sec.title }}</span>
          <span v-if="sec.detail" class="hbd__sec-detail">{{ sec.detail }}</span>
        </div>
        <div v-for="(r, n) in sec.rows" :key="n" class="hbd__row" :class="{ 'is-main': isMain(r) }" :title="isMain(r) ? 'Main metric: 100% when complete' : undefined">
          <span class="hbd__label" :style="{ paddingLeft: r.level * 14 + 'px' }">{{ r.label }}</span>
          <span class="hbd__pct">
            <template v-if="r.pct.endsWith('%')">
              <span class="hbd__bar"><span class="hbd__fill" :style="{ width: width(r.pct) }" /></span>
              <span class="hbd__num">{{ r.pct }}</span>
            </template>
            <span v-else-if="r.pct" class="hbd__num hbd__num--none">{{ r.pct }}</span>
          </span>
          <span class="hbd__detail">{{ r.detail }}</span>
        </div>
      </div>
    </div>
    <!-- a layout this does not know: the printout exactly as printed -->
    <pre v-else-if="levels?.progress" class="hbd__raw">{{ levels.progress }}</pre>
    <!-- a disassembly has no progress.py: say what it is built on and stop there -->
    <p v-else-if="levels" class="hbd__none">No progress report: tools/progress.py not found.</p>
  </section>
</template>

<style scoped>
/* the same card as the Parameters block below the header: one family of surfaces */
.hbd { margin-top: var(--sp-4); padding: var(--sp-4); background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-lg); box-shadow: var(--shadow-sm); }
.hbd__head { display: flex; align-items: baseline; flex-wrap: wrap; gap: var(--sp-3); margin-bottom: var(--sp-3); }
.hbd__title { margin: 0; font-size: 13px; font-weight: 600; }
.hbd__name { font-family: var(--font-mono); font-size: 11.5px; color: var(--text-faint); }
.hbd__hint { font-family: var(--font-mono); font-size: 11.5px; color: var(--text-faint); }
.hbd__refresh { margin-left: auto; align-self: center; }
/* the table: a heading per section, then label | bar and percentage | detail */
.hbd__sections { display: flex; flex-direction: column; gap: var(--sp-4); }
.hbd__sec-head { display: flex; align-items: baseline; flex-wrap: wrap; gap: var(--sp-3); padding: 0 var(--sp-2) var(--sp-1); margin-bottom: 2px; border-bottom: 1px solid var(--line); }
.hbd__sec-title { font-size: 12px; font-weight: 600; letter-spacing: 0.02em; }
.hbd__sec-detail { font-size: 12px; color: var(--text-muted); }
.hbd__row { display: grid; grid-template-columns: minmax(150px, 240px) 150px minmax(0, 1fr); align-items: center; column-gap: var(--sp-3); padding: 5px var(--sp-2); border-radius: var(--r-sm); font-size: 12.5px; }
/* every other row is tinted, so the eye can stay on one line across the three columns; the
   heading is the first child of its section, which makes the odd children the second, fourth... row */
.hbd__row:nth-child(odd) { background: var(--surface-2); }
.hbd__label { color: var(--text); }
.hbd__row.is-main .hbd__label, .hbd__row.is-main .hbd__num { font-weight: 700; }
.hbd__pct { display: flex; align-items: center; gap: var(--sp-2); }
/* the number is always printed: the bar is a glance, never the only carrier of the value */
.hbd__bar { flex: 1 1 auto; height: 4px; border-radius: 2px; background: var(--surface-3); overflow: hidden; }
.hbd__fill { display: block; height: 100%; background: var(--accent); }
.hbd__num { flex: none; min-width: 44px; text-align: right; font-family: var(--font-mono); font-size: 12px; }
.hbd__num--none { color: var(--text-faint); }
.hbd__detail { min-width: 0; color: var(--text-muted); }
@media (max-width: 640px) {
  .hbd__row { grid-template-columns: 1fr auto; row-gap: 2px; }
  .hbd__pct { width: 130px; }
  .hbd__detail { grid-column: 1 / -1; }
}
/* the fallback: fixed-width columns shown as printed, scrolling sideways instead of wrapping */
.hbd__raw { margin: 0; padding: var(--sp-3); overflow-x: auto; font-family: var(--font-mono); font-size: 12px; line-height: 1.6; color: var(--text); background: var(--surface-2); border: 1px solid var(--line); border-radius: var(--r); white-space: pre; }
.hbd__none { margin: 0; font-size: 12.5px; color: var(--text-muted); }
</style>
