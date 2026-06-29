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

const route  = useRoute()
const router = useRouter()

// Experimental disclaimer: dismissible for the session (sessionStorage).
const disclaimerDismissed = ref(sessionStorage.getItem('cpc.translate.disclaimer') === '1')
function dismissDisclaimer() {
  disclaimerDismissed.value = true
  sessionStorage.setItem('cpc.translate.disclaimer', '1')
}

interface Block {
  offset: string
  speakerId: number
  jp: string
  jpBytes: number
  ca: string
  scene?: number       // which scenario (box) this line lives in — drives the box budget
  order?: number       // translator's story order; floats this block up on save (API _order_key)
  done?: boolean       // marked handled / keep-as-original (counts as done, no translation)
  note?: string
}

const blocks = ref<Block[]>([
  { offset: '0x000A48', speakerId: 1, jp: 'なんか力が出ない…', jpBytes: 18, ca: 'No tinc forces…' },
  { offset: '0x000A64', speakerId: 1, jp: 'はやっぱりねてよう…', jpBytes: 20, ca: 'Millor me\'n vaig a dormir…' },
  { offset: '0x000A96', speakerId: 1, jp: 'ドラやきが　なくなってきたな…', jpBytes: 30, ca: 'Se m\'acaben els dorayakis…' },
  { offset: '0x000ABA', speakerId: 1, jp: 'ママのお手伝いをして　ドラやきを', jpBytes: 32, ca: 'He d\'ajudar la mama per aconseguir dorayakis', note: 'Consecutive with next block — treat as one unit' },
  { offset: '0x000ADC', speakerId: 1, jp: 'ふやさなきゃ！！', jpBytes: 16, ca: 'Vull més dorayakis!!' },
  { offset: '0x000B32', speakerId: 1, jp: 'あ！　ドラやき！！', jpBytes: 18, ca: 'Ah! Un dorayaki!!' },
  { offset: '0x000B62', speakerId: 1, jp: 'やったね♪', jpBytes: 10, ca: 'Genial♪' },
  { offset: '0x000B6E', speakerId: 1, jp: 'もらっちゃおう〜', jpBytes: 16, ca: 'Me\'l quedo~' },
  { offset: '0x000BC0', speakerId: 1, jp: 'あ！！　ドラやきが　なくなった！？', jpBytes: 34, ca: 'Ah!! S\'ha acabat el dorayaki!?' },
  { offset: '0x000C3E', speakerId: 1, jp: 'ぼくは　ドラやきが　ないと', jpBytes: 26, ca: 'Sense dorayaki' },
  { offset: '0x000C5C', speakerId: 1, jp: 'も　やる気が　おきないんだ！！！', jpBytes: 32, ca: 'no tinc cap motivació!!!' },
  { offset: '0x000D08', speakerId: 9, jp: 'お兄ちゃん！　元気？', jpBytes: 20, ca: 'Germà! Com estàs?' },
  { offset: '0x000D68', speakerId: 9, jp: 'セワシくんと　タイムテレビで', jpBytes: 28, ca: 'Estava parlant amb en Sewashi' },
  { offset: '0x000D88', speakerId: 9, jp: 'ていたんだけど……', jpBytes: 18, ca: 'per la tele del temps……' },
  { offset: '0x000E50', speakerId: 9, jp: 'お兄ちゃん　のび太さんに', jpBytes: 24, ca: 'El Nobita, germà,' },
  { offset: '0x000E6A', speakerId: 9, jp: 'ぜんぜん　しんらいされていないわよ', jpBytes: 34, ca: 'no et té gens de confiança' },
  { offset: '0x000E96', speakerId: 1, jp: 'えぇ！！　ホントかい！？', jpBytes: 24, ca: 'Ei!! De veritat!?' },
  { offset: '0x000EB8', speakerId: 9, jp: 'のび太さんの　良いところを', jpBytes: 26, ca: 'Fes treure el millor del Nobita' },
  { offset: '0x000ED4', speakerId: 9, jp: 'のばして　あげないと', jpBytes: 20, ca: 'i ajudar-lo a créixer' },
])

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

// The game's font is FULL-WIDTH Shift-JIS: every character costs 2 bytes, and
// accents fold to base Latin (à→a, the stock font has no accented glyphs). So the
// real ROM cost is 2 * (folded char count) — NOT the UTF-8 length, which ran ~half.
function caBytes(text: string) {
  const folded = text.normalize('NFD').replace(/[̀-ͯ]/g, '')
  return folded.length * 2
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
    const res = await fetch(
      `${API_BASE}/translate/measure?path=${encodeURIComponent(path)}&file=${encodeURIComponent(tab)}`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ blocks: blocks.value.map(b => ({ offset: b.offset, ca: b.ca, jpBytes: b.jpBytes })) }) })
    const data = await res.json()
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
  return blocks.value.find(x => (x.scene ?? 0) === scene && x.order != null)?.order
}
function setSceneOrder(scene: number, ev: Event) {
  const raw = (ev.target as HTMLInputElement).value
  const n = raw === '' ? undefined : Number(raw)
  for (const b of blocks.value) if ((b.scene ?? 0) === scene) b.order = n
  saveState()
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

const LANGUAGES = [
  { code: 'ca', label: 'Català' },
  { code: 'es', label: 'Español' },
  { code: 'en', label: 'English' },
  { code: 'fr', label: 'Français' },
  { code: 'de', label: 'Deutsch' },
  { code: 'pt', label: 'Português' },
  { code: 'it', label: 'Italiano' },
]

type Step = 'pick' | 'table'
const step = ref<Step>('pick')

async function saveState() {
  if (!curNs.value || !activeTab.value) return
  try {
    // Per-source: the API deep-merges, so saving the active tab keeps the others.
    await fetch(`${API_BASE}/translate/${encodeURIComponent(curNs.value)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sources: { [activeTab.value]: blocks.value }, sceneBudget: sceneSlackByTab.value }),
    })
  } catch { /* offline — edits stay local */ }
}

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
  saveState()
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
    const res  = await fetch(`${API_BASE}/translate/projects`)
    const data = await res.json()
    projects.value = (data.projects as Project[]) || []
    // Projects saved before metadata existed have a path but no meta — backfill it
    // (instant IP.BIN read) so the whole list gets rich cards, and persist it once.
    for (const p of projects.value) if (!p.meta && p.path) backfillProjectMeta(p.ns, p.path)
  } catch { /* leave list as-is */ }
}

async function backfillProjectMeta(ns: string, path: string) {
  try {
    const res  = await fetch(`${API_BASE}/translate/meta?path=${encodeURIComponent(path)}`)
    const data = await res.json()
    if (!data.meta) return
    projects.value = projects.value.map(p => (p.ns === ns ? { ...p, meta: data.meta } : p))
    fetch(`${API_BASE}/translate/${encodeURIComponent(ns)}`, {     // persist so it's a one-time cost
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ meta: data.meta }),
    }).catch(() => {})
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
    await fetch(`${API_BASE}/translate/${encodeURIComponent(ns)}`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      // NB: no `total` here on purpose — persistTotal() is the sole writer of the
      // aggregate, so the create POST can't clobber it back to the primary count.
      body:    JSON.stringify({ gameName, lang: selLang.value, system: selSystem.value,
                                path: selGame.value, meta: meta.value,
                                sources: { [primarySafe]: tabBlocks.value[primarySafe] || [] } }),
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
    const res  = await fetch(`${API_BASE}/translate/${encodeURIComponent(ns)}`)
    const data = await res.json()
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

watch(tabBlocks, () => {
  clearTimeout(statsTimer)
  statsTimer = setTimeout(() => { recomputeStats(); recomputeTabPct(); measureScenes(); recomputeSceneInfo() }, 300)
}, { deep: true })
watch(activeTab, recomputeTabPct, { immediate: true })


// ── Scene accordion ────────────────────────────────────────────────────────────
// The dialogue is grouped into scenario "boxes" the engine packs text into. Each is a
// bordered, collapsible section so the translator works one scene at a time. Collapsed by
// default: opening a project shows a clean scene index (~76 headers), not 7.6k rows, which
// also means no virtual-scroll machinery is needed (a collapsed scene is one header row).
const scrollEl = ref<HTMLElement | null>(null)
const expanded = ref<Set<number>>(new Set())     // which scenes are open (empty = all collapsed)
function toggleScene(scene: number) {
  const next = new Set(expanded.value)
  if (next.has(scene)) next.delete(scene); else next.add(scene)
  expanded.value = next
}
type Disp =
  | { kind: 'head'; scene: number; slack: number; offset: string }
  | { kind: 'row'; block: Block; index: number; cum: number; slack: number }
// Flat render list: each scene's header (carrying its start offset), then (only if expanded) its
// rows. Reads scene/identity, not ca text, so editing a translation never rebuilds it.
const displayRows = computed<Disp[]>(() => {
  const arr = blocks.value
  // Group blocks into scenes (disc order within each), then order the SCENES by the Story # you
  // assign: numbered scenes float to the top ascending, the rest stay in disc order. Reads
  // `order`/`scene`, not ca text, so this re-sorts when you set a Story # but not while translating.
  type G = { scene: number; order: number | null; slack: number; offset: string; rows: { block: Block; index: number }[] }
  const byScene = new Map<number, G>()
  const groups: G[] = []
  for (let i = 0; i < arr.length; i++) {
    const b = arr[i]
    const sc = b.scene ?? 0
    let g = byScene.get(sc)
    if (!g) {
      g = { scene: sc, order: b.order ?? null, slack: sceneSlack.value[sc] ?? 0, offset: b.offset, rows: [] }
      byScene.set(sc, g); groups.push(g)
    }
    if (g.order == null && b.order != null) g.order = b.order
    g.rows.push({ block: b, index: i })
  }
  groups.sort((a, b) => {
    if (a.order != null && b.order != null) return a.order - b.order
    if (a.order != null) return -1
    if (b.order != null) return 1
    return a.scene - b.scene
  })
  const out: Disp[] = []
  for (const g of groups) {
    out.push({ kind: 'head', scene: g.scene, slack: g.slack, offset: g.offset })
    if (expanded.value.has(g.scene)) {
      let cum = 0
      // running box usage in disc order, so each row shows how full the box is up to (and incl.) it
      for (const r of g.rows) {
        cum += blockExp.value[r.block.offset] || 0
        out.push({ kind: 'row', block: r.block, index: r.index, cum, slack: g.slack })
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
})


// Disc metadata (IP.BIN) for the header card — instant (~74ms), fetched on open.
const meta = ref<GameMeta | null>(null)
async function fetchMeta(path: string) {
  meta.value = null
  try {
    const res  = await fetch(`${API_BASE}/translate/meta?path=${encodeURIComponent(path)}`)
    const data = await res.json()
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
    await fetch(`${API_BASE}/translate/${encodeURIComponent(curNs.value)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ speakers: { [activeTab.value]: speakerNames.value[activeTab.value] || {} } }),
    })
  } catch { /* offline — names stay local */ }
}

const KIND_LABEL: Record<string, string> = {
  dialogue: 'Dialogue', menu: 'Menu', items: 'Items', ui: 'UI',
  chat: 'Chat', secret: 'Secret', readme: 'Readme', text: 'Text',
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
    await fetch(`${API_BASE}/translate/${encodeURIComponent(curNs.value)}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ toneLinks: toneLinks.value }),
    })
  } catch { /* offline — links stay local */ }
}
// The active source, named for the prompt (kind label + on-disc filename).
const activeTabObj   = computed(() => tabs.value.find(t => t.safe === activeTab.value))
const activeKindLabel = computed(() => { const t = activeTabObj.value; return t ? (KIND_LABEL[t.kind] || t.kind) : 'Text' })
const activeFileName  = computed(() => { const f = activeTabObj.value?.file || ''; return f.split(/[\\/]/).pop() || f })
// While the rail is open, keep the active source persisted in state.json.sources so
// the prompt's GET (json in) actually finds it — Claude reads + writes the same key.
watch([railOpen, activeTab], () => {
  if (railOpen.value && curNs.value && activeTab.value && blocks.value.length) saveState()
})
function mapBlocks(raw: { offset: number; jpBytes: number; hex: string; speaker: number; scene?: number }[]): Block[] {
  return (raw || []).map(b => ({
    offset:    '0x' + b.offset.toString(16).toUpperCase().padStart(6, '0'),
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
    const res = await fetch(`${API_BASE}/translate/sources?path=${encodeURIComponent(path)}`)
    srcs = ((await res.json()).sources as SourceTab[]) || []
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
    await fetch(`${API_BASE}/translate/${encodeURIComponent(curNs.value)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ total: stats.value.total }),
    })
    loadProjects()   // refresh the list so the card reflects the new aggregate
  } catch { /* offline — list keeps the old count */ }
}

async function loadTab(safe: string) {
  if (tabState.value[safe] === 'loading' || tabState.value[safe] === 'ready') return
  // reassign the whole object so the update reliably triggers re-render (a per-key
  // mutation was arriving but not rendering until a refresh).
  tabState.value = { ...tabState.value, [safe]: 'loading' }
  try {
    const res  = await fetch(`${API_BASE}/translate/extract?path=${encodeURIComponent(curPath.value)}&file=${encodeURIComponent(safe)}`)
    const data = await res.json()
    // Reconcile: the fresh extract carries `scene` + jpBytes; overlay any saved draft's
    // ca/order/done onto it by offset, so re-extracting to gain scene tags never loses work.
    const fresh = mapBlocks(data.blocks)
    const prior = tabBlocks.value[safe]
    if (prior && prior.length) {
      const byOff = new Map(prior.map(b => [b.offset, b]))
      for (const b of fresh) {
        const s = byOff.get(b.offset)
        if (s) { b.ca = s.ca || ''; b.order = s.order; b.done = s.done ?? b.done }   // keep extract's done (artifacts) if the draft has none
      }
    }
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
async function saveDraft() {
  clearTimeout(speakerSaveTimer)                       // flush pending speaker edits now
  await Promise.all([saveState(), saveSpeakers()])     // blocks + speaker names
  draftSaved.value = true
  setTimeout(() => { draftSaved.value = false }, 1800)
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
    const res  = await fetch(`${API_BASE}/translate/run`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body:   JSON.stringify({ path: curPath.value }),
    })
    const data = await res.json()
    if (data.error) {
      buildFailed.value = true
      buildMsg.value = `Build failed: ${data.error}`.slice(0, 80)
    } else {
      const secs = Math.round((Date.now() - startedAt) / 1000)
      unlock(`ROM Built — ${selGameName.value || 'game'}`, `${secs}s`)
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
  fetch(`${API_BASE}/translate/open`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ ns: p.ns }),
  })
}

function langName(code: string) {
  return LANGUAGES.find(l => l.code === code)?.label || code
}

function deleteProject(p: Project) {
  if (!confirm(`Delete the ${p.gameName} (${langName(p.lang)}) project? This removes its saved table.`)) return
  fetch(`${API_BASE}/translate/delete`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ ns: p.ns }),
  }).then(() => loadProjects())
}

function backToProjects() {
  router.push('/translation')
}

async function loadSystems() {
  pickError.value = ''
  try {
    const res  = await fetch(`${API_BASE}/translate/systems`)
    const data = await res.json()
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
    const res  = await fetch(`${API_BASE}/translate/games?system=${encodeURIComponent(selSystem.value)}`)
    const data = await res.json()
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
  const ae = document.activeElement as HTMLElement | null
  if (ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA')) return
  const ns = curNs.value
  try {
    const res  = await fetch(`${API_BASE}/translate/${encodeURIComponent(ns)}`)
    const data = await res.json()
    if (ns !== curNs.value || !data || !data.sources) return     // navigated away mid-fetch
    const src = data.sources as Record<string, Block[]>
    for (const safe of Object.keys(tabBlocks.value)) {
      const local = tabBlocks.value[safe], remote = src[safe]
      if (!remote || !local || remote.length !== local.length) continue
      for (let i = 0; i < local.length; i++) {
        if (local[i].ca !== remote[i].ca) local[i].ca = remote[i].ca
      }
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
          <UiButton class="tt-action" :disabled="building || extracting" @click="saveDraft">{{ draftSaved ? 'Saved ✓' : 'Save draft' }}</UiButton>
          <UiButton variant="primary" :loading="building" :disabled="extracting" loading-text="Building…" @click="confirmBuild">Build ROM</UiButton>
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
            <th class="col-bytes" title="Per-line bytes vs the original — informational">Bytes</th>
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
                <span class="scene-id mono">{{ item.scene + 1 }}/</span>
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
            <tr v-else
                :class="['tt-row', 'scene-body', { 'run-start': isFirstInRun(item.index), 'run-cont': !isFirstInRun(item.index) }]">
              <td class="col-order"></td>
              <td class="col-offset mono">{{ item.block.offset }}</td>

              <td v-if="showLegend" class="col-speaker">
                <template v-if="isFirstInRun(item.index)">
                  <div class="speaker-cell">
                    <span class="speaker-dot" :style="{ background: speakerColor(item.block.speakerId) }" />
                    <span class="speaker-name">{{ speakerLabel(item.block.speakerId) }}</span>
                  </div>
                </template>
                <div v-else class="speaker-cont">
                  <span class="speaker-cont-line" :style="{ background: speakerColor(item.block.speakerId) }" />
                </div>
              </td>

              <td class="col-jp">
                <span class="jp-text">{{ item.block.jp }}</span>
                <span v-if="item.block.note" class="block-note" :title="item.block.note">⚠</span>
              </td>

              <td class="col-ca">
                <div class="ca-cell">
                  <textarea class="ca-input" v-model="item.block.ca" rows="2" @change="saveState" />
                  <button v-if="dupCount(item.block.jp) > 1" class="ca-prop" type="button"
                          :title="`Copy this Catalan into all ${dupCount(item.block.jp)} identical lines`"
                          @click="propagate(item.block)">propagate to {{ dupCount(item.block.jp) }}</button>
                </div>
              </td>

              <td class="col-bytes">
                <!-- the line's own size vs its Japanese (neutral reference) -->
                <div class="bytes-cell">
                  <span class="bytes-used">{{ caBytes(item.block.ca) }}</span>
                  <span class="bytes-sep">/</span>
                  <span class="bytes-budget">{{ item.block.jpBytes }}</span>
                </div>
                <!-- cumulative box fill to this line: bar + running aggregate; over where it exceeds slack -->
                <div class="box-agg" :class="{ over: item.cum > item.slack }"
                     :title="`box used to here: ${item.cum.toLocaleString()} / ${item.slack.toLocaleString()} B`">
                  <span class="box-agg-label">Agg</span>
                  <span class="box-progress">
                    <span class="box-progress-fill"
                          :style="{ width: Math.min(100, item.slack ? item.cum / item.slack * 100 : 0) + '%' }"></span>
                  </span>
                </div>
              </td>

              <td class="col-done">
                <input type="checkbox" v-model="item.block.done" @change="saveState"
                       title="Done — keep original Japanese" />
              </td>
            </tr>
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

<style scoped>
.tt-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--surface-2);
  font-family: var(--font-sans);
}

.tt-disclaimer {
  display: flex; align-items: center; gap: 10px;
  background: linear-gradient(135deg, rgba(255, 193, 7, 0.12), rgba(244, 67, 54, 0.12));
  border: 1px solid rgba(255, 152, 0, 0.4);
  border-radius: var(--r-sm);
  margin: var(--sp-3); padding: 6px 12px;
  flex-shrink: 0; font-size: 12.5px; color: var(--text-muted);
}
.tt-disclaimer-text { flex: 1; }
.tt-disclaimer-text strong { color: rgb(217, 119, 6); font-weight: 600; }
/* layout only — the close look comes from UiClose */
.tt-disclaimer-x { flex-shrink: 0; }

.tt-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-3) var(--sp-5);
  background: var(--surface);
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}

.tt-title {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: 14px;
}

.tt-game { font-weight: 600; color: var(--text); }
.tt-sep  { color: var(--text-faint); }
.tt-lang { color: var(--text-muted); }
.tt-count { color: var(--text-faint); font-family: var(--font-mono); font-size: 12px; }
.tt-actions { display: inline-flex; align-items: center; gap: 8px; margin-left: 16px; }
.tt-build-msg { font-size: 12px; color: var(--text-faint); }
.tt-build-msg--fail { color: var(--bad); font-weight: 600; }

.tt-stats {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: 12px;
  font-family: var(--font-mono);
}
.tt-total { color: var(--text-muted); margin-right: var(--sp-1); }

.stat { padding: 2px 6px; border-radius: var(--r-sm); font-weight: 500; }
.stat.pending { background: #dbeafe; color: #2563eb; }
.stat.ok   { background: #dcfce7; color: var(--ok); }
.stat.warn { background: #fef3c7; color: var(--warn); }
.stat.over { background: #fee2e2; color: var(--bad); }
.stat.muted { color: var(--text-faint); padding: 0; }
.stat-sep { color: var(--line-strong); }

/* Skeleton bars for the header stats while the disc scans / tabs extract (no flashing counts). */
.stat-skel {
  display: inline-block; height: 14px; border-radius: 7px;
  margin-right: var(--sp-2); background: var(--line);
  animation: tt-skel 1.2s ease-in-out infinite;
}
@keyframes tt-skel { 0%, 100% { opacity: 0.45; } 50% { opacity: 0.85; } }

/* Source tabs (one per discovered file) */
.tt-tabs {
  display: flex; flex-wrap: wrap; gap: 6px;
  margin-top: 16px; padding-bottom: 12px; margin-bottom: 4px; margin-left: 4px;
  border-bottom: 1px solid var(--line);
}
.tt-tab {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 6px 12px; border: 1px solid var(--line); border-radius: var(--r-sm);
  background: var(--surface); color: var(--text-faint); cursor: pointer;
  font-size: 13px; transition: background .1s, border-color .1s, color .1s;
}
.tt-tab:hover { background: var(--surface-2); border-color: var(--line-strong); }
.tt-tab--active {
  color: var(--text); border-color: var(--accent);
  box-shadow: inset 0 -2px 0 var(--accent);
}
.tt-tab-kind { font-weight: 600; }
.tt-tab-state {
  font-family: var(--font-mono); font-size: 11px;
  color: var(--text-faint); min-width: 14px; text-align: right;
}
.tt-tab-dot { color: var(--line-strong); }
/* scene fit/total badge, shown only on the active tab that has scenes (STORY.PAC) */
.tt-tab-scenes {
  font-family: var(--font-mono); font-size: 11px;
  padding-left: 8px; margin-left: 6px; border-left: 1px solid var(--line-strong);
  color: var(--text-muted);
}
/* spinners are now UiSpinner */

.tt-discovering-note {
  display: flex; align-items: center; gap: 10px;
  padding: 16px 4px; color: var(--text-faint); font-size: 13px;
}

/* Table-page body: main work area + collapsible Claude-prompt rail */
/* The prompt rail OVERLAYS the table (absolute + slide), so opening it never
   reflows / re-renders the 7k-row table. The tab rides the panel's left edge. */
.tt-body { position: relative; display: flex; flex: 1; min-height: 0; overflow: hidden; }
.tt-main { flex: 1; min-width: 0; display: flex; flex-direction: column; min-height: 0; }
.tt-rail {
  position: absolute; top: 0; right: 0; bottom: 0;
  width: 360px; max-width: 80%; z-index: 6;
  background: var(--surface);            /* opaque — the table must not show through */
  transform: translateX(100%);
  transition: transform 0.22s ease;
}
.tt-rail--open { transform: translateX(0); box-shadow: -10px 0 30px rgba(0, 0, 0, 0.14); }
.tt-rail-tab {
  position: absolute; right: 100%; top: 50%; transform: translateY(-50%);
  width: 34px; padding: 18px 0;
  writing-mode: vertical-rl; text-orientation: mixed;
  background: var(--accent); border: none; border-radius: 8px 0 0 8px;
  cursor: pointer; color: #fff; font-size: 12px; font-weight: 600; letter-spacing: 0.06em;
  box-shadow: -2px 0 10px rgba(0, 0, 0, 0.12); transition: filter 0.1s;
}
.tt-rail-tab:hover { filter: brightness(1.08); }
.tt-rail--open .tt-rail-tab {
  writing-mode: horizontal-tb; width: 28px; padding: 8px 0;
  font-size: 18px; font-weight: 400;   /* stays terracotta, just the collapse chevron */
}
.tt-rail-body {
  height: 100%; box-sizing: border-box;
  padding: var(--sp-3); overflow-y: auto;
  border-left: 1px solid var(--line); background: var(--surface);
}

.tt-table-wrap {
  flex: 1;
  overflow-y: auto;
}

.tt-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  table-layout: fixed;   /* stable column widths while only a window of rows renders */
}

/* Virtual-scroll spacers: empty rows that pad the scroll height above/below the window */
.tt-spacer td { padding: 0; border: 0; }

.tt-table thead th {
  position: sticky;
  top: 0;
  background: var(--surface);
  border-bottom: 1px solid var(--line-strong);
  padding: var(--sp-2) var(--sp-3);
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  z-index: 1;
}

.tt-row {
  height: 58px;            /* fixed + uniform so the virtual-scroll math stays exact */
  border-bottom: 1px solid var(--line);
  background: var(--surface);
  transition: background 0.1s;
}
.tt-row:hover { background: var(--surface-2); }
.tt-row.ok   { border-left: 2px solid transparent; }
.tt-row.warn { border-left: 2px solid var(--warn); }
.tt-row.over { border-left: 2px solid var(--bad); }

.tt-row td {
  padding: var(--sp-2) var(--sp-3);
  vertical-align: top;
  overflow: hidden;        /* clip overflow to the fixed row height */
}

.col-offset { width: 100px; }
.col-speaker { width: 160px; }
.col-jp { width: 30%; }
.col-ca { width: 35%; }
.col-ca-pct { font-weight: 400; color: var(--text-muted); font-family: var(--font-mono); font-size: 12px; font-variant-numeric: tabular-nums; }
.col-bytes { width: 84px; }
.col-done { width: 44px; text-align: center; }
.col-done input { cursor: pointer; }

/* Disk/Story # column: the scene header shows disk# / story-input ("1/[5]"); rows leave it blank. */
.col-order { width: 92px; }
.disk-story { display: flex; align-items: center; gap: 4px; white-space: nowrap; }
.order-input {
  width: 44px; padding: 2px 4px; text-align: center;
  border: 1px solid var(--line); border-radius: 4px;
  background: var(--surface); color: var(--text);
  font-family: var(--font-mono); font-size: 12px; font-variant-numeric: tabular-nums;
}
.order-input::placeholder { color: var(--text-faint); }
.order-input.dup { border-color: var(--bad); color: var(--bad); }   /* duplicate story number */

/* Scene accordion — the header row mirrors the columns: id, speakers, JP/CA snippets, budget. */
.scene-head { cursor: pointer; border-top: 2px solid var(--line-strong); background: var(--surface-2, var(--surface)); }
.scene-head:hover { filter: brightness(0.985); }
.scene-head td { padding: var(--sp-2) var(--sp-3); vertical-align: middle; }
.scene-caret { color: var(--text-muted); font-size: 11px; }
.scene-id { font-weight: 600; color: var(--text); font-size: 12px; }
.scene-speakers { display: flex; gap: 4px; flex-wrap: wrap; }
/* First … last line preview, clipped to the row height. */
.scene-snippet {
  color: var(--text-muted); font-size: 12px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%;
}
/* Budget colour + a left rail so each scene reads as a bordered box. */
.scene-head.ok   { border-left: 3px solid var(--ok); }
.scene-head.warn { border-left: 3px solid var(--warn); }
.scene-head.over { border-left: 3px solid var(--bad); }
.tt-row.scene-body td:first-child { border-left: 3px solid var(--line); }

/* Keep the whole table clear of the floating "Automatic Translation" rail tab on the right.
   Margin on the table area shifts the header and rows together — no internal misalignment. */
.tt-table-wrap { margin-right: 34px; }

/* Build pre-flight warning modal */
.tt-modal-backdrop {
  position: fixed; inset: 0; z-index: 50;
  background: rgba(15, 23, 42, 0.45);
  display: flex; align-items: center; justify-content: center;
}
.tt-modal {
  background: var(--surface); border: 1px solid var(--line-strong);
  border-radius: var(--r-md); box-shadow: 0 20px 50px rgba(0,0,0,0.25);
  padding: var(--sp-4); width: min(460px, 92vw);
}
.tt-modal-title { margin: 0 0 var(--sp-3); font-size: 15px; font-weight: 600; color: var(--text); }
.tt-modal-list { list-style: none; margin: 0 0 var(--sp-3); padding: 0; display: flex; flex-direction: column; gap: var(--sp-2); }
.tt-modal-item { font-size: 13px; color: var(--text); padding-left: var(--sp-3); border-left: 3px solid var(--line); }
.tt-modal-item.pending { border-left-color: #2563eb; }
.tt-modal-item.over    { border-left-color: var(--bad); }
.tt-modal-item.warn    { border-left-color: var(--warn); }
.tt-modal-note { margin: 0 0 var(--sp-4); font-size: 12.5px; color: var(--text-muted); }
.tt-modal-actions { display: flex; justify-content: flex-end; gap: var(--sp-2); }

.mono { font-family: var(--font-mono); font-size: 11px; color: var(--text-faint); }

/* Speaker */
.speaker-cell {
  display: flex;
  align-items: center;
  gap: var(--sp-1);
  flex-wrap: wrap;
}
.speaker-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.speaker-info {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.speaker-name {
  font-weight: 500;
  color: var(--text);
  font-size: 12px;
}
.speaker-suggestion {
  font-size: 10px;
  color: var(--text-faint);
  font-style: italic;
}
.run-count {
  font-size: 10px;
  color: var(--text-faint);
  font-family: var(--font-mono);
  margin-top: 2px;
  padding-left: 14px;
}
.speaker-cont {
  display: flex;
  align-items: stretch;
  height: 100%;
  padding: 0 0 0 3px;
}
.speaker-cont-line {
  width: 2px;
  border-radius: 1px;
  opacity: 0.3;
  min-height: 24px;
  display: block;
}
.tt-row.run-start { border-top: 1px solid var(--line-strong); }
.tt-row.run-cont  { border-top: 1px solid transparent; }
.speaker-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  border: none;
  cursor: pointer;
  font-family: var(--font-mono);
  transition: opacity 0.1s;
}
.speaker-badge.inferred {
  background: #fef3c7;
  color: #92400e;
}
.speaker-badge.unconfirmed {
  background: var(--surface-3);
  color: var(--text-faint);
}
.speaker-badge.confirmed {
  background: #dcfce7;
  color: #166534;
  cursor: default;
}
.speaker-badge.rejected {
  background: #fee2e2;
  color: var(--bad);
  cursor: default;
}
.thumb-btn {
  background: none;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  cursor: pointer;
  font-size: 12px;
  padding: 1px 4px;
  line-height: 1;
  transition: border-color 0.1s;
}
.thumb-btn:hover { border-color: var(--accent); }
.rejected-suggestion {
  text-decoration: line-through;
  color: var(--bad);
  opacity: 0.6;
}

/* JP */
.jp-text {
  color: var(--text);
  line-height: 1.5;
}
.block-note {
  margin-left: var(--sp-1);
  color: var(--warn);
  cursor: help;
  font-size: 12px;
}

/* CA input */
.ca-cell {
  display: flex;
  gap: var(--sp-1);
  align-items: flex-start;
}
/* Propagate-to-identical button: shows the duplicate count; fills all copies with this Catalan. */
.ca-prop {
  flex: none; align-self: stretch;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--font-mono); font-size: 11px; line-height: 1.2;
  padding: 2px 10px; border: 1px solid var(--line-strong); border-radius: var(--r-sm);
  background: var(--surface); color: var(--text-muted); cursor: pointer; white-space: nowrap;
}
.ca-prop:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-weak, var(--surface)); }
.ca-input {
  flex: 1;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  padding: var(--sp-1) var(--sp-2);
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text);
  background: var(--surface);
  resize: none;            /* fixed height keeps rows uniform for virtual scroll; long text scrolls inside */
  height: 42px;
  min-height: 0;
  line-height: 1.5;
  transition: border-color 0.1s;
}
.ca-input:focus {
  outline: none;
  border-color: var(--accent);
}
/* layout only — the bordered look comes from UiIconButton */
.suggest-btn { flex-shrink: 0; }

/* Bytes */
.bytes-cell {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);          /* per-line = a neutral reference, not a verdict */
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px 6px;
  border-radius: var(--r-sm);
  width: fit-content;
}
/* (the coloured variants below are for the SCENE-HEAD budget cell, which carries the box verdict) */
.bytes-cell.pending { background: #eff6ff; color: #2563eb; }
.bytes-cell.ok   { background: #dcfce7; color: var(--ok); }
.bytes-cell.warn { background: #fef3c7; color: var(--warn); }
.bytes-cell.over { background: #fee2e2; color: var(--bad); }

/* Cumulative box fill under each line: how full the scene's slack is up to (and incl.) this line,
   as a bar + a running aggregate number. Grows as you go down; turns red on the line where the scene
   crosses its slack = trim above here. */
.box-agg { display: flex; align-items: center; gap: 4px; margin-top: 3px; }
.box-progress { flex: none; height: 3px; width: 34px; border-radius: 2px; background: var(--line); overflow: hidden; }
.box-progress-fill { display: block; height: 100%; background: var(--ok); transition: width 0.2s ease; }
.box-agg-label { font-size: 9px; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-faint); }
.box-agg.over .box-progress-fill { background: var(--bad); }
.box-agg.over .box-agg-label { color: var(--bad); }
.bytes-sep { opacity: 0.5; }
.bytes-budget { opacity: 0.7; }

/* ── Discovering step ── */
.tt-discovering {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
  padding: 48px 24px;
  max-width: 560px;
  margin: 0 auto;
}
.tt-checklist {
  list-style: none;
  margin: 0 0 20px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.tt-checklist-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: var(--text-faint);
}
.tt-checklist-item--done   { color: var(--text); }
.tt-checklist-item--active { color: var(--text); }
.tt-checklist-icon {
  width: 18px; height: 18px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.tt-check       { color: var(--ok); font-size: 14px; font-weight: 700; }
.tt-check-empty {
  display: inline-block;
  width: 10px; height: 10px;
  border: 1.5px solid var(--line-strong);
  border-radius: 50%;
}
.tt-translating {
  display: flex; align-items: center; gap: 10px;
  font-size: 14px; opacity: 0.85;
}
.tt-scanning {
  display: flex; align-items: center; justify-content: center; gap: 12px;
  padding: 80px 24px; color: var(--text-muted); font-size: 14px;
}
.tt-translate-ok {
  margin: 0;
  padding: 12px 14px;
  border: 1px solid #2e7d32;
  border-radius: var(--r);
  background: rgba(46, 125, 50, 0.08);
  font-size: 13px; line-height: 1.5;
}
.tt-translate-ok code {
  font-family: var(--mono, monospace); font-size: 12px;
  word-break: break-all;
}
.tt-quick-build { margin-top: 4px; opacity: 0.65; font-size: 12px; }
.tt-projects { margin-top: 28px; width: 100%; max-width: 440px; text-align: left; }
.tt-projects-heading {
  font-size: 12px; color: var(--text-faint);
  text-transform: uppercase; letter-spacing: 0.05em; margin: 0 0 10px;
}
.tt-proj-group { margin-bottom: 10px; }
.tt-proj-group-head {
  display: flex; align-items: center; gap: 8px; width: 100%;
  padding: 4px 2px; margin-bottom: 6px;
  background: none; border: none; cursor: pointer; text-align: left;
}
.tt-proj-caret { color: var(--text-faint); font-size: 10px; width: 10px; }
.tt-proj-group-name { font-size: 13px; font-weight: 600; color: var(--text); }
.tt-proj-group-count {
  font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);
  background: var(--surface-2); border-radius: 999px; padding: 1px 8px;
}
.tt-projects-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
/* the card IS the row: balanced, clickable, actions revealed on hover */
.tt-project {
  position: relative; display: flex; align-items: center;
  border: 1px solid var(--line); border-radius: var(--r-sm);
  background: var(--surface); transition: background 0.1s, border-color 0.1s;
}
.tt-project:hover { background: var(--surface-2); border-color: var(--line-strong); }
.tt-project-open {
  flex: 1; min-width: 0; display: flex; align-items: center; gap: 12px;
  padding: 8px 12px; background: none; border: none; cursor: pointer; text-align: left;
}
.tt-proj-card { flex: 1; min-width: 0; }
.tt-project-count {
  flex-shrink: 0;     /* no margin-left:auto — it would starve the card's flex-grow */
  font-size: 12px; color: var(--text-faint); font-family: var(--font-mono); white-space: nowrap;
  transition: opacity 0.1s;
}
.tt-project:hover .tt-project-count { opacity: 0; }   /* yield to the actions on hover */
/* Actions overlay the right edge — ABSOLUTE so they reserve no layout space
   (in-flow opacity:0 was stealing ~70px, squeezing the card to half the row). */
.tt-project-actions {
  position: absolute; right: 12px; top: 50%; transform: translateY(-50%);
  display: flex; gap: 4px;
  opacity: 0; transition: opacity 0.1s;
}
.tt-project:hover .tt-project-actions { opacity: 1; }
/* 📁/🗑 icon buttons are now <UiIconButton variant="bordered"> */
.tt-back { margin-right: 12px; }
.tt-disc-next  { align-self: center; }
.tt-disc-card {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: var(--r);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.tt-disc-heading {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  margin: 0;
}
.tt-disc-body {
  font-size: 13px;
  color: var(--text-faint);
  line-height: 1.6;
  margin: 0;
}
.tt-disc-input-row {
  display: flex;
  gap: 8px;
}
.tt-disc-input {
  flex: 1;
  font-size: 13px;
  padding: 6px 10px;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-sm);
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-mono);
}
.tt-disc-add {
  padding: 6px 14px;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: var(--r-sm);
  font-size: 13px;
  cursor: pointer;
  transition: opacity 0.15s;
}
.tt-disc-add:hover  { opacity: 0.85; }
.tt-disc-add:active { opacity: 0.7; }
.tt-disc-links {
  list-style: none;
  padding: 0; margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.tt-disc-link {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--text-faint);
  background: var(--bg-alt, color-mix(in srgb, var(--bg) 95%, #000));
  border-radius: var(--r-sm);
  padding: 4px 8px;
}
.tt-disc-link-url { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tt-disc-remove {
  background: none; border: none; cursor: pointer;
  color: var(--text-faint); font-size: 11px; flex-shrink: 0;
}
.tt-disc-remove:hover { color: var(--bad); }
.tt-skip {
  background: none;
  border: none;
  font-size: 12px;
  color: var(--text-faint);
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
}
.tt-skip:hover { color: var(--text); }
.tt-skip--manual { font-size: 11px; opacity: 0.6; }

/* ── Setup step ── */
.tt-setup {
  position: relative;               /* anchor for the absolutely-placed rail */
  display: flex;
  align-items: center;
  justify-content: center;          /* the picker stays dead-centre... */
  height: 100%;
  padding: 48px 24px;
  overflow: hidden;                 /* the rail scrolls, not the page */
}
.tt-setup-form {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 20px;
  width: 100%;
  max-width: 420px;
}
.tt-setup-rail {                    /* ...and the rail floats on the right, not displacing it */
  position: absolute;
  top: 24px;
  right: 24px;
  bottom: 24px;
  width: 340px;
  max-width: 30%;
  overflow-y: auto;                 /* scrolls when projects outgrow the viewport */
  padding-right: 4px;
}
.tt-drop {
  width: 100%;
  max-width: 480px;
  border: 2px dashed var(--line-strong);
  border-radius: var(--r);
  padding: 48px 24px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  background: transparent;
}
.tt-drop:hover,
.tt-drop--active { border-color: var(--accent); background: var(--accent-subtle, color-mix(in srgb, var(--accent) 6%, transparent)); }
.tt-drop--filled  { border-style: solid; border-color: var(--ok); }
.tt-file-input    { display: none; }
.tt-drop-label    { font-size: 15px; color: var(--text-faint); }
.tt-drop-label--ready { color: var(--text); font-family: var(--font-mono); font-size: 13px; }
.tt-drop-error { color: var(--bad); font-size: 13px; }
.tt-upload-error { font-size: 12px; color: var(--bad); margin: 0; }
.tt-prompt-card { background: var(--bg-alt, color-mix(in srgb, var(--bg) 94%, #000)); }
.tt-checklist-item--awaiting { color: var(--accent); }
.tt-await-icon { color: var(--accent); font-size: 10px; }
.tt-prompt-cta {
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.tt-prompt-inline-item {
  list-style: none;
  margin: 4px 0 8px 28px;
  padding: 10px 12px;
  border-left: 2px solid var(--accent);
  background: var(--bg-alt, color-mix(in srgb, var(--bg) 94%, #000));
  border-radius: 0 4px 4px 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.tt-prompt-code {
  font-family: var(--font-mono);
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--text);
  margin: 0;
  padding: 8px;
  background: var(--bg);
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
}
.tt-lang-row {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  width: 100%;
}
.tt-lang-label  { font-size: 12px; color: var(--text-faint); }
.tt-lang-hint   { font-size: 11px; color: var(--text-faint); margin-top: 4px; line-height: 1.35; }
.tt-lang-select {
  font-size: 13px;
  padding: 6px 10px;
  width: 320px;
  max-width: 320px;
  text-overflow: ellipsis;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-sm);
  background: var(--bg);
  color: var(--text);
  cursor: pointer;
}
.tt-submit {
  padding: 8px 28px;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: var(--r-sm);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s;
}
.tt-submit:disabled { opacity: 0.35; cursor: default; }
</style>
