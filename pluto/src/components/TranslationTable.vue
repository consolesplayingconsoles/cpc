<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { API_BASE } from '../composables/useNodes'
import UiSelect from './ui/UiSelect.vue'
import UiButton from './ui/UiButton.vue'

const route  = useRoute()
const router = useRouter()

type SpeakerStatus = 'confirmed' | 'inferred' | 'unconfirmed' | 'rejected'

interface Block {
  offset: string
  speakerId: number
  jp: string
  jpBytes: number
  ca: string
  note?: string
}

// Speaker map: what we know about each speaker ID
const speakers = ref<Record<number, { name: string; status: SpeakerStatus; suggestion: string }>>({
  1:  { name: 'Speaker 01', status: 'inferred', suggestion: 'Doraemon' },
  9:  { name: 'Speaker 09', status: 'inferred', suggestion: 'Dorami' },
  2:  { name: 'Speaker 02', status: 'unconfirmed', suggestion: '' },
  7:  { name: 'Speaker 07', status: 'unconfirmed', suggestion: '' },
})

function thumbsUp(id: number) {
  if (speakers.value[id]) {
    speakers.value[id].name = speakers.value[id].suggestion || speakers.value[id].name
    speakers.value[id].status = 'confirmed'
    saveState()
  }
}
function thumbsDown(id: number) {
  if (speakers.value[id]) {
    speakers.value[id].status = 'rejected'
    saveState()
  }
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
  return SPEAKER_COLORS[id] ?? '#8a8a8a'
}

function caBytes(text: string) {
  return new TextEncoder().encode(text).length
}

function byteStatus(block: Block): 'ok' | 'warn' | 'over' {
  const used = caBytes(block.ca)
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

// How many consecutive rows share this speaker ID
function runLength(idx: number): number {
  const id = blocks.value[idx].speakerId
  let len = 1
  while (idx + len < blocks.value.length && blocks.value[idx + len].speakerId === id) len++
  return len
}

const stats = computed(() => {
  const total = blocks.value.length
  const ok = blocks.value.filter(b => byteStatus(b) === 'ok').length
  const warn = blocks.value.filter(b => byteStatus(b) === 'warn').length
  const over = blocks.value.filter(b => byteStatus(b) === 'over').length
  const confirmedIds = Object.values(speakers.value).filter(s => s.status === 'confirmed').length
  const totalIds = Object.keys(speakers.value).length
  return { total, ok, warn, over, confirmedIds, totalIds }
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

const ACCEPTED_EXTENSIONS = ['.gdi', '.zip', '.7z', '.rar', '.gz', '.cdi', '.chd']

const dropActive    = ref(false)
const romFile       = ref<File | null>(null)
const romError      = ref('')
const targetLang    = ref('')
const uploadError   = ref('')
const extractPrompt = ref('')

function setRom(f: File) {
  const ext = f.name.slice(f.name.lastIndexOf('.')).toLowerCase()
  if (!ACCEPTED_EXTENSIONS.includes(ext)) {
    romError.value = `${ext} is not a recognised ROM format.`
    romFile.value  = null
  } else {
    romError.value = ''
    romFile.value  = f
  }
}

function onDragOver(e: DragEvent) { e.preventDefault(); dropActive.value = true }
function onDragLeave()            { dropActive.value = false }
function onDrop(e: DragEvent) {
  e.preventDefault()
  dropActive.value = false
  const f = e.dataTransfer?.files[0]
  if (f) setRom(f)
}
function onFileInput(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) setRom(f)
}

function canSubmit() { return romFile.value !== null && targetLang.value !== '' }

async function submitRom() {
  if (!canSubmit()) return
  uploadError.value  = ''
  const ext = romFile.value!.name.slice(romFile.value!.name.lastIndexOf('.')).toLowerCase()
  extractStatus.value = COMPRESSED_EXTS.includes(ext) ? 'decompressing' : 'parsing'
  step.value = 'discovering'
  await nextTick()
  const form = new FormData()
  form.append('files[]', romFile.value!)
  form.append('lang', targetLang.value)
  try {
    const res  = await fetch(`${API_BASE}/translate/upload`, { method: 'POST', body: form })
    let data: Record<string, unknown> = {}
    try { data = await res.json() } catch { /* non-JSON body */ }
    if (!res.ok) {
      uploadError.value = (data.error as string) || `Upload failed (${res.status})`
      step.value = 'setup'
      return
    }
    if (data.game_id) gameId.value = data.game_id as string
    if (data.prompt) {
      extractPrompt.value  = data.prompt as string
      awaitingUser.value   = true
    }
  } catch { /* network error */ }
}

// ── Polling ───────────────────────────────────────────────────────────────────

type Step = 'pick' | 'setup' | 'discovering' | 'ready' | 'table'
const step   = ref<Step>('pick')

const discoveryLinks = ref<string[]>([])
const linkInput      = ref('')

function addLink() {
  const url = linkInput.value.trim()
  if (url && !discoveryLinks.value.includes(url)) discoveryLinks.value.push(url)
  linkInput.value = ''
}

async function copyPrompt() {
  try {
    await navigator.clipboard.writeText(extractPrompt.value)
  } catch (err) {
    console.error('Copy failed:', err)
  }
}

const gameId = ref('boku-doraemon-dc')
let pollTimer: ReturnType<typeof setInterval> | null = null

function applyState(state: Record<string, unknown>) {
  if (Array.isArray(state.blocks)) blocks.value = state.blocks as Block[]
  if (state.speakers && typeof state.speakers === 'object') {
    speakers.value = state.speakers as typeof speakers.value
  }
  if (typeof state.game === 'string') gameId.value = state.game
}

const COMPRESSED_EXTS = ['.zip', '.7z', '.rar', '.gz']

const BASE_STEPS = [
  { id: 'scanning', pending: 'Scan for text blocks',    active: 'Scanning for text blocks...',  done: 'Text blocks found' },
  { id: 'done',     pending: 'Build translation table', active: 'Building translation table...', done: 'Ready' },
]

const DECOMPRESS_STEP = { id: 'decompressing', pending: 'Decompress archive', active: 'Decompressing archive...', done: 'Archive decompressed' }

const extractSteps = computed(() =>
  extractStatus.value === 'decompressing' || STATUS_ORDER.indexOf(extractStatus.value) > STATUS_ORDER.indexOf('decompressing')
    ? [DECOMPRESS_STEP, ...BASE_STEPS]
    : BASE_STEPS
)

type ExtractStatus = 'pending' | 'decompressing' | 'parsing' | 'locating' | 'scanning' | 'done'
const STATUS_ORDER: ExtractStatus[] = ['pending', 'decompressing', 'parsing', 'locating', 'scanning', 'done']

const extractStatus = ref<ExtractStatus>('pending')
const awaitingUser  = ref(false)

function stepState(id: string): 'done' | 'awaiting' | 'active' | 'pending' {
  const current = STATUS_ORDER.indexOf(extractStatus.value)
  const mine    = STATUS_ORDER.indexOf(id as ExtractStatus)
  if (mine < current) return 'done'
  if (mine === current) return awaitingUser.value ? 'awaiting' : 'active'
  return 'pending'
}

async function poll() {
  // Stop polling once we're viewing the table
  if (step.value === 'table') return

  try {
    const res  = await fetch(`${API_BASE}/translate/${gameId.value}`)
    if (!res.ok) return
    const data = await res.json()
    if (data.status) {
      const incoming = STATUS_ORDER.indexOf(data.status as ExtractStatus)
      if (incoming > STATUS_ORDER.indexOf(extractStatus.value)) {
        extractStatus.value = data.status as ExtractStatus
        awaitingUser.value  = false
      }
    }
    if (data.status && data.status !== 'done') return
    applyState(data)
    step.value = 'ready'
  } catch { /* API not running locally — hardcoded mock stays */ }
}

async function saveState() {
  try {
    await fetch(`${API_BASE}/translate/${gameId.value}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ blocks: blocks.value, speakers: speakers.value }),
    })
  } catch { /* offline — edits stay local */ }
}

// ── Batocera pick → translate flow ─────────────────────────────────────────
interface PickSystem { node: string; name: string; system: string; supported: boolean }
interface PickGame   { name: string; path: string }

const systems       = ref<PickSystem[]>([])
const games         = ref<PickGame[]>([])
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
interface Project { ns: string; gameName: string; lang: string; total: number }
const projects = ref<Project[]>([])
const curNs    = ref('')

async function loadProjects() {
  try {
    const res  = await fetch(`${API_BASE}/translate/projects`)
    const data = await res.json()
    projects.value = (data.projects as Project[]) || []
  } catch { /* leave list as-is */ }
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
    const res  = await fetch(`${API_BASE}/translate/extract?path=${encodeURIComponent(selGame.value)}`)
    const data = await res.json()
    if (!data.blocks) {
      pickError.value = (data.error as string) || (data.detail as string) || 'Extraction failed.'
      return
    }
    const newBlocks: Block[] = (data.blocks as { offset: number; jpBytes: number; hex: string; speaker: number }[]).map(b => ({
      offset:    '0x' + b.offset.toString(16).toUpperCase().padStart(6, '0'),
      speakerId: b.speaker ?? 0,
      jp:        decodeBlock(b.hex),
      jpBytes:   b.jpBytes,
      ca:        '',
    }))
    await fetch(`${API_BASE}/translate/${encodeURIComponent(ns)}`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ gameName, lang: selLang.value, system: selSystem.value,
                                path: selGame.value, total: newBlocks.length, blocks: newBlocks }),
    })
    blocks.value      = newBlocks
    selGameName.value = gameName
    curNs.value       = ns
    step.value        = 'table'
    router.push(`/translation/${encodeURIComponent(ns)}`)
    loadProjects()
  } catch {
    pickError.value = 'Extraction request failed.'
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
    if (Array.isArray(data.blocks)) {
      blocks.value      = data.blocks as Block[]
      selGameName.value = (data.gameName as string) || ns
      selLang.value     = (data.lang as string) || ''
      curNs.value       = ns
      step.value        = 'table'
    } else {
      router.replace('/translation')   // project gone → back to the picker
    }
  } catch { /* ignore */ }
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

onMounted(() => {
  loadSystems()
  loadProjects()
  poll()
  pollTimer = setInterval(poll, 5000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div class="tt-root">

    <!-- ── EXPERIMENTAL DISCLAIMER ── -->
    <div class="tt-disclaimer">
      <div class="tt-disclaimer-content">
        <strong>⚠️ Experimental Feature</strong>
        <p>Text extraction and translation is under active development. Extraction methods are game-specific and documented per-title. <strong>Expect broken ROMs, corrupted text, and incomplete extractions.</strong> Test thoroughly before relying on output.</p>
      </div>
    </div>

    <!-- ── Pick language + game, open the translation table ── -->
    <div v-if="step === 'pick'" class="tt-setup">
      <div class="tt-lang-row">
        <label class="tt-lang-label">Language</label>
        <UiSelect v-model="selLang">
          <option value="" disabled>Pick a language</option>
          <option v-for="l in LANGUAGES" :key="l.code" :value="l.code">{{ l.label }}</option>
        </UiSelect>
      </div>

      <div class="tt-lang-row">
        <label class="tt-lang-label">System</label>
        <UiSelect v-model="selSystem">
          <option value="" disabled>Pick a system</option>
          <option v-for="s in systems" :key="s.system" :value="s.system" :disabled="!s.supported">{{ s.name }}{{ s.supported ? '' : ' (soon)' }}</option>
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

      <UiButton variant="primary" :disabled="!selGame || !selLang || extracting" @click="createProject">
        {{ extracting ? 'Creating…' : 'Create' }}
      </UiButton>

      <div v-if="extracting" class="tt-translating">
        <span class="tt-spinner" />
        <span>Extracting dialogue on Batocera…</span>
      </div>
      <p v-if="pickError" class="tt-upload-error">{{ pickError }}</p>

      <!-- Previous projects: come back to a saved table (no DB — the dirs ARE the list) -->
      <div v-if="projects.length" class="tt-projects">
        <p class="tt-projects-heading">Previous Projects</p>
        <ul class="tt-projects-list">
          <li v-for="p in projects" :key="p.ns" class="tt-project">
            <button class="tt-project-open" @click="loadProject(p)">
              <span class="tt-project-name">{{ p.gameName }}</span>
              <span class="tt-project-lang">{{ langName(p.lang) }}</span>
              <span class="tt-project-count">{{ p.total }} blocks</span>
            </button>
            <button class="tt-project-dir" title="Open project folder" @click="openProjectDir(p)">📁</button>
            <button class="tt-project-dir tt-project-del" title="Delete project" @click="deleteProject(p)">🗑</button>
          </li>
        </ul>
      </div>
    </div>

    <!-- ── Step 0: Drop ROM + pick language ── -->
    <div v-if="step === 'setup'" class="tt-setup">
      <div
        class="tt-drop"
        :class="{ 'tt-drop--active': dropActive, 'tt-drop--filled': romFile }"
        @dragover="onDragOver"
        @dragleave="onDragLeave"
        @drop="onDrop"
        @click="($refs.fileInput as HTMLInputElement).click()"
      >
        <input ref="fileInput" type="file" class="tt-file-input" @change="onFileInput" />
        <span v-if="!romFile && !romError" class="tt-drop-label">Drop ROM here</span>
        <span v-else-if="romError" class="tt-drop-label tt-drop-error">{{ romError }}</span>
        <span v-else class="tt-drop-label tt-drop-label--ready">{{ romFile!.name }}</span>
      </div>

      <p v-if="uploadError" class="tt-upload-error">{{ uploadError }}</p>

      <div class="tt-lang-row">
        <label class="tt-lang-label">Translate to</label>
        <select class="tt-lang-select" v-model="targetLang">
          <option value="" disabled>Pick a language</option>
          <option v-for="l in LANGUAGES" :key="l.code" :value="l.code">{{ l.label }}</option>
        </select>
      </div>

      <button class="tt-submit" :disabled="!canSubmit()" @click="submitRom">Submit</button>
    </div>

    <!-- ── Step 1: Discovering / Ready ── -->
    <div v-else-if="step === 'discovering' || step === 'ready'" class="tt-discovering">
      <ul class="tt-checklist">
        <li
          v-for="s in extractSteps"
          :key="s.id"
          class="tt-checklist-item"
          :class="`tt-checklist-item--${step === 'discovering' ? stepState(s.id) : 'done'}`"
        >
          <span class="tt-checklist-icon">
            <template v-if="step === 'discovering'">
              <span v-if="stepState(s.id) === 'done'"     class="tt-check">&#10003;</span>
              <span v-else-if="stepState(s.id) === 'active'"  class="tt-spinner tt-spinner--sm" />
              <span v-else-if="stepState(s.id) === 'awaiting'" class="tt-await-icon">&#9654;</span>
              <span v-else class="tt-check-empty" />
            </template>
            <span v-else class="tt-check">&#10003;</span>
          </span>
          <span class="tt-checklist-label">{{
            step !== 'discovering' || stepState(s.id) === 'done'   ? s.done
            : stepState(s.id) === 'active'                         ? s.active
            : stepState(s.id) === 'awaiting'                       ? s.pending
            : s.pending
          }}</span>
        </li>
      </ul>

      <div v-if="extractPrompt && step === 'discovering'" class="tt-prompt-card">
        <span class="tt-prompt-cta">Copy this prompt to Claude Code</span>
        <pre class="tt-prompt-code">{{ extractPrompt }}</pre>
        <button class="tt-disc-add" @click="copyPrompt">Copy</button>
      </div>

      <div class="tt-disc-card">
        <p class="tt-disc-heading">Optional: add reference sources</p>
        <p class="tt-disc-body">
          Drop links to official sources in your target language: dubbed episodes,
          character wikis, translated scripts or official subtitles. We'll use them
          to give Claude richer context: better tone, canonical names, the right register.
          Use official sources for better results.
        </p>
        <div class="tt-disc-input-row">
          <input
            class="tt-disc-input"
            v-model="linkInput"
            placeholder="https://..."
            @keydown.enter.prevent="addLink"
          />
          <button class="tt-disc-add" @click="addLink">Add</button>
        </div>
        <button v-if="step === 'ready'" class="tt-submit tt-disc-next" @click="step = 'table'">Continue to translation</button>

        <ul v-if="discoveryLinks.length" class="tt-disc-links">
          <li v-for="(url, i) in discoveryLinks" :key="i" class="tt-disc-link">
            <span class="tt-disc-link-url">{{ url }}</span>
            <button class="tt-disc-remove" @click="discoveryLinks.splice(i, 1)">✕</button>
          </li>
        </ul>
      </div>

    </div>

    <!-- ── Step 2: Header + table ── -->
    <template v-else-if="step === 'table'">
    <!-- Header -->
    <div class="tt-header">
      <div class="tt-title">
        <UiButton class="tt-back" @click="backToProjects">‹ Projects</UiButton>
        <span class="tt-game">{{ selGameName || 'Boku Doraemon' }}</span>
        <span class="tt-sep">·</span>
        <span class="tt-lang">日本語 → {{ langLabel || 'Català' }}</span>
        <span class="tt-sep">·</span>
        <span class="tt-count">{{ stats.total }} blocks</span>
      </div>
      <div class="tt-stats">
        <span class="stat ok">{{ stats.ok }} ok</span>
        <span class="stat warn">{{ stats.warn }} warn</span>
        <span class="stat over">{{ stats.over }} overflow</span>
        <span class="stat-sep">·</span>
        <span class="stat muted">{{ stats.confirmedIds }}/{{ stats.totalIds }} speaker IDs confirmed</span>
      </div>
    </div>

    <!-- Table -->
    <div class="tt-table-wrap">
      <table class="tt-table">
        <thead>
          <tr>
            <th class="col-offset">Offset</th>
            <th class="col-speaker">Speaker</th>
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

            <td class="col-speaker">
              <!-- Only render speaker info on the first row of each run -->
              <template v-if="isFirstInRun(index)">
                <div class="speaker-cell">
                  <span
                    class="speaker-dot"
                    :style="{ background: speakerColor(block.speakerId) }"
                  />
                  <div class="speaker-info">
                    <span class="speaker-name">{{ speakers[block.speakerId]?.name ?? `Speaker ${block.speakerId.toString().padStart(2,'0')}` }}</span>
                    <span
                      v-if="speakers[block.speakerId]?.status === 'inferred' && speakers[block.speakerId]?.suggestion"
                      class="speaker-suggestion"
                    >possibly: {{ speakers[block.speakerId].suggestion }}?</span>
                    <span
                      v-else-if="speakers[block.speakerId]?.status === 'rejected' && speakers[block.speakerId]?.suggestion"
                      class="speaker-suggestion rejected-suggestion"
                    >not {{ speakers[block.speakerId].suggestion }}</span>
                  </div>
                  <template v-if="speakers[block.speakerId]?.status === 'inferred'">
                    <button class="thumb-btn" title="Yes, this is correct" @click="thumbsUp(block.speakerId)">👍</button>
                    <button class="thumb-btn" title="No, this is wrong" @click="thumbsDown(block.speakerId)">👎</button>
                  </template>
                  <span v-else-if="speakers[block.speakerId]?.status === 'confirmed'" class="speaker-badge confirmed">✓</span>
                  <span v-else-if="speakers[block.speakerId]?.status === 'rejected'" class="speaker-badge rejected">✗</span>
                </div>
                <div v-if="runLength(index) > 1" class="run-count">{{ runLength(index) }} lines</div>
              </template>
              <!-- Continuation rows: just a thin colour line -->
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
                <button class="suggest-btn" title="Suggest shorter variants">↩</button>
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
  background: linear-gradient(135deg, rgba(255, 193, 7, 0.15), rgba(244, 67, 54, 0.15));
  border: 1px solid rgba(255, 152, 0, 0.5);
  border-radius: 4px;
  margin: var(--sp-3);
  padding: var(--sp-3) var(--sp-4);
  flex-shrink: 0;
}

.tt-disclaimer-content {
  color: var(--text);
  font-size: 13px;
  line-height: 1.5;
}

.tt-disclaimer-content strong {
  display: block;
  margin-bottom: var(--sp-2);
  color: rgb(255, 152, 0);
  font-weight: 600;
}

.tt-disclaimer-content p {
  margin: 0;
  color: var(--text-secondary);
}

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

.tt-stats {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: 12px;
  font-family: var(--font-mono);
}

.stat { padding: 2px 6px; border-radius: var(--r-sm); font-weight: 500; }
.stat.ok   { background: #dcfce7; color: var(--ok); }
.stat.warn { background: #fef3c7; color: var(--warn); }
.stat.over { background: #fee2e2; color: var(--bad); }
.stat.muted { color: var(--text-faint); padding: 0; }
.stat-sep { color: var(--line-strong); }

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
.suggest-btn {
  padding: var(--sp-1) var(--sp-2);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: var(--surface);
  color: var(--text-muted);
  cursor: pointer;
  font-size: 12px;
  flex-shrink: 0;
  transition: border-color 0.1s, color 0.1s;
}
.suggest-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

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
  text-transform: uppercase; letter-spacing: 0.05em; margin: 0 0 8px;
}
.tt-projects-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.tt-project { display: flex; align-items: center; gap: 6px; }
.tt-project-open {
  flex: 1; display: flex; align-items: baseline; gap: 10px;
  padding: 8px 12px; border: 1px solid var(--line); border-radius: var(--r-sm);
  background: var(--surface); cursor: pointer; text-align: left;
  transition: background 0.1s, border-color 0.1s;
}
.tt-project-open:hover { background: var(--surface-2); border-color: var(--line-strong); }
.tt-project-name  { font-weight: 600; color: var(--text); }
.tt-project-lang  { font-size: 12px; color: var(--accent); }
.tt-project-count { font-size: 12px; color: var(--text-faint); margin-left: auto; }
.tt-project-dir {
  padding: 6px 8px; border: 1px solid var(--line); border-radius: var(--r-sm);
  background: var(--surface); cursor: pointer; font-size: 14px; line-height: 1;
  transition: background 0.1s, border-color 0.1s, color 0.1s;
}
.tt-project-dir:hover { background: var(--surface-2); border-color: var(--line-strong); }
.tt-project-del:hover { background: var(--surface-2); border-color: var(--bad); color: var(--bad); }
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
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
  height: 100%;
  padding: 60px 24px;
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
  width: 320px;
}
.tt-lang-label  { font-size: 12px; color: var(--text-faint); }
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
