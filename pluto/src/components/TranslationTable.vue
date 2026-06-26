<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { API_BASE } from '../composables/useNodes'
import { useAchievement } from '../composables/useAchievement'
import UiSelect from './ui/UiSelect.vue'
import UiButton from './ui/UiButton.vue'
import UiIconButton from './ui/UiIconButton.vue'
import UiClose from './ui/UiClose.vue'
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
  if (used === 0) return 'pending'        // untranslated -> pending, not "ok"
  const budget = block.jpBytes
  if (used <= budget) return 'ok'
  if (used <= budget * 1.3) return 'warn'
  return 'over'
}

// Returns true if this block starts a new speaker run
function isFirstInRun(idx: number): boolean {
  if (idx === 0) return true
  return blocks.value[idx].speakerId !== blocks.value[idx - 1].speakerId
}

// Aggregate across ALL loaded sources (every tab), not just the active one, so the
// header badges read project-wide progress. Grows as lazy tabs stream in.
const stats = computed(() => {
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
  return { total, pending, ok, warn, over }
})

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
      body: JSON.stringify({ sources: { [activeTab.value]: blocks.value } }),
    })
  } catch { /* offline — edits stay local */ }
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
    .sort((a, b) => b.count - a.count)
})
// Only a real legend if the source carries speaker tags (any non-zero id).
const showLegend = computed(() => activeSpeakers.value.some(s => s.id !== 0))
const activeNames = computed(() => speakerNames.value[activeTab.value] || {})
// The display name for a speaker id — the legend name once set, else "Speaker NN".
// Used by every table row, so naming a speaker propagates to all its occurrences.
function speakerLabel(id: number): string {
  return activeNames.value[id] || `Speaker ${id.toString().padStart(2, '0')}`
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
  speakerSaveTimer = setTimeout(saveSpeakers, 600)        // debounce while typing
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
function mapBlocks(raw: { offset: number; jpBytes: number; hex: string; speaker: number }[]): Block[] {
  return (raw || []).map(b => ({
    offset:    '0x' + b.offset.toString(16).toUpperCase().padStart(6, '0'),
    speakerId: b.speaker ?? 0,
    jp:        decodeBlock(b.hex),
    jpBytes:   b.jpBytes,
    ca:        '',
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
  srcs.forEach(s => { state[s.safe] = (tabBlocks.value[s.safe]?.length ? 'ready' : 'idle') })
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
  Promise.all(rest).then(() => { if (curNs.value) persistTotal() })
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
    tabBlocks.value = { ...tabBlocks.value, [safe]: mapBlocks(data.blocks) }
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
      <span class="tt-disclaimer-text"><strong>⚠️ Experimental</strong> Extraction is game-specific and WIP; expect broken ROMs &amp; corrupted text.</span>
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
        <span class="tt-spinner" />
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
                <UiIconButton variant="bordered" title="Delete project" @click="deleteProject(p)">🗑</UiIconButton>
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
        <span class="tt-total">{{ stats.total.toLocaleString() }} blocks</span>
        <span v-if="stats.pending" class="stat pending">{{ stats.pending }} pending</span>
        <span class="stat ok">{{ stats.ok }} ok</span>
        <span class="stat warn">{{ stats.warn }} warn</span>
        <span class="stat over">{{ stats.over }} overflow</span>
        <span class="tt-actions">
          <span v-if="buildMsg" class="tt-build-msg" :class="{ 'tt-build-msg--fail': buildFailed }">{{ buildMsg }}</span>
          <UiButton class="tt-action" :disabled="building || extracting" @click="saveDraft">{{ draftSaved ? 'Saved ✓' : 'Save draft' }}</UiButton>
          <UiButton variant="primary" :loading="building" :disabled="extracting" loading-text="Building…" @click="runBuild">Build ROM</UiButton>
        </span>
      </div>
    </div>

    <!-- Cold scan: we're already on the table page, so show progress HERE, not a frozen picker -->
    <div v-if="discovering" class="tt-scanning">
      <span class="tt-spinner" />
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
          <span v-if="tabState[t.safe] === 'loading'" class="tt-tab-spin"></span>
          <span v-else-if="tabState[t.safe] === 'ready'">{{ (tabBlocks[t.safe] || []).length }}</span>
          <span v-else-if="tabState[t.safe] === 'error'">!</span>
          <span v-else class="tt-tab-dot">·</span>
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
      @rename="renameSpeaker"
    />

    <!-- Table -->
    <div class="tt-table-wrap">
      <table class="tt-table">
        <thead>
          <tr>
            <th class="col-offset">Offset</th>
            <th v-if="showLegend" class="col-speaker">Speaker</th>
            <th class="col-jp">Japanese</th>
            <th class="col-ca">{{ langLabel || 'Catalan' }}</th>
            <th class="col-bytes">Bytes</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(block, index) in blocks"
            :key="block.offset"
            :class="['tt-row', byteStatus(block), { 'run-start': isFirstInRun(index), 'run-cont': !isFirstInRun(index) }]"
          >
            <td class="col-offset mono">{{ block.offset }}</td>

            <td v-if="showLegend" class="col-speaker">
              <!-- Speaker shown once per run; continuation rows get a thin colour line -->
              <template v-if="isFirstInRun(index)">
                <div class="speaker-cell">
                  <span class="speaker-dot" :style="{ background: speakerColor(block.speakerId) }" />
                  <span class="speaker-name">{{ speakerLabel(block.speakerId) }}</span>
                </div>
              </template>
              <div v-else class="speaker-cont">
                <span class="speaker-cont-line" :style="{ background: speakerColor(block.speakerId) }" />
              </div>
            </td>

            <td class="col-jp">
              <span class="jp-text">{{ block.jp }}</span>
              <span v-if="block.note" class="block-note" :title="block.note">⚠</span>
            </td>

            <td class="col-ca">
              <div class="ca-cell">
                <textarea
                  class="ca-input"
                  v-model="block.ca"
                  rows="2"
                  @change="saveState"
                />
                <UiIconButton variant="bordered" class="suggest-btn" title="Suggest shorter variants">↩</UiIconButton>
              </div>
            </td>

            <td class="col-bytes">
              <div class="bytes-cell" :class="byteStatus(block)">
                <span class="bytes-used">{{ caBytes(block.ca) }}</span>
                <span class="bytes-sep">/</span>
                <span class="bytes-budget">{{ block.jpBytes }}</span>
              </div>
            </td>
          </tr>
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
  flex-shrink: 0; font-size: 12.5px; color: var(--text-secondary);
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
.tt-tab-spin {
  display: inline-block; width: 10px; height: 10px;
  border: 2px solid var(--line-strong); border-top-color: var(--accent);
  border-radius: 50%; animation: tt-spin .7s linear infinite;
}
@keyframes tt-spin { to { transform: rotate(360deg); } }

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
}

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
}

.col-offset { width: 100px; }
.col-speaker { width: 160px; }
.col-jp { width: 30%; }
.col-ca { width: 35%; }
.col-bytes { width: 80px; }

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
.ca-input {
  flex: 1;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  padding: var(--sp-1) var(--sp-2);
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text);
  background: var(--surface);
  resize: vertical;
  min-height: 40px;
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
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px 6px;
  border-radius: var(--r-sm);
  width: fit-content;
}
.bytes-cell.pending { background: #eff6ff; color: #2563eb; }
.bytes-cell.ok   { background: #dcfce7; color: var(--ok); }
.bytes-cell.warn { background: #fef3c7; color: var(--warn); }
.bytes-cell.over { background: #fee2e2; color: var(--bad); }
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
.tt-spinner {
  display: inline-block;
  width: 14px; height: 14px;
  border: 2px solid var(--line-strong);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
.tt-spinner--sm { width: 12px; height: 12px; }
@keyframes spin { to { transform: rotate(360deg); } }
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
