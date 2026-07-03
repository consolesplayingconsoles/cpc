<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { API_BASE } from '../composables/useNodes'
import { useAchievement } from '../composables/useAchievement'
import UiSelect from './ui/UiSelect.vue'
import UiButton from './ui/UiButton.vue'
import UiIconButton from './ui/UiIconButton.vue'
import UiClose from './ui/UiClose.vue'
import UiSpinner from './ui/UiSpinner.vue'
import MetadataCard from './MetadataCard.vue'
import type { GameMeta } from './MetadataCard.vue'
import SpeakerLegend from './SpeakerLegend.vue'
import PromptCopier from './PromptCopier.vue'
import TranslationRow from './TranslationRow.vue'
import { type Block, caBytes } from '../lib/translation'
import { formatOffset, buildSourcesPayload, reconcileByOffset, mergePolledCa } from './TranslationTable.logic'
import { translationApi } from '../api/translation'
import { LANGUAGES } from '../lib/languages'

const route  = useRoute()
const router = useRouter()

// Experimental disclaimer: dismissible for the session (sessionStorage).
const disclaimerDismissed = ref(sessionStorage.getItem('cpc.translate.disclaimer') === '1')
function dismissDisclaimer() {
  disclaimerDismissed.value = true
  sessionStorage.setItem('cpc.translate.disclaimer', '1')
}

// Rows for the ACTIVE tab. Empty until a project/tab loads from the API — this generic workbench
// carries no game content (the old hardcoded Boku Doraemon demo lines lived here; gone now).
const blocks = ref<Block[]>([])

const SPEAKER_COLORS: Record<number, string> = {
  1: '#5b8dd9',
  9: '#c87053',
  2: '#7c9e6e',
  7: '#9b7db8',
}

function speakerColor(id: number) {
  if (SPEAKER_COLORS[id]) return SPEAKER_COLORS[id]
  if (id === 0) return '#8a8a8a'                          // untagged / narration
  return `hsl(${(id * 67) % 360}, 42%, 58%)`              // stable, distinct-ish for the rest
}

function byteStatus(block: Block): 'pending' | 'ok' | 'warn' | 'over' {
  const used = caBytes(block.ca)
  if (used === 0) return block.done ? 'ok' : 'pending'   // "done" = handled / keep-as-original
  const budget = block.jpBytes
  if (used <= budget) return 'ok'
  if (used <= budget * 1.3) return 'warn'
  return 'over'
}

// ── Box (scenario) budget — the PRIMARY fit signal; per-line bytes stay as detail ───────────
// The engine holds each scene in a fixed box with a little spare room (slack, from extraction).
// The BOX is the unit that must fit: a single line over its own jpBytes is fine as long as the
// box fits, because we trade space across the lines in it. sceneSlack is static (per active tab);
// sceneFill (the live Catalan expansion) is debounced like the other badges so typing stays fast.
const sceneSlackByTab = ref<Record<string, Record<number, number>>>({})   // tab -> scene -> slack
const sceneSlack = computed<Record<number, number>>(() => sceneSlackByTab.value[activeTab.value] || {})
const sceneFill  = ref<Record<number, number>>({})        // scene -> real expansion bytes (packer)
const blockExp   = ref<Record<string, number>>({})        // block offset -> real per-line expansion
// The meter's authoritative `used` comes from the PACKER, never a UI estimate (which ignores the
// pagination/control bytes the build writes, and would under-report on already-tight slack). Posts
// the tab's blocks to the box's /measure; debounced like the other badges so typing stays fast.
async function measureScenes() {
  const path = curPath.value, tab = activeTab.value
  if (!path || !tab || !blocks.value.length) return
  try {
    const data = await translationApi.measure(path, tab,
      blocks.value.map(b => ({ offset: b.offset, ca: b.ca, jpBytes: b.jpBytes })))
    if (data && data.used) {
      const f: Record<number, number> = {}
      for (const k in data.used as Record<string, number>) f[+k] = (data.used as Record<string, number>)[k]
      sceneFill.value = f
      blockExp.value = (data.line as Record<string, number>) || {}   // per-line, for the cumulative
    }
  } catch { /* keep the last numbers on a transient failure */ }
}
function sceneStatus(scene: number): { used: number; slack: number; pct: number; state: 'ok' | 'warn' | 'over' } {
  const slack = sceneSlack.value[scene] ?? 0
  const used  = Math.max(0, sceneFill.value[scene] ?? 0)
  const pct   = slack > 0 ? Math.round((used / slack) * 100) : (used > 0 ? 999 : 0)
  const state: 'ok' | 'warn' | 'over' = used <= slack ? 'ok' : (used <= slack * 1.15 ? 'warn' : 'over')
  return { used, slack, pct, state }
}
// Box-level project tally for the header: scenes that fit their slack vs scenes over it (from the
// real measure). The meaningful aggregate — per-line "overflow" is noise, a line may exceed its own
// bytes as long as its box fits.
const sceneStats = computed(() => {
  let fit = 0, over = 0
  for (const k in sceneFill.value) {
    if ((sceneFill.value[+k] ?? 0) <= (sceneSlack.value[+k] ?? 0)) fit++
    else over++
  }
  return { fit, over, measured: fit + over }
})

// Per-scene navigation info for the header cells (speakers present + first/last JP and CA lines),
// debounced like the other badges so typing stays fast.
type SceneInfo = { speakers: number[]; firstJp: string; lastJp: string; firstCa: string; lastCa: string }
const sceneInfoMap = ref<Record<number, SceneInfo>>({})
function recomputeSceneInfo() {
  // The game templates every scenario with the same opening line, so a line repeated across many
  // scenes is boilerplate and useless for navigation. Count line frequency and surface each
  // scene's first/last DISTINCTIVE line instead (fall back to any line if a scene is all-boilerplate).
  // `done` lines (handled / texture artifacts marked done at extract) are skipped — they're noise.
  const freq = new Map<string, number>()
  for (const b of blocks.value) if (!b.done && b.jp) freq.set(b.jp, (freq.get(b.jp) || 0) + 1)
  const BOILER = 8
  const m: Record<number, SceneInfo & { seen: Set<number>; anyJp: string; anyCa: string }> = {}
  for (const b of blocks.value) {
    if (b.done) continue
    const sc = b.scene ?? 0
    let e = m[sc]
    if (!e) e = m[sc] = { speakers: [], firstJp: '', lastJp: '', firstCa: '', lastCa: '', seen: new Set(), anyJp: b.jp, anyCa: b.ca }
    if (!e.seen.has(b.speakerId)) { e.seen.add(b.speakerId); e.speakers.push(b.speakerId) }
    if ((freq.get(b.jp) || 0) < BOILER) {                 // distinctive (not the templated boilerplate)
      if (!e.firstJp) { e.firstJp = b.jp; e.firstCa = b.ca }
      e.lastJp = b.jp; e.lastCa = b.ca
    }
  }
  const out: Record<number, SceneInfo> = {}
  for (const k in m) {
    const e = m[+k]
    out[+k] = {
      speakers: e.speakers,
      firstJp: e.firstJp || e.anyJp, lastJp: e.lastJp || e.anyJp,
      firstCa: e.firstJp ? e.firstCa : e.anyCa, lastCa: e.lastJp ? e.lastCa : e.anyCa,
    }
  }
  sceneInfoMap.value = out
}
function sceneInfo(scene: number): SceneInfo {
  return sceneInfoMap.value[scene] || { speakers: [], firstJp: '', lastJp: '', firstCa: '', lastCa: '' }
}

// Story order is per SCENE (you reorder whole scenes, not lines): read/write `order` on every
// block in the scene so the save-sort groups them. Duplicate story numbers are flagged on screen.
function sceneOrder(scene: number): number | undefined {
  return sceneOrderMap.value[scene] ?? undefined   // O(1) lookup (was an O(n) find per header)
}
function setSceneOrder(scene: number, ev: Event) {
  const raw = (ev.target as HTMLInputElement).value
  const n = raw === '' ? undefined : Number(raw)
  for (const b of blocks.value) if ((b.scene ?? 0) === scene) b.order = n
  bumpEdit()                              // local only — persist happens on Save draft
}
const dupStoryOrders = computed<Set<number>>(() => {
  const byScene = new Map<number, number>()
  for (const b of blocks.value) if (b.order != null) byScene.set(b.scene ?? 0, b.order)
  const counts = new Map<number, number>()
  for (const o of byScene.values()) counts.set(o, (counts.get(o) || 0) + 1)
  return new Set([...counts].filter(([, c]) => c > 1).map(([o]) => o))
})

// Returns true if this block starts a new speaker run
function isFirstInRun(idx: number): boolean {
  if (idx === 0) return true
  return blocks.value[idx].speakerId !== blocks.value[idx - 1].speakerId
}

// Aggregate across ALL loaded sources (every tab), not just the active one, so the
// header badges read project-wide progress. Grows as lazy tabs stream in.
// DEBOUNCED: this loops all ~8k blocks, so as a reactive `computed` it re-ran on
// every keystroke and froze editing. Now it's a ref recomputed ~300ms after edits
// settle (badges lag a moment; typing stays instant).
const stats = ref({ total: 0, pending: 0, ok: 0, warn: 0, over: 0 })
function recomputeStats() {
  let total = 0, pending = 0, ok = 0, warn = 0, over = 0
  for (const arr of Object.values(tabBlocks.value)) {
    for (const b of arr) {
      total++
      const s = byteStatus(b)
      if (s === 'pending') pending++
      else if (s === 'ok') ok++
      else if (s === 'warn') warn++
      else over++
    }
  }
  stats.value = { total, pending, ok, warn, over }
}
let statsTimer: ReturnType<typeof setTimeout> | undefined

// ── Drop + language step ──────────────────────────────────────────────────────

type Step = 'pick' | 'table'
const step = ref<Step>('pick')

async function saveState() {
  if (!curNs.value) return
  // Flush EVERY loaded tab, not just the active one. Under the manual-save model, edits accumulate
  // across tabs (each block is mutated in place inside tabBlocks) and only reach disk here. Saving
  // just the active tab silently dropped edits made on other tabs — e.g. translate a menu, switch
  // tabs, hit Save, and the menu never made it into the PUT, so it reverted to its old state value.
  // Skip a tab that never loaded (empty array) so an aborted extract can't wipe a source. The API
  // deep-merges by source key, so untouched/unloaded sources are preserved.
  const sources = buildSourcesPayload(tabBlocks.value)
  if (!Object.keys(sources).length) return
  // THROWS if the API rejects/unreachable — callers must surface it. Swallowing here is the bug that
  // ate drafts: "Saved ✓" showed and `dirty` cleared while nothing reached disk (API was down).
  await translationApi.putState(curNs.value, { sources, sceneBudget: sceneSlackByTab.value })
}
// Typing must do NOTHING heavy. The fit-meter + stats refresh only when you leave a field (blur),
// not on each keystroke — so editing a line is as light as typing into a plain textbox.
function onCaCommit() { bumpEdit() }     // local only — persist happens on Save draft

// ── Propagate: make every block with the SAME Japanese share one Catalan ───────
// A line recurs dozens of times as separate blocks; without this they drift (1,000+
// blocks were inconsistent) and every tightening would need N hand-edits. Click the
// row you want as canonical -> it fills all identical-JP copies and saves once.
const jpCounts = ref<Map<string, number>>(new Map())
function recomputeJpCounts() {
  const m = new Map<string, number>()
  for (const b of blocks.value) if (b.jp) m.set(b.jp, (m.get(b.jp) || 0) + 1)
  jpCounts.value = m
}
function dupCount(jp: string | undefined): number {
  return jp ? (jpCounts.value.get(jp) || 1) : 1
}
function propagate(block: Block) {
  if (!block.jp) return
  const ca = block.ca
  for (const b of blocks.value) if (b.jp === block.jp) b.ca = ca
  bumpEdit()                              // local only — persist happens on Save draft
}

// ── Batocera pick → translate flow ─────────────────────────────────────────
interface PickSystem { node: string; name: string; system: string; supported: boolean }
interface PickGame   { name: string; path: string }

const systems       = ref<PickSystem[]>([])
const games         = ref<PickGame[]>([])
const selSource     = ref('ja')   // locked: only Japanese source text is detected for now
const selLang       = ref('')
const selSystem     = ref('')
const selGame       = ref('')
const selGameName   = ref('')
const extracting    = ref(false)
const pickError     = ref('')

const langLabel = computed(() => LANGUAGES.find(l => l.code === selLang.value)?.label || '')

// Decode a block's raw Shift-JIS bytes (hex) in the browser — Batocera has no
// shift_jis codec, so the box ships raw bytes and we decode here. Control bytes
// (line/page breaks) collapse to spaces for display; the build patches by offset.
function decodeBlock(hex: string): string {
  const bytes = new Uint8Array((hex.match(/../g) || []).map(h => parseInt(h, 16)))
  return new TextDecoder('shift_jis').decode(bytes)
    .replace(/[\u0000-\u001f\ufffd]/g, ' ')   // strip control bytes + invalid-byte markers
    .replace(/ {2,}/g, ' ').trim()
}

// ── Projects (no DB — the dirs under dist/translations/ ARE the project list) ──
interface Project { ns: string; gameName: string; lang: string; total: number; system?: string; path?: string; meta?: GameMeta | null }
const projects = ref<Project[]>([])
const curNs    = ref('')
async function loadProjects() {
  try {
    const data = await translationApi.listProjects()
    projects.value = (data.projects as Project[]) || []
    // Projects saved before metadata existed have a path but no meta — backfill it
    // (instant IP.BIN read) so the whole list gets rich cards, and persist it once.
    for (const p of projects.value) if (!p.meta && p.path) backfillProjectMeta(p.ns, p.path)
  } catch { /* leave list as-is */ }
}

async function backfillProjectMeta(ns: string, path: string) {
  try {
    const data = await translationApi.meta(path)
    if (!data.meta) return
    projects.value = projects.value.map(p => (p.ns === ns ? { ...p, meta: data.meta } : p))
    translationApi.putState(ns, { meta: data.meta }).catch(() => {})   // persist so it's a one-time cost
  } catch { /* keep the gameName fallback */ }
}

function consoleLabel(sys: string): string {
  return systems.value.find(s => s.system === sys)?.name || sys || 'Other'
}

// Projects grouped by console, sorted (consoles A-Z, games A-Z within). The header
// count is always shown so collapsing a console never hides how many you really have.
const groupedProjects = computed(() => {
  const by = new Map<string, Project[]>()
  for (const p of projects.value) {
    const k = p.system || ''
    if (!by.has(k)) by.set(k, [])
    by.get(k)!.push(p)
  }
  return [...by.entries()]
    .map(([sys, list]) => ({
      sys,
      label: consoleLabel(sys),
      projects: [...list].sort((a, b) => a.gameName.localeCompare(b.gameName)),
    }))
    .sort((a, b) => a.label.localeCompare(b.label))
})

// Collapse state per console, remembered across sessions.
const COLLAPSE_KEY = 'cpc.translate.collapsed'
function loadCollapsed(): Record<string, boolean> {
  try { return JSON.parse(localStorage.getItem(COLLAPSE_KEY) || '{}') } catch { return {} }
}
const collapsedConsoles = ref<Record<string, boolean>>(loadCollapsed())
function toggleConsole(sys: string) {
  collapsedConsoles.value = { ...collapsedConsoles.value, [sys]: !collapsedConsoles.value[sys] }
  try { localStorage.setItem(COLLAPSE_KEY, JSON.stringify(collapsedConsoles.value)) } catch { /* ignore */ }
}

// Create = "I want to work on it now": extract, persist, open the table.
async function createProject() {
  if (!selGame.value || !selLang.value || extracting.value) return
  extracting.value = true
  pickError.value  = ''
  try {
    const gameName = games.value.find(g => g.path === selGame.value)?.name || 'game'
    const ns = `${gameName} [${selLang.value}]`
    if (projects.value.some(p => p.ns === ns)) {
      pickError.value = 'That project already exists. Open it from Previous Projects below.'
      return
    }
    // Reach the table page IMMEDIATELY; the scan + first extract run THERE (the
    // table shows a scanning state), so a big disc no longer freezes the picker.
    selGameName.value  = gameName
    curNs.value        = ns
    blocks.value       = []
    tabBlocks.value    = {}                                 // fresh project: no saved drafts
    speakerNames.value = {}
    toneLinks.value    = ''
    step.value         = 'table'
    router.push(`/translation/${encodeURIComponent(ns)}`)  // watcher: ns===curNs → no-op
    await loadSources(selGame.value)
    if (!tabs.value.length) {
      step.value  = 'pick'                                 // bounce back with the error
      curNs.value = ''
      router.replace('/translation')
      pickError.value = 'No translatable text found in this game.'
      return
    }
    // Persist the record + the primary source's blocks so resume is instant.
    const primarySafe = tabs.value[0].safe
    // NB: no `total` here on purpose — persistTotal() is the sole writer of the aggregate,
    // so the create POST can't clobber it back to the primary count.
    await translationApi.createState(ns, {
      gameName, lang: selLang.value, system: selSystem.value,
      path: selGame.value, meta: meta.value,
      sources: { [primarySafe]: tabBlocks.value[primarySafe] || [] },
    })
    loadProjects()
  } catch {
    pickError.value = 'Could not extract this game.'
  } finally {
    extracting.value = false
  }
}

// Load a saved project's state.json into the table. Driven by the URL watcher.
async function openNs(ns: string) {
  if (!ns) return
  try {
    const data = await translationApi.getState(ns)
    if (data && data.path) {
      selGameName.value = (data.gameName as string) || ns
      selLang.value     = (data.lang as string) || ''
      curNs.value       = ns
      tabBlocks.value    = (data.sources as Record<string, Block[]>) || {}   // preload saved drafts
      sceneSlackByTab.value = (data.sceneBudget as Record<string, Record<number, number>>) || {}  // box budgets baked into state
      speakerNames.value = (data.speakers as Record<string, Record<number, string>>) || {}
      toneLinks.value    = (data.toneLinks as string) || ''
      blocks.value       = []
      step.value        = 'table'
      loadSources(data.path as string)   // tabs reuse saved drafts, fetch the rest
    } else {
      router.replace('/translation')   // project gone → back to the picker
    }
  } catch { /* ignore */ }
}

// ── Multitab: one tab per discovered source (box /sources), lazy per-tab load ──
interface SourceTab {
  file: string; safe: string; kind: string
  view: number; loadOrder: number; size: number; kanaPct: number
}
const tabs      = ref<SourceTab[]>([])
const activeTab = ref('')                                  // active source's safe-name
const tabBlocks = ref<Record<string, Block[]>>({})
const tabState  = ref<Record<string, 'idle' | 'loading' | 'ready' | 'error'>>({})
const curPath   = ref('')                                  // the game's GDI path
const discovering = ref(false)                             // /sources scan in flight
// True while the disc is being scanned or any tab is still extracting -- the header stats are
// partial/meaningless until everything's in, so we show a skeleton instead of flashing counts.
const tabsLoading = computed(() =>
  discovering.value || !tabs.value.length || tabs.value.some(t => tabState.value[t.safe] !== 'ready'))

// % of the ACTIVE tab's lines that carry a translation. A computed over `blocks`
// would re-run per keystroke (the freeze we just fixed), so it's a ref refreshed
// on the same debounce as the badges, plus instantly on tab change.
const tabProg = ref({ done: 0, total: 0, pct: 0 })
const speakerPct = ref<Record<number, number>>({})    // per-speaker % done (debounced)
function recomputeTabPct() {
  const arr = blocks.value
  let done = 0
  const per: Record<number, [number, number]> = {}     // id -> [done, total]
  for (const b of arr) {
    const t = caBytes(b.ca) > 0 || !!b.done
    if (t) done++
    const e = per[b.speakerId] || [0, 0]
    e[1]++; if (t) e[0]++
    per[b.speakerId] = e
  }
  tabProg.value = { done, total: arr.length, pct: arr.length ? Math.round((done / arr.length) * 100) : 0 }
  const sp: Record<number, number> = {}
  for (const id in per) { const [d, tt] = per[id]; sp[Number(id)] = tt ? Math.round((d / tt) * 100) : 0 }
  speakerPct.value = sp
}

// An edit bumps this cheap counter; the heavy recompute debounces off IT. A `{ deep: true }`
// watch over the whole blocks array re-traversed all ~7,600 blocks on every keystroke — that was
// the typing lag. A shallow counter watch costs nothing per char.
const editTick = ref(0)
const dirty = ref(false)                 // unsaved local edits; only "Save draft" persists to disk
function bumpEdit() { editTick.value++; dirty.value = true; saveError.value = false }
// Manual-save model: warn before leaving/reloading with unsaved edits (nothing hits disk until Save draft).
window.addEventListener('beforeunload', (e) => { if (dirty.value) { e.preventDefault(); e.returnValue = '' } })
watch(editTick, () => {
  clearTimeout(statsTimer)
  statsTimer = setTimeout(() => { recomputeStats(); recomputeTabPct(); measureScenes(); recomputeSceneInfo() }, 300)
})
watch(activeTab, recomputeTabPct, { immediate: true })


// ── Scene accordion ────────────────────────────────────────────────────────────
// The dialogue is grouped into scenario "boxes" the engine packs text into. Each is a
// bordered, collapsible section so the translator works one scene at a time. Collapsed by
// default: opening a project shows a clean scene index (~76 headers), not 7.6k rows, which
// also means no virtual-scroll machinery is needed (a collapsed scene is one header row).
const scrollEl = ref<HTMLElement | null>(null)
const expanded = ref<Set<number>>(new Set())     // which scenes are open (empty = all collapsed)
function toggleScene(scene: number) {
  // Accordion: one box open at a time. displayRows emits every header but only the
  // OPEN box's rows, so the rendered DOM is one scene's textareas, not the whole
  // 7,600-line file. Keeps typing fast no matter how many boxes you've worked through.
  expanded.value = expanded.value.has(scene) ? new Set() : new Set([scene])
}
// Sort toggle: float the over-budget boxes to the top so you can work through them. The offsets are
// fixed (slack is per-box, never shared), so this only reorders the VIEW, never the disc. Snapshots
// the overflow when you click (not live) so the box you're editing doesn't reshuffle under you; click
// again to re-rank — a box you've just brought into budget drops to the green pile. Smallest overflow
// sits on top, so you peel the closest-to-fitting boxes off first.
const sortMode = ref<'story' | 'overflow'>('story')
const overflowRank = ref<Record<number, number>>({})
function toggleSortOverflow() {
  if (sortMode.value === 'overflow') { sortMode.value = 'story'; return }
  const r: Record<number, number> = {}
  for (const k in sceneFill.value) {
    const over = (sceneFill.value[+k] ?? 0) - (sceneSlack.value[+k] ?? 0)
    if (over > 0) r[+k] = over
  }
  overflowRank.value = r
  sortMode.value = 'overflow'
}
type Disp =
  | { kind: 'head'; scene: number; slack: number; offset: string }
  | { kind: 'row'; block: Block; index: number; cum: number; slack: number; runStart: boolean }
type SceneGroup = { scene: number; order: number | null; slack: number; offset: string
                    rows: { block: Block; index: number; runStart: boolean }[] }
// The heavy O(7,600) walk, run ONCE. Groups blocks into scenes and precomputes each row's
// run-start. Depends only on block identity (scene/order/offset/speakerId) + slack — NOT on
// expand/sort/measure/ca. So opening a box or re-sorting never re-walks the whole file again.
const sceneGroups = computed<SceneGroup[]>(() => {
  const arr = blocks.value
  const byScene = new Map<number, SceneGroup>()
  const groups: SceneGroup[] = []
  for (let i = 0; i < arr.length; i++) {
    const b = arr[i]
    const sc = b.scene ?? 0
    let g = byScene.get(sc)
    if (!g) {
      g = { scene: sc, order: b.order ?? null, slack: sceneSlack.value[sc] ?? 0, offset: b.offset, rows: [] }
      byScene.set(sc, g); groups.push(g)
    }
    if (g.order == null && b.order != null) g.order = b.order
    g.rows.push({ block: b, index: i, runStart: isFirstInRun(i) })
  }
  return groups
})
// scene -> Story #, memoized (was an O(n) find() called PER HEADER = O(n²) every render).
const sceneOrderMap = computed<Record<number, number | null>>(() => {
  const m: Record<number, number | null> = {}
  for (const g of sceneGroups.value) m[g.scene] = g.order
  return m
})
// Flat render list: sort the cached groups + emit headers, rows only when expanded. Cheap —
// ~76 groups + one open box's rows, never the whole file. Reads scene/identity, not ca text.
const displayRows = computed<Disp[]>(() => {
  const groups = [...sceneGroups.value]
  if (sortMode.value === 'overflow') {
    const rank = overflowRank.value
    groups.sort((a, b) => {
      const oa = rank[a.scene], ob = rank[b.scene]
      if (oa !== undefined && ob !== undefined) return oa - ob   // over-budget first, smallest overflow on top
      if (oa !== undefined) return -1
      if (ob !== undefined) return 1
      return a.scene - b.scene                                    // in-budget boxes after, in disc order
    })
  } else {
    groups.sort((a, b) => {
      if (a.order != null && b.order != null) return a.order - b.order
      if (a.order != null) return -1
      if (b.order != null) return 1
      return a.scene - b.scene
    })
  }
  const out: Disp[] = []
  for (const g of groups) {
    out.push({ kind: 'head', scene: g.scene, slack: g.slack, offset: g.offset })
    if (expanded.value.has(g.scene)) {
      let cum = 0
      // running box usage in disc order, so each row shows how full the box is up to (and incl.) it
      for (const r of g.rows) {
        cum += blockExp.value[r.block.offset] || 0
        out.push({ kind: 'row', block: r.block, index: r.index, cum, slack: g.slack, runStart: r.runStart })
      }
    }
  }
  return out
})
// Collapse everything + scroll to top when the active tab changes.
watch(activeTab, () => {
  expanded.value = new Set()
  if (scrollEl.value) scrollEl.value.scrollTop = 0
  sceneFill.value = {}                   // clear -> meters show "…" until the new measure lands
  measureScenes()                        // real per-scene budget for the newly active tab
  recomputeSceneInfo()                   // header first/last lines are per-tab -- recompute or the new
  recomputeJpCounts()                    // tab shows the PREVIOUS tab's scene-0 line (the "tete" bug)
})


// Disc metadata (IP.BIN) for the header card — instant (~74ms), fetched on open.
const meta = ref<GameMeta | null>(null)
async function fetchMeta(path: string) {
  meta.value = null
  try {
    const data = await translationApi.meta(path)
    meta.value = (data.meta as GameMeta) || null
  } catch { meta.value = null }
}

// ── Speaker legend: editable names per source, persisted in state.json.speakers ──
const speakerNames = ref<Record<string, Record<number, string>>>({})   // safe -> id -> name

// Distinct speakers in the active source's blocks, major-first, with table colours.
const activeSpeakers = computed(() => {
  const counts = new Map<number, number>()
  for (const b of blocks.value) counts.set(b.speakerId, (counts.get(b.speakerId) || 0) + 1)
  return [...counts.entries()]
    .map(([id, count]) => ({ id, count, color: speakerColor(id) }))
    .sort((a, b) => a.id - b.id)
})
// Only a real legend if the source carries speaker tags (any non-zero id).
const showLegend = computed(() => activeSpeakers.value.some(s => s.id !== 0))
const activeNames = computed(() => speakerNames.value[activeTab.value] || {})

// The table's speaker column reads names through a DEBOUNCED copy. Editing a name
// in the legend otherwise re-rendered its label across all ~7k rows on every
// keystroke; the legend input still updates live (cheap, ~10 chips), the table
// catches up ~300ms after you pause. Refreshed instantly on tab change.
const displayNames = ref<Record<number, string>>({})
let displayTimer: ReturnType<typeof setTimeout> | undefined
function refreshDisplayNames() { displayNames.value = activeNames.value }
watch(activeTab, refreshDisplayNames, { immediate: true })

// The display name for a speaker id — the legend name once set, else a fallback.
function speakerLabel(id: number): string {
  return displayNames.value[id] || 'Speaker Unknown'
}

let speakerSaveTimer: ReturnType<typeof setTimeout> | undefined
function renameSpeaker(id: number, name: string) {
  const safe = activeTab.value
  if (!safe) return
  speakerNames.value = {
    ...speakerNames.value,
    [safe]: { ...(speakerNames.value[safe] || {}), [id]: name },
  }
  clearTimeout(speakerSaveTimer)
  speakerSaveTimer = setTimeout(saveSpeakers, 600)        // debounce save while typing
  clearTimeout(displayTimer)
  displayTimer = setTimeout(refreshDisplayNames, 300)     // debounce the 7k-row re-render
}
async function saveSpeakers() {
  if (!curNs.value || !activeTab.value) return
  try {
    await translationApi.putState(curNs.value, { speakers: { [activeTab.value]: speakerNames.value[activeTab.value] || {} } })
  } catch { /* offline — names stay local */ }
}

const KIND_LABEL: Record<string, string> = {
  dialogue: 'Dialogue', menu: 'Menu', items: 'Items', ui: 'UI',
  chat: 'Chat', secret: 'Secret', readme: 'Readme', text: 'Text',
  screen: 'Screen', system: 'System',
}
// Every tab is named by its FILENAME (unique) with the kind as a hint, e.g.
// "S1_1_SCENE (TEXT)" -- any kind can have multiple files (per-chapter dialogue,
// several UI blobs...) and would otherwise dupe as "Dialogue"/"UI"/"Text".
function tabLabel(t: SourceTab): string {
  const base = (t.file.split(/[\\/]/).pop() || t.file).replace(/\.[^.]+$/, '')
  return `${base} (${(KIND_LABEL[t.kind] || t.kind).toUpperCase()})`
}

// ── Prompt rail: the Claude translation prompt + per-project reference links ──
const RAIL_KEY = 'cpc.translate.rail'
const railOpen = ref(localStorage.getItem(RAIL_KEY) === '1')
function toggleRail() {
  railOpen.value = !railOpen.value
  try { localStorage.setItem(RAIL_KEY, railOpen.value ? '1' : '0') } catch { /* ignore */ }
}
const toneLinks = ref('')                                  // reference links, per project
let toneSaveTimer: ReturnType<typeof setTimeout> | undefined
function onToneLinks(v: string) {
  toneLinks.value = v
  clearTimeout(toneSaveTimer)
  toneSaveTimer = setTimeout(saveToneLinks, 700)           // debounce while typing
}
async function saveToneLinks() {
  if (!curNs.value) return
  try {
    await translationApi.putState(curNs.value, { toneLinks: toneLinks.value })
  } catch { /* offline — links stay local */ }
}
// The active source, named for the prompt (kind label + on-disc filename).
const activeTabObj   = computed(() => tabs.value.find(t => t.safe === activeTab.value))
const activeKindLabel = computed(() => { const t = activeTabObj.value; return t ? (KIND_LABEL[t.kind] || t.kind) : 'Text' })
const activeFileName  = computed(() => { const f = activeTabObj.value?.file || ''; return f.split(/[\\/]/).pop() || f })
// While the rail is open, keep the active source persisted in state.json.sources so
// the prompt's GET (json in) actually finds it — Claude reads + writes the same key.
watch([railOpen, activeTab], () => {
  // Best-effort background save; the manual Save draft is the one that reports success/failure.
  if (railOpen.value && curNs.value && activeTab.value && blocks.value.length) saveState().catch(() => {})
})
function mapBlocks(raw: { offset: number; jpBytes: number; hex: string; speaker: number; scene?: number }[]): Block[] {
  return (raw || []).map(b => ({
    offset:    formatOffset(b.offset),
    speakerId: b.speaker ?? 0,
    jp:        decodeBlock(b.hex),
    jpBytes:   b.jpBytes,
    ca:        '',
    scene:     b.scene ?? 0,
  }))
}

// Discover the sources, AWAIT the primary (first content), then fire the rest in
// PARALLEL. Tabs whose draft is already in tabBlocks (preloaded by openNs, or a
// freshly-loaded one) are REUSED, not re-fetched. tabBlocks is set by the caller:
// openNs preloads saved drafts; createProject clears it.
async function loadSources(path: string) {
  curPath.value = path
  fetchMeta(path)                       // header card — parallel, non-blocking
  tabs.value = []; tabState.value = {}
  discovering.value = true
  let srcs: SourceTab[] = []
  try {
    srcs = ((await translationApi.sources(path)).sources as SourceTab[]) || []
  } finally {
    discovering.value = false
  }
  tabs.value = [...srcs].sort((a, b) => a.view - b.view)
  const state: Record<string, 'idle' | 'ready'> = {}
  // Re-extract (to gain `scene`/budget tags) unless the saved draft already carries them; loadTab
  // reconciles the saved ca/order/done back in by offset, so this self-heals pre-scene projects.
  srcs.forEach(s => {
    const saved = tabBlocks.value[s.safe]
    state[s.safe] = (saved && saved.length && saved[0].scene !== undefined) ? 'ready' : 'idle'
  })
  tabState.value = state
  const primary = tabs.value[0]
  if (primary) {
    activeTab.value = primary.safe
    blocks.value = tabBlocks.value[primary.safe] || []
    if (state[primary.safe] !== 'ready') await loadTab(primary.safe)   // first content
  }
  // the rest, in PARALLEL; once they all settle, persist the TRUE aggregate total
  // (the saved `total` was the primary tab only — the list undercounted).
  const rest = [...srcs]
    .sort((a, b) => a.loadOrder - b.loadOrder)
    .filter(s => s.safe !== primary?.safe && tabState.value[s.safe] !== 'ready')
    .map(s => loadTab(s.safe))
  Promise.all(rest).then(() => {
    // Everything's in: compute the real stats NOW so they're fresh the instant the skeleton lifts.
    recomputeStats(); recomputeTabPct(); recomputeSceneInfo(); recomputeJpCounts(); measureScenes()
    if (curNs.value) persistTotal()
  })
}

// Write the all-sources block count back to state.json so the projects list shows
// the whole disc, not just the first tab. Self-heals older projects when opened.
async function persistTotal() {
  try {
    await translationApi.putState(curNs.value, { total: stats.value.total })
    loadProjects()   // refresh the list so the card reflects the new aggregate
  } catch { /* offline — list keeps the old count */ }
}

async function loadTab(safe: string) {
  if (tabState.value[safe] === 'loading' || tabState.value[safe] === 'ready') return
  // reassign the whole object so the update reliably triggers re-render (a per-key
  // mutation was arriving but not rendering until a refresh).
  tabState.value = { ...tabState.value, [safe]: 'loading' }
  try {
    const data = await translationApi.extract(curPath.value, safe)
    // Reconcile: the fresh extract carries `scene` + jpBytes; overlay any saved draft's
    // ca/order/done onto it by offset, so re-extracting to gain scene tags never loses work.
    const fresh = reconcileByOffset(mapBlocks(data.blocks), tabBlocks.value[safe])
    tabBlocks.value = { ...tabBlocks.value, [safe]: fresh }
    // Bake the per-scene slack (from extraction) for this tab's box-budget meter. Only the
    // SCP/CMD source (nullsplit) ships scenes; others simply have no box meter.
    if (Array.isArray(data.scenes)) {
      const sl: Record<number, number> = {}
      for (const s of data.scenes as { scene: number; slack: number }[]) sl[s.scene] = s.slack
      sceneSlackByTab.value = { ...sceneSlackByTab.value, [safe]: sl }
    }
    tabState.value  = { ...tabState.value, [safe]: 'ready' }
    if (activeTab.value === safe) blocks.value = tabBlocks.value[safe]
  } catch {
    tabState.value = { ...tabState.value, [safe]: 'error' }
  }
}

function selectTab(safe: string) {
  activeTab.value = safe
  blocks.value = tabBlocks.value[safe] || []
  if (tabState.value[safe] !== 'ready') loadTab(safe)
}

// Re-fetch any source that errored or never loaded (cheap: already cached on the box).
function retryTabs() {
  tabs.value.forEach(t => loadTab(t.safe))   // loadTab skips the ones already 'ready'
}

// Save draft = persist the active tab's translations to state.json. No ROM build.
const draftSaved = ref(false)
const saveError  = ref(false)     // last Save draft failed (API unreachable/rejected) — work NOT on disk
async function saveDraft() {
  clearTimeout(speakerSaveTimer)                       // flush pending speaker edits now
  saveError.value = false
  try {
    await Promise.all([saveState(), saveSpeakers()])   // blocks + speaker names — throws if the API rejects
    dirty.value = false                                // ONLY clear dirty + claim success on a real write
    draftSaved.value = true
    setTimeout(() => { draftSaved.value = false }, 1800)
  } catch {
    // The write didn't land (API offline / error). Keep `dirty` so the beforeunload guard still fires
    // and the operator knows their draft isn't saved — never a false "Saved ✓".
    saveError.value = true
  }
}

// Build = rebuild the patched ROM on Batocera (translate.sh). Blocking on the box.
// Success fires the shared ACHIEVEMENT toast; failure surfaces loud + red inline.
const { unlock } = useAchievement()
const building = ref(false)
const buildMsg = ref('')
const buildFailed = ref(false)
async function runBuild() {
  if (building.value || !curPath.value) return
  building.value = true; buildMsg.value = ''; buildFailed.value = false
  const startedAt = Date.now()
  try {
    const data = await translationApi.run(curPath.value)
    if (data.error) {
      buildFailed.value = true
      buildMsg.value = `Build failed: ${data.error}`.slice(0, 80)
    } else {
      const secs = Math.round((Date.now() - startedAt) / 1000)
      unlock(`Released to Batocera — ${selGameName.value || 'game'}`, `${secs}s`)
    }
  } catch {
    buildFailed.value = true
    buildMsg.value = 'Build failed: no response from the box'
  } finally {
    building.value = false
    if (buildFailed.value) setTimeout(() => { buildMsg.value = '' }, 8000)
  }
}

// Pre-flight before building: all-green => go straight through; otherwise warn
// (untranslated lines ship as Japanese; overflow lines truncate until the expander).
const showBuildWarn = ref(false)
function confirmBuild() {
  if (building.value || !curPath.value) return
  const s = stats.value
  if (s.pending === 0 && s.over === 0) { runBuild(); return }   // all green -> safe to go
  showBuildWarn.value = true
}
function proceedBuild() { showBuildWarn.value = false; runBuild() }

// Clicking a project just navigates; the URL is the source of truth.
function loadProject(p: Project) {
  router.push(`/translation/${encodeURIComponent(p.ns)}`)
}

// The URL drives the view: <ns> -> open that table, empty -> the picker. immediate
// so a reload / HMR with /translation/<ns> restores the open table.
watch(() => route.params.ns, (raw) => {
  const ns = (raw as string) || ''
  if (!ns)                { step.value = 'pick'; curNs.value = ''; loadProjects(); return }
  if (ns === curNs.value) return   // already loaded (e.g. just created)
  openNs(ns)
}, { immediate: true })

function openProjectDir(p: Project) {
  translationApi.openDir(p.ns)
}

function langName(code: string) {
  return LANGUAGES.find(l => l.code === code)?.label || code
}

function deleteProject(p: Project) {
  if (!confirm(`Delete the ${p.gameName} (${langName(p.lang)}) project? This removes its saved table.`)) return
  translationApi.remove(p.ns).then(() => loadProjects())
}

function backToProjects() {
  router.push('/translation')
}

async function loadSystems() {
  pickError.value = ''
  try {
    const data = await translationApi.listSystems()
    systems.value = (data.systems as PickSystem[]) || []
  } catch {
    pickError.value = 'Could not reach the API.'
  }
}

async function onSystemChange() {
  selGame.value       = ''
  games.value         = []
  pickError.value     = ''
  if (!selSystem.value) return
  try {
    const data = await translationApi.listGames(selSystem.value)
    games.value = (data.games as PickGame[]) || []
  } catch {
    pickError.value = 'Could not list games.'
  }
}

watch(selSystem, onSystemChange)   // refresh games when the system changes

// External translators (Claude via cpc) write straight to state.json, so the open
// table won't see them without a poll. Pull the saved state and merge changed `ca`
// IN PLACE (mutate, don't replace) so only the changed rows re-render — never the
// whole 7k-row table. Paused while an input is focused, so it can't clobber typing.
let pollTimer: ReturnType<typeof setInterval> | undefined
async function pollSaved() {
  if (step.value !== 'table' || !curNs.value || stats.value.pending === 0) return
  // Manual-save model: unsaved local edits are the source of truth. This poll only pulls in
  // EXTERNAL (Claude) changes; while `dirty`, remote is stale by definition, so merging it would
  // clobber the edits you haven't saved yet (index-merge below reverts them). Resume once you save.
  if (dirty.value) return
  const ae = document.activeElement as HTMLElement | null
  if (ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA')) return
  const ns = curNs.value
  try {
    const data = await translationApi.getState(ns)
    if (ns !== curNs.value || !data || !data.sources) return     // navigated away mid-fetch
    const src = data.sources as Record<string, Block[]>
    for (const safe of Object.keys(tabBlocks.value)) {
      mergePolledCa(tabBlocks.value[safe], src[safe])
    }
  } catch { /* offline — try again next tick */ }
}

onMounted(() => {
  loadSystems()
  loadProjects()
  pollTimer = setInterval(pollSaved, 5000)
})
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
</script>

<template>
  <div class="tt-root">

    <!-- ── EXPERIMENTAL DISCLAIMER (compact, dismissible for the session) ── -->
    <div v-if="!disclaimerDismissed" class="tt-disclaimer">
      <span class="tt-disclaimer-text"><strong>⚠️ Experimental</strong> Extraction is game-specific and a work in progress. Expect broken ROMs &amp; corrupted text. Contributions are very welcome.</span>
      <UiClose class="tt-disclaimer-x" title="Hide for this session" @click="dismissDisclaimer" />
    </div>

    <!-- ── Pick language + game, open the translation table ── -->
    <div v-if="step === 'pick'" class="tt-setup">
      <div class="tt-setup-form">
      <div class="tt-lang-row">
        <label class="tt-lang-label">Source language</label>
        <UiSelect v-model="selSource" disabled>
          <option value="ja">日本語 (Japanese)</option>
        </UiSelect>
        <span class="tt-lang-hint">Only Japanese source supported for now</span>
      </div>

      <div class="tt-lang-row">
        <label class="tt-lang-label">Target language</label>
        <UiSelect v-model="selLang">
          <option value="" disabled>Pick a language</option>
          <option v-for="l in LANGUAGES" :key="l.code" :value="l.code">{{ l.label }}</option>
        </UiSelect>
      </div>

      <div class="tt-lang-row">
        <label class="tt-lang-label">System</label>
        <UiSelect v-model="selSystem">
          <option value="" disabled>Pick a system</option>
          <option v-for="s in systems" :key="s.system" :value="s.system" :disabled="!s.supported">{{ s.name }}</option>
        </UiSelect>
      </div>

      <div class="tt-lang-row">
        <label class="tt-lang-label">Game</label>
        <UiSelect v-model="selGame" :disabled="!selSystem || !games.length">
          <option value="" disabled>
            {{ !selSystem ? 'Pick a system first' : (games.length ? 'Pick a game' : 'No translatable GDI games') }}
          </option>
          <option v-for="g in games" :key="g.path" :value="g.path">{{ g.name }}</option>
        </UiSelect>
      </div>

      <UiButton variant="primary" :loading="extracting" :disabled="!selGame || !selLang" loading-text="Scanning…" @click="createProject">
        Create
      </UiButton>

      <div v-if="extracting" class="tt-translating">
        <UiSpinner />
        <span>Scanning disc for text… first time on a game takes a minute.</span>
      </div>
      <p v-if="pickError" class="tt-upload-error">{{ pickError }}</p>
      </div>

      <!-- Previous projects: a right rail of collapsible console groups (no DB —
           the dirs ARE the list). Scrolls internally; header counts always show. -->
      <aside v-if="projects.length" class="tt-projects tt-setup-rail">
        <p class="tt-projects-heading">Previous Projects</p>
        <div v-for="g in groupedProjects" :key="g.sys" class="tt-proj-group">
          <button class="tt-proj-group-head" @click="toggleConsole(g.sys)">
            <span class="tt-proj-caret">{{ collapsedConsoles[g.sys] ? '▸' : '▾' }}</span>
            <span class="tt-proj-group-name">{{ g.label }}</span>
            <span class="tt-proj-group-count">{{ g.projects.length }}</span>
          </button>
          <ul v-show="!collapsedConsoles[g.sys]" class="tt-projects-list">
            <li v-for="p in g.projects" :key="p.ns" class="tt-project">
              <button class="tt-project-open" @click="loadProject(p)">
                <MetadataCard
                  class="tt-proj-card"
                  :meta="p.meta || null"
                  :game-name="p.gameName"
                  :pair="`日本語 → ${langName(p.lang)}`"
                  variant="list"
                />
                <span class="tt-project-count">{{ p.total.toLocaleString() }} blocks</span>
              </button>
              <div class="tt-project-actions">
                <UiIconButton variant="bordered" title="Open project folder" @click="openProjectDir(p)">📁</UiIconButton>
                <UiIconButton variant="bordered" danger title="Delete project" @click="deleteProject(p)">🗑</UiIconButton>
              </div>
            </li>
          </ul>
        </div>
      </aside>
    </div>


    <!-- ── Step 2: Header + table ── -->
    <template v-else-if="step === 'table'">
    <!-- Header -->
    <div class="tt-header">
      <div class="tt-title">
        <UiButton class="tt-back" @click="backToProjects">‹ Projects</UiButton>
        <MetadataCard
          :meta="meta"
          :game-name="selGameName"
          :pair="`日本語 → ${langLabel || 'Català'}`"
          variant="header"
        />
      </div>
      <div class="tt-stats">
        <template v-if="tabsLoading">
          <span class="stat-skel" style="width:78px"></span>
        </template>
        <template v-else>
          <span class="tt-total">{{ stats.total.toLocaleString() }} blocks</span>
        </template>
        <span class="tt-actions">
          <span v-if="buildMsg" class="tt-build-msg" :class="{ 'tt-build-msg--fail': buildFailed }">{{ buildMsg }}</span>
          <UiButton class="tt-action" :class="{ 'tt-dirty': dirty && !draftSaved && !saveError, 'tt-save-fail': saveError }" :disabled="building || extracting" @click="saveDraft">{{ saveError ? '⚠ Save failed — retry' : draftSaved ? 'Saved ✓' : (dirty ? 'Save draft •' : 'Save draft') }}</UiButton>
          <UiButton variant="primary" :loading="building" :disabled="extracting" loading-text="Releasing…" @click="confirmBuild">Build &amp; release to Batocera</UiButton>
        </span>
      </div>
    </div>

    <!-- Cold scan: we're already on the table page, so show progress HERE, not a frozen picker -->
    <div v-if="discovering" class="tt-scanning">
      <UiSpinner />
      <span>Scanning disc for text… first time on a game takes a minute.</span>
    </div>

    <!-- Main work area (tabs + table) beside the collapsible Claude-prompt rail -->
    <div v-else class="tt-body">
    <div class="tt-main">

    <!-- Source tabs: one per discovered file (view order); they fill in as they load -->
    <div class="tt-tabs" v-if="tabs.length">
      <button v-for="t in tabs" :key="t.safe"
              class="tt-tab" :class="{ 'tt-tab--active': activeTab === t.safe }"
              :title="t.file" @click="selectTab(t.safe)">
        <span class="tt-tab-kind">{{ tabLabel(t) }}</span>
        <span class="tt-tab-state">
          <UiSpinner v-if="tabState[t.safe] === 'loading'" :size="10" />
          <span v-else-if="tabState[t.safe] === 'ready'">{{ (tabBlocks[t.safe] || []).length }}</span>
          <span v-else-if="tabState[t.safe] === 'error'">!</span>
          <span v-else class="tt-tab-dot">·</span>
        </span>
        <!-- scenes are a STORY.PAC concept; show fit/total only on the active tab that has them -->
        <span v-if="activeTab === t.safe && sceneStats.measured" class="tt-tab-scenes"
              :title="`${sceneStats.fit} of ${sceneStats.measured} scenes fit their byte budget · ${sceneStats.over} over`">
          {{ sceneStats.fit }}/{{ sceneStats.measured }} fit
        </span>
      </button>
      <button v-if="tabs.some(t => tabState[t.safe] === 'error' || tabState[t.safe] === 'idle')"
              class="tt-tab tt-tab-retry" title="Retry sources that didn't load" @click="retryTabs">
        ↻ Retry
      </button>
    </div>

    <!-- Speaker legend (only when the source carries speaker tags) -->
    <SpeakerLegend
      v-if="showLegend"
      :speakers="activeSpeakers"
      :names="activeNames"
      :pct="speakerPct"
      @rename="renameSpeaker"
    />

    <!-- Table -->
    <div class="tt-table-wrap" ref="scrollEl">
      <table class="tt-table">
        <thead>
          <tr>
            <th class="col-order" title="Disk / Story # — the scene's disk position and the story order you assign (floats up on save)">Disk/Story #</th>
            <th class="col-offset" title="Offset — the line's byte position on the disc">Offset</th>
            <th v-if="showLegend" class="col-speaker">Speaker</th>
            <th class="col-jp">Japanese</th>
            <th class="col-ca">{{ langLabel || 'Catalan' }} <span class="col-ca-pct">{{ tabProg.done.toLocaleString() }}/{{ tabProg.total.toLocaleString() }} <strong>({{ tabProg.pct }}%)</strong></span></th>
            <th class="col-bytes" :class="{ 'col-bytes-sorted': sortMode === 'overflow' }"
                title="Per-line bytes vs the original. Click to sort boxes by overflow (closest-to-fitting on top); click again for disc order."
                @click="toggleSortOverflow">
              Bytes <span class="col-bytes-sort">{{ sortMode === 'overflow' ? '▲ over' : '⇅' }}</span>
            </th>
            <th class="col-done" title="Mark handled — kept as original Japanese">Done</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="item in displayRows"
                    :key="item.kind === 'head' ? 'h' + item.scene : item.block.offset">
            <!-- Scene box: a collapsible header with the budget as used / available bytes -->
            <tr v-if="item.kind === 'head'"
                :class="['scene-head', sceneStatus(item.scene).state]"
                @click="toggleScene(item.scene)">
              <td class="col-order disk-story">
                <span class="scene-caret">{{ expanded.has(item.scene) ? '▾' : '▸' }}</span>
                <span class="scene-id mono">{{ item.scene }}/</span>
                <input class="order-input" type="number" min="1" placeholder="—"
                       :class="{ dup: sceneOrder(item.scene) != null && dupStoryOrders.has(sceneOrder(item.scene)!) }"
                       :value="sceneOrder(item.scene)" @change="setSceneOrder(item.scene, $event)" @click.stop
                       title="Story Scene number — unique; reorders scenes on save" />
              </td>
              <td class="col-offset mono">{{ item.offset }}</td>
              <td v-if="showLegend" class="col-speaker">
                <span class="scene-speakers">
                  <span v-for="sid in sceneInfo(item.scene).speakers" :key="sid"
                        class="speaker-dot" :style="{ background: speakerColor(sid) }" :title="speakerLabel(sid)" />
                </span>
              </td>
              <td class="col-jp scene-snippet">
                {{ sceneInfo(item.scene).firstJp }}<template v-if="sceneInfo(item.scene).lastJp && sceneInfo(item.scene).lastJp !== sceneInfo(item.scene).firstJp"> … {{ sceneInfo(item.scene).lastJp }}</template>
              </td>
              <td class="col-ca scene-snippet">
                {{ sceneInfo(item.scene).firstCa }}<template v-if="sceneInfo(item.scene).lastCa && sceneInfo(item.scene).lastCa !== sceneInfo(item.scene).firstCa"> … {{ sceneInfo(item.scene).lastCa }}</template>
              </td>
              <td class="col-bytes">
                <div class="bytes-cell" :class="sceneFill[item.scene] !== undefined ? sceneStatus(item.scene).state : ''">
                  <template v-if="sceneFill[item.scene] !== undefined">
                    <span class="bytes-used">{{ sceneStatus(item.scene).used.toLocaleString() }}</span>
                    <span class="bytes-sep">/</span>
                    <span class="bytes-budget">{{ item.slack.toLocaleString() }}</span>
                  </template>
                  <span v-else class="stat-skel" style="width:56px"></span>
                </div>
              </td>
              <td class="col-done"></td>
            </tr>
            <!-- A line within the scene -->
            <TranslationRow v-else
                :block="item.block" :show-legend="showLegend" :run-start="item.runStart"
                :cum="item.cum" :slack="item.slack" :dup-count="dupCount(item.block.jp)"
                :speaker-color="speakerColor(item.block.speakerId)"
                :speaker-label="speakerLabel(item.block.speakerId)"
                :kind="activeTabObj?.kind || 'dialogue'"
                @commit="onCaCommit" @propagate="propagate(item.block)" />
          </template>
        </tbody>
      </table>
    </div>
    </div><!-- /tt-main -->

      <!-- Collapsible Claude-prompt rail: a thin tab when closed, the copier when open -->
      <aside class="tt-rail" :class="{ 'tt-rail--open': railOpen }">
        <button class="tt-rail-tab" :title="railOpen ? 'Hide prompt' : 'Claude translation prompt'" @click="toggleRail">
          {{ railOpen ? '›' : 'Automatic Translation' }}
        </button>
        <div class="tt-rail-body">
          <PromptCopier
            :title="selGameName"
            :target="langLabel || 'Català'"
            :file="activeFileName"
            :safe="activeTab"
            :kind-label="activeKindLabel"
            :ns="curNs"
            :api-base="API_BASE"
            :blocks="blocks"
            :speaker-names="activeNames"
            :model-value="toneLinks"
            @update:model-value="onToneLinks"
          />
        </div>
      </aside>
    </div><!-- /tt-body -->
    </template><!-- end v-else (table view) -->

    <!-- Build pre-flight warning: shown only when lines are pending and/or overflow -->
    <div v-if="showBuildWarn" class="tt-modal-backdrop" @click.self="showBuildWarn = false">
      <div class="tt-modal">
        <h3 class="tt-modal-title">Build with open issues?</h3>
        <ul class="tt-modal-list">
          <li v-if="stats.pending" class="tt-modal-item pending">
            <strong>{{ stats.pending.toLocaleString() }}</strong> lines aren't translated yet: they'll ship as the original Japanese.
          </li>
          <li v-if="stats.over" class="tt-modal-item over">
            <strong>{{ stats.over.toLocaleString() }}</strong> lines overflow the byte budget: they'll be truncated in-game until the expand/repack step exists.
          </li>
          <li v-if="stats.warn" class="tt-modal-item warn">
            <strong>{{ stats.warn.toLocaleString() }}</strong> lines run tight against the budget: worth a second look.
          </li>
        </ul>
        <p class="tt-modal-note">You can build anyway, just make sure you've got a plan for these before you ship it.</p>
        <div class="tt-modal-actions">
          <UiButton @click="showBuildWarn = false">Cancel</UiButton>
          <UiButton variant="primary" @click="proceedBuild">Build anyway</UiButton>
        </div>
      </div>
    </div>

  </div>
</template>

<!-- NOT scoped: the table's cell/row classes (tt-*, col-*, ca-*, bytes-*, box-*, speaker-*, .mono)
     are unique to this workbench and are shared with the TranslationRow child, which renders its
     own <tr>. Scoping would strip the child's styling. (.mono also exists in Robutek but its own
     scoped rule wins there.) -->
<style src="./TranslationTable.css"></style>
