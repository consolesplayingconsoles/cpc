<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { NodeMap } from '../../composables/useNodes'
import { ICONS } from '../../composables/useIcons'
import { catalogueApi, type SystemSummary, type SystemView, type Game, type MissingCover, type GameHit } from '../../api/catalogue'
import consolesConfig from '../../../config/consoles.json'
import UiButton from '../ui/UiButton.vue'
import UiSpinner from '../ui/UiSpinner.vue'
import UiIconButton from '../ui/UiIconButton.vue'
import UiSelect from '../ui/UiSelect.vue'
import UiCopyButton from '../ui/UiCopyButton.vue'
import Terminal, { type TerminalOutput } from '../Terminal.vue'
import GameDrawer from './GameDrawer.vue'
import AdminCommand from './AdminCommand.vue'
import UiSubTabs from '../ui/UiSubTabs.vue'
import { useAchievement } from '../../composables/useAchievement'
import { useRomActions } from '../../composables/useRomActions'

// Media: the game catalogue. Grid of SYSTEMS (not nodes) -> one system's games -> a
// drawer per game. System + game ride the URL (/media/:system/:game) so a reload keeps
// the open drawer. Data is the local read-only catalogue; Sync refreshes it from nodes.
const props = defineProps<{ active: boolean; nodes: NodeMap }>()
const nodesRef = computed(() => props.nodes)

// System names + icons are shared config (consoles.json `systems`), same namespace as saves.
const SYSTEMS = (consolesConfig.systems ?? {}) as Record<string, { brand?: string; name?: string; icon?: string }>
function systemName(s: string) { return SYSTEMS[s]?.name ?? s }
function systemIcon(s: string) { const k = SYSTEMS[s]?.icon; return k ? ICONS[k] : undefined }
const route = useRoute()
const router = useRouter()

const system  = computed(() => (route.name === 'media' && route.params.system as string) || '')
const gameKey = computed(() => (route.name === 'media' && route.params.game as string) || '')

const systems  = ref<SystemSummary[]>([])
const view     = ref<SystemView | null>(null)
const loading  = ref(false)
const apiError = ref('')
const filter   = ref('')

// Cards (default) or the dense list; per-viewer preference.
const VIEW_KEY = 'cpc.media.view'
const layout = ref<'cards' | 'list'>((() => { try { return localStorage.getItem(VIEW_KEY) === 'list' ? 'list' : 'cards' } catch { return 'cards' } })())
function setLayout(v: 'cards' | 'list') { layout.value = v; try { localStorage.setItem(VIEW_KEY, v) } catch { /* ignore */ } }
// Covers can take a while (first ask fetches from libretro): spinner until the image lands.
const coverLoaded = ref<Record<string, boolean>>({})
const coverVersion = ref<Record<string, number>>({})
function coverSrc(g: Game) { return g.cover === 'miss' ? '' : catalogueApi.coverUrl(system.value, g.key, coverVersion.value[g.key]) }
function coverChanged(g: Game) {
  g.cover = 'custom'
  coverLoaded.value[g.key] = false
  coverVersion.value[g.key] = Date.now()
}

// A new label renames the game and re-matches its art: reload and re-ask the cover.
async function relabeled() {
  const key = openGame.value?.key
  if (key) { coverLoaded.value[key] = false; coverVersion.value[key] = Date.now() }
  await load()
}

async function load() {
  loading.value = true
  apiError.value = ''
  try {
    if (system.value) view.value = await catalogueApi.system(system.value)
    else systems.value = (await catalogueApi.systems()).systems
  } catch {
    apiError.value = 'Catalogue API unreachable'
  } finally {
    loading.value = false
  }
}
watch(system, () => { filter.value = ''; if (props.active) load() })
watch(() => props.active, (a) => { if (a) load() }, { immediate: true })

// ── Cross-system game lists, grouped by system; click one -> its drawer.
//   missing:  games with no image linked in the catalogue (local only)
//   physical: games you own on a shelf with no digital copy on any node
//   hardware: your consoles and peripherals (rows open the system's page)
type ListMode = 'missing' | 'physical' | 'hardware'
const listMode = ref<ListMode | ''>('')
const missingOpen = computed(() => listMode.value !== '')
const lists = ref<Record<ListMode, MissingCover[] | null>>({ missing: null, physical: null, hardware: null })
const missing = computed(() => listMode.value ? lists.value[listMode.value] : null)
const missingLoading = ref(false)
async function toggleList(mode: ListMode) {
  listMode.value = listMode.value === mode ? '' : mode
  if (!listMode.value || missingLoading.value) return
  missingLoading.value = true
  try {
    const r = mode === 'missing' ? await catalogueApi.missingCovers() : mode === 'physical' ? await catalogueApi.physicalOnly() : await catalogueApi.hardware()
    lists.value[mode] = r.games
  } catch {
    apiError.value = 'Catalogue API unreachable'
  } finally {
    missingLoading.value = false
  }
}
function setGridView(v: 'consoles' | 'hardware') {
  if (v === 'hardware' && listMode.value !== 'hardware') toggleList('hardware')
  if (v === 'consoles' && listMode.value) listMode.value = ''
}
// Per-system sections fold; big ones (MAME) start folded so the list stays scannable.
const missingFolded = ref<Record<string, boolean>>({})
const isFolded = (sys: string, n: number) => missingFolded.value[sys] ?? n > 20
function toggleFold(sys: string, n: number) { missingFolded.value[sys] = !isFolded(sys, n) }
const missingBySystem = computed(() => {
  const by = new Map<string, MissingCover[]>()
  for (const m of missing.value ?? []) if (!m.system || matchesSystem(m.system)) by.set(m.system, [...(by.get(m.system) ?? []), m])
  // general-purpose hardware (system "") goes last
  return [...by.entries()].sort(([a], [b]) => (a ? 0 : 1) - (b ? 0 : 1) || systemName(a).localeCompare(systemName(b)))
})

// Grid filter: system name, brand or folder key ("sega", "dreamcast", "ngpc"). It stays
// on screen in the Missing covers view too (filtering those sections), so nothing jumps.
const systemFilter = ref('')
function matchesSystem(system: string) {
  const q = systemFilter.value.trim().toLowerCase()
  return !q || [system, systemName(system), SYSTEMS[system]?.brand ?? ''].some(t => t.toLowerCase().includes(q))
}

// Cover chips use short codes so several regions fit one line (full name on hover).
const REGION_CODES: Record<string, string> = {
  Japan: 'JP', USA: 'US', Europe: 'EU', Asia: 'AS', World: 'WLD', Korea: 'KR', China: 'CN', Taiwan: 'TW',
  Brazil: 'BR', Australia: 'AU', Canada: 'CA', France: 'FR', Germany: 'DE', Spain: 'ES', Italy: 'IT',
  Netherlands: 'NL', Sweden: 'SE', UK: 'UK', Russia: 'RU', Export: 'EXP',
}
const regionCode = (r: string) => REGION_CODES[r] ?? r.slice(0, 3).toUpperCase()

// Header stats over the whole catalogue (not the grid filters): what Pluto has written down.
const stats = computed(() => {
  const sum = (k: 'games' | 'tools' | 'translations' | 'mods' | 'physical') => systems.value.reduce((n, s) => n + (s[k] ?? 0), 0)
  const plural = (n: number, one: string, many = one + 's') => `${n.toLocaleString()} ${n === 1 ? one : many}`
  return [plural(sum('games') - sum('tools'), 'game'), plural(systems.value.length, 'system'),
    plural(sum('translations'), 'translation'), plural(sum('mods'), 'mod'),
    `${sum('physical').toLocaleString()} physical`, plural(sum('tools'), 'tool')]
})

// Hybrid search: the same box also finds GAMES in every system (debounced API search), listed
// under the tiles grouped by system; a click opens that game's drawer in its system.
const gameHits = ref<GameHit[]>([])
const searching = ref(false)
let searchSeq = 0
let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(systemFilter, (q) => {
  clearTimeout(searchTimer)
  const seq = ++searchSeq
  if (!q.trim()) { gameHits.value = []; searching.value = false; return }
  searching.value = true
  searchTimer = setTimeout(async () => {
    try {
      const r = await catalogueApi.search(q.trim())
      if (seq === searchSeq) gameHits.value = r.games
    } catch {
      if (seq === searchSeq) apiError.value = 'Catalogue API unreachable'
    } finally {
      if (seq === searchSeq) searching.value = false
    }
  }, 250)
})
const hitsBySystem = computed(() => {
  const by = new Map<string, GameHit[]>()
  for (const h of gameHits.value) by.set(h.system, [...(by.get(h.system) ?? []), h])
  return [...by.entries()].sort(([a], [b]) => systemName(a).localeCompare(systemName(b)))
})

// Grid toggles: ★ starred systems, Owned consoles. Both on = either one (the ones you own
// plus the ones you starred); neither = all.
const favSystemsOnly = ref(false)
const ownedOnly = ref(true)                   // on by default: your own consoles first
const gridFilters = computed(() => [favSystemsOnly.value, ownedOnly.value].filter(Boolean).length)
const gridFilterOpen = ref(false)
function keepSystem(s: SystemSummary) {
  if (!favSystemsOnly.value && !ownedOnly.value) return true
  return (favSystemsOnly.value && s.favourite) || (ownedOnly.value && s.owned)
}
async function toggleSystemFav(s: SystemSummary) {
  s.favourite = !s.favourite
  try { await catalogueApi.setSystemFavourite(s.system, s.favourite) } catch { s.favourite = !s.favourite; apiError.value = 'Could not save the favourite' }
}

// Families: brand, then name. Systems without a brand (arcade) go last.
const sortedSystems = computed(() => [...systems.value].filter(s => matchesSystem(s.system) && keepSystem(s)).sort((a, b) => {
  const ba = SYSTEMS[a.system]?.brand, bb = SYSTEMS[b.system]?.brand
  if (!!ba !== !!bb) return ba ? -1 : 1
  return (ba ?? '').localeCompare(bb ?? '') || systemName(a.system).localeCompare(systemName(b.system))
}))

// Grid sections by manufacturer (sortedSystems order kept); brandless systems under "Other".
const brandGroups = computed(() => {
  const out: { brand: string; systems: SystemSummary[] }[] = []
  for (const s of sortedSystems.value) {
    const brand = SYSTEMS[s.system]?.brand ?? 'Other'
    const last = out[out.length - 1]
    if (last && last.brand === brand) last.systems.push(s)
    else out.push({ brand, systems: [s] })
  }
  return out
})

const favOnly = ref(false)
// Copy kind: '' = all, 'digital' = has a file on a node, 'physical' = has a shelf copy.
// A game with both kinds shows under either.
// Filter menu: independent checks, all must hold (Digital + Physical = games with both).
const onlyDigital = ref(false)
const onlyPhysical = ref(false)
const onlySaved = ref(false)
const deletedOnly = ref(false)                  // games whose every file is gone from its node
const noCoverOnly = ref(false)                  // no image linked in the catalogue (same rule as Missing covers)
const activeFilters = computed(() => [favOnly.value, onlyDigital.value, onlyPhysical.value, onlySaved.value, deletedOnly.value, noCoverOnly.value].filter(Boolean).length)
const filterOpen = ref(false)
const sendMenuOpen = ref(false)
function closeFilterMenu(e: MouseEvent) {
  if (!(e.target as HTMLElement)?.closest?.('.md__filter-menu')) { filterOpen.value = false; gridFilterOpen.value = false; sendMenuOpen.value = false }
}
onMounted(() => document.addEventListener('click', closeFilterMenu))
onUnmounted(() => document.removeEventListener('click', closeFilterMenu))
watch(system, () => { favOnly.value = false; onlyDigital.value = false; onlyPhysical.value = false; onlySaved.value = false; deletedOnly.value = false; noCoverOnly.value = false; groupBy.value = ''; kindTab.value = 'game' })

// Group by a metadata field. Which fields: systems.<x>.filters, else defaultFilters, and
// only those with at least one value among this system's games (coverage is uneven).
type MetaField = 'genre' | 'developer' | 'publisher' | 'year'
const FIELD_LABEL: Record<MetaField, string> = { genre: 'Genre', developer: 'Developer', publisher: 'Publisher', year: 'Year' }
const groupBy = ref<'' | MetaField>('')
const groupFields = computed<MetaField[]>(() => {
  const wanted = ((SYSTEMS[system.value] as { filters?: string[] } | undefined)?.filters ?? consolesConfig.defaultFilters) as MetaField[]
  const all = view.value?.games ?? []
  return wanted.filter(f => all.some(g => g.meta?.[f]))
})
const sections = computed(() => {
  if (!groupBy.value) return [{ label: '', games: games.value }]
  const by = new Map<string, Game[]>()
  for (const g of games.value) {
    const k = g.meta?.[groupBy.value] ?? ''
    by.set(k, [...(by.get(k) ?? []), g])
  }
  return [...by.entries()]
    .sort(([a], [b]) => (a ? 0 : 1) - (b ? 0 : 1) || a.localeCompare(b))
    .map(([k, gs]) => ({ label: k || 'Unknown', games: gs }))
})

// Play / Open folder / Send live in the drawer (click a card); the page keeps Send all.
const { sendTargets, sendCommand, actionError } = useRomActions(system, nodesRef)

// System tiles + the system page show every node CONFIGURED for the system (nodeConsoles:
// capable), dimmed when it holds none of its games; game cards show only nodes where the
// game is PRESENT. Same source as the API's hosts list.
function hostsFor(sys: string): string[] {
  const nc = (consolesConfig.nodeConsoles ?? {}) as Record<string, string[]>
  return Object.keys(nc).filter(n => (nc[n].includes('*') || nc[n].includes(sys)) && ICONS[n]).sort()
}

const hostsWithGames = computed(() => new Set((view.value?.games ?? []).flatMap(g => g.nodes)))

// A system page has two tabs: its games and its tools (Dreamkey, DreamShell...).
const kindTab = ref<'game' | 'tool' | 'hardware'>('game')
const hardwareCount = computed(() => hardwareGames.value.length)
const kindCount = (k: 'game' | 'tool') => (view.value?.games ?? []).filter(g => (g.kind ?? 'game') === k).length
// Hardware tab: the console + its peripherals shown through the SAME list as games (always list),
// as game-shaped entries (title, region chip; model/storage/status in the subtitle).
const hardwareGames = computed<Game[]>(() => {
  const hw = view.value?.hardware
  if (!hw) return []
  const item = (key: string, title: string, sub: string[], region = ''): Game => ({
    key, title, ids: [], files: [], physical: [], meta: {}, regions: region ? [region] : [], nodes: [], saves: [],
    favourite: false, cover: 'miss', kind: 'game', hardwareInfo: sub.filter(Boolean).join(' · '),
  } as unknown as Game)
  const out: Game[] = []
  if (hw.console) out.push(item('hw-console', systemName(system.value) + (hw.console.model ? ' ' + hw.console.model : ''),
    [hw.console.status ?? '', hw.console.notes ?? ''], hw.console.region))
  hw.peripherals.forEach((p, i) => out.push(item('hw-' + i, p.name + ((p.count ?? 1) > 1 ? ' ×' + p.count : ''),
    [p.model ?? '', p.storage ?? '', p.status ?? '', p.notes ?? ''])))
  return out
})
const games = computed<Game[]>(() => {
  const q = filter.value.trim().toLowerCase()
  if (kindTab.value === 'hardware') return q ? hardwareGames.value.filter(g => g.title.toLowerCase().includes(q)) : hardwareGames.value
  const all = (view.value?.games ?? []).filter(g => (g.kind ?? 'game') === kindTab.value && (!favOnly.value || g.favourite) &&
    (!onlyDigital.value || g.files.some(f => f.status === 'present')) &&
    (!onlyPhysical.value || g.physical.length > 0) &&
    (!onlySaved.value || g.saves.length > 0) &&
    (!deletedOnly.value || onlyDeleted(g)) &&
    (!noCoverOnly.value || (g.cover !== 'custom' && g.cover !== 'cached')))
  return q ? all.filter(g => g.title.toLowerCase().includes(q) || g.files.some(f => f.path.toLowerCase().includes(q))
                          || Object.values(g.meta ?? {}).some(v => v.toLowerCase().includes(q))) : all
})
const openGame = computed(() => view.value?.games.find(g => g.key === gameKey.value) ?? null)

function go(sys?: string, game?: string) {
  const path = '/media' + (sys ? '/' + encodeURIComponent(sys) : '') + (game ? '/' + encodeURIComponent(game) : '')
  if (route.path !== path) router.push(path)
}

// "Original + 1 translation · 2 mods": the Original prefix only when variants exist too,
// so "1 mod" alone means there's no original copy (present files only).
function variantSummary(g: Game): string {
  const hw = (g as Game & { hardwareInfo?: string }).hardwareInfo
  if (hw !== undefined) return hw                       // Hardware tab rows: model · storage · status
  const mods = new Set<string>(), tls = new Set<string>()
  let original = false
  for (const f of g.files) {
    if (f.status !== 'present') continue
    if (!f.variants.length) original = true
    for (const v of f.variants) (v.kind === 'mod' ? mods : tls).add(v.name)
  }
  const parts = [tls.size ? `${tls.size} translation${tls.size > 1 ? 's' : ''}` : '', mods.size ? `${mods.size} mod${mods.size > 1 ? 's' : ''}` : '']
    .filter(Boolean).join(' · ')
  return parts && original ? `Original + ${parts}` : parts
}
const onlyDeleted = (g: Game) => g.files.length > 0 && g.nodes.length === 0
function nodeName(id: string) { return props.nodes[id]?.name ?? id }

async function toggleFavourite(g: Game, on: boolean) {
  g.favourite = on
  try { await catalogueApi.setFavourite(view.value!.system, g.key, on) } catch { g.favourite = !on }
}

// ↑/↓ walk the (filtered) list while the drawer is open; Esc closes it.
function onKey(e: KeyboardEvent) {
  if (!props.active || !openGame.value) return
  if ((e.target as HTMLElement)?.tagName === 'INPUT') return
  if (e.key === 'Escape') { go(system.value); return }
  if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
  e.preventDefault()
  const i = games.value.findIndex(g => g.key === gameKey.value)
  const next = games.value[i + (e.key === 'ArrowDown' ? 1 : -1)]
  if (next) {
    router.replace('/media/' + encodeURIComponent(system.value) + '/' + encodeURIComponent(next.key))
    document.getElementById('media-row-' + next.key)?.scrollIntoView({ block: 'nearest' })
  }
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))

// ── Sync: same SSE line/done contract as deploy, shown in the same console ──
const syncOut = ref<TerminalOutput | null>(null)
const termTitle = ref('sync')                            // the console serves sync and send
const syncing = computed(() => syncOut.value?.ok === null)
const { unlock } = useAchievement()
// Nodes whose drive only root can read (the PS2 HDD) don't sync from here: the API streams
// "<node>: needs admin, run in Terminal: <command>" (service.sync admin_nodes), shown as a dialog.
const ADMIN_LINE = /^\S+: needs admin, run in Terminal: (.+)$/
const adminCommands = ref<string[]>([])
function sync(target: string) {
  const startedAt = Date.now()
  termTitle.value = 'sync'
  adminCommands.value = []
  syncOut.value = { raw: '', ok: null, step: target === '*' ? 'all systems' : systemName(target), startedAt }
  const es = new EventSource(catalogueApi.syncUrl(target))
  es.addEventListener('line', (e: MessageEvent) => {
    if (syncOut.value) syncOut.value = { ...syncOut.value, raw: syncOut.value.raw + e.data + '\n' }
    const admin = ADMIN_LINE.exec(e.data)
    if (admin) adminCommands.value = [...adminCommands.value, admin[1]]
  })
  es.addEventListener('done', (e: MessageEvent) => {
    es.close()
    const ok = e.data === 'ok'
    if (syncOut.value) syncOut.value = { ...syncOut.value, ok, step: ok ? 'done' : 'failed' }
    if (ok) setTimeout(() => unlock(`Successfully Synced ${target === '*' ? 'All Systems' : systemName(target)}`, `${Math.round((Date.now() - startedAt) / 1000)}s`), 600)
    load()
  })
  es.onerror = () => {
    es.close()
    if (syncOut.value?.ok === null) syncOut.value = { ...syncOut.value, raw: syncOut.value.raw + '\n[connection lost]', ok: false, step: 'failed' }
  }
}
// Floats bottom-right, left of the game drawer when one is open (as the deploy console does
// beside the Network drawer), so it never covers the drawer.
// Send all: streams into the same console as sync. A target that needs admin (PS2 drive)
// answers with a `command` event instead of copying: the popup shows it.
function sendAll(node: string, name: string) {
  const startedAt = Date.now()
  termTitle.value = 'send'
  syncOut.value = { raw: '', ok: null, step: 'send to ' + name, startedAt }
  const es = new EventSource(catalogueApi.sendStreamUrl(system.value, node))
  es.addEventListener('line', (e: MessageEvent) => {
    if (syncOut.value) syncOut.value = { ...syncOut.value, raw: syncOut.value.raw + e.data + '\n' }
  })
  es.addEventListener('command', (e: MessageEvent) => {
    try { sendCommand.value = JSON.parse(e.data).command } catch { /* malformed: the log shows it */ }
  })
  es.addEventListener('done', (e: MessageEvent) => {
    es.close()
    const ok = e.data === 'ok'
    if (syncOut.value) syncOut.value = { ...syncOut.value, ok, step: ok ? 'done' : 'failed' }
    if (ok && !sendCommand.value) setTimeout(() => unlock(`Sent to ${name}`, `${Math.round((Date.now() - startedAt) / 1000)}s`), 600)
    load()
  })
  es.onerror = () => {
    es.close()
    if (syncOut.value?.ok === null) syncOut.value = { ...syncOut.value, raw: syncOut.value.raw + '\n[connection lost]', ok: false, step: 'failed' }
  }
}
const termStyle = computed(() => ({
  right: openGame.value ? 'min(432px, calc(100% - 16px))' : '16px', bottom: '16px',
  width: openGame.value ? 'min(560px, max(240px, calc(100% - 448px)))' : 'min(560px, calc(100% - 32px))', height: '260px',
}))
</script>

<template>
  <div class="md">
    <!-- ── Grid: systems with games ── -->
    <template v-if="!system">
      <!-- view toolbar, same look as a system page: search takes the room left -->
      <div class="md__toolbar md__toolbar--grid">
        <input v-model="systemFilter" class="md__filter md__search" type="search" placeholder="Search systems and games" />
        <!-- same Filter menu + pills pattern as a system page -->
        <span v-if="!missingOpen" class="md__filter-menu">
          <UiButton :class="{ 'is-on': gridFilters }" @click.stop="gridFilterOpen = !gridFilterOpen">
            Filter<template v-if="gridFilters"> · {{ gridFilters }}</template> ▾
          </UiButton>
          <div v-if="gridFilterOpen" class="md__menu md__menu--right" role="menu">
            <label><input v-model="favSystemsOnly" type="checkbox" /> Favourites</label>
            <label><input v-model="ownedOnly" type="checkbox" /> Owned consoles</label>
          </div>
        </span>
        <!-- what the grid shows: consoles or your hardware, a select like a system page's Cards/List -->
        <span class="md__view md__view--wide">
          <UiSelect :model-value="listMode === 'hardware' ? 'hardware' : 'consoles'" @update:model-value="setGridView($event as 'consoles' | 'hardware')">
            <option value="consoles">All consoles</option>
            <option value="hardware">Hardware</option>
          </UiSelect>
        </span>
        <UiButton class="md__action" :class="{ 'is-on': listMode === 'physical' }" @click="toggleList('physical')">
          {{ listMode === 'physical' ? 'All systems' : 'Physical only' }}
        </UiButton>
        <UiButton class="md__action" :class="{ 'is-on': listMode === 'missing' }" @click="toggleList('missing')">
          {{ listMode === 'missing' ? 'All systems' : 'Missing covers' }}<template v-if="lists.missing && listMode !== 'missing'"> ({{ lists.missing.length }})</template>
        </UiButton>
        <UiButton class="md__action" variant="primary" :loading="syncing" loading-text="Syncing…" @click="sync('*')">Sync all</UiButton>
        <!-- Physical only shows covers too: same Cards/List choice as a system page -->
        <span v-if="listMode === 'physical'" class="md__layout">
          <UiIconButton variant="ghost" :active="layout === 'cards'" title="Cards" @click="setLayout('cards')">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/></svg>
          </UiIconButton>
          <UiIconButton variant="ghost" :active="layout === 'list'" title="List" @click="setLayout('list')">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M5 6h14M5 12h14M5 18h14"/></svg>
          </UiIconButton>
        </span>
      </div>
      <div class="md__body">
        <p v-if="systems.length" class="md__stats">{{ stats.join(' · ') }}</p>
        <span v-if="!missingOpen && gridFilters" class="md__pills md__pills--grid">
          <button v-if="favSystemsOnly" class="md__pill" @click="favSystemsOnly = false">Favourites ✕</button>
          <button v-if="ownedOnly" class="md__pill" @click="ownedOnly = false">Owned consoles ✕</button>
          <button class="md__pill-clear" @click="favSystemsOnly = ownedOnly = false">Clear all</button>
        </span>
        <template v-if="missingOpen">
          <p v-if="missingLoading" class="md__state"><UiSpinner /> {{ listMode === 'missing' ? 'Checking covers…' : listMode === 'hardware' ? 'Loading hardware…' : 'Checking shelves…' }}</p>
          <p v-else-if="missing && !missing.length" class="md__state">{{ listMode === 'missing' ? 'Every game has a cover.' : listMode === 'hardware' ? 'No hardware recorded.' : 'Every physical game has a digital copy.' }}</p>
          <section v-for="[sys, list] in missingBySystem" :key="sys" class="md__missing">
            <button class="md__section md__fold" :aria-expanded="!isFolded(sys, list.length)" @click="toggleFold(sys, list.length)">
              <svg class="md__fold-chev" :class="{ 'is-open': !isFolded(sys, list.length) }" width="12" height="12" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
              <img v-if="systemIcon(sys) || ICONS[sys]" :src="systemIcon(sys) || ICONS[sys]" class="md__missing-ic" alt="" />
              {{ !sys ? 'General purpose' : SYSTEMS[sys] ? systemName(sys) : nodeName(sys) }} <span>{{ list.length }}</span>
            </button>
            <div v-if="!isFolded(sys, list.length) && listMode === 'physical' && layout === 'cards'" class="md__cards md__cards--mini">
              <div v-for="m in list" :key="m.key" class="md__card" role="button" tabindex="0" @click="go(m.system, m.key)" @keydown.enter="go(m.system, m.key)">
                <span class="md__cover">
                  <img :src="catalogueApi.coverUrl(m.system, m.key)" alt="" loading="lazy" />
                </span>
                <span class="md__card-body">
                  <span class="md__card-title">{{ m.title }}</span>
                </span>
              </div>
            </div>
            <ul v-else-if="!isFolded(sys, list.length)" class="md__list">
              <li v-for="m in list" :key="m.system + m.key" class="md__row" @click="listMode === 'hardware' ? (SYSTEMS[m.system] && go(m.system)) : go(m.system, m.key)">
                <span class="md__title">{{ m.title }}</span>
                <span v-if="m.info" class="md__variants">{{ m.info }}</span>
              </li>
            </ul>
          </section>
        </template>
        <p v-if="apiError" class="md__state is-bad">{{ apiError }}</p>
        <p v-else-if="loading && !systems.length" class="md__state"><UiSpinner /> Loading catalogue…</p>
        <p v-else-if="!systems.length" class="md__state">No games yet. Sync all to build the catalogue.</p>
        <p v-if="!missingOpen && systems.length && !sortedSystems.length && !gameHits.length && !searching" class="md__state">Nothing matches "{{ systemFilter }}".</p>
        <template v-if="!missingOpen">
         <template v-for="grp in brandGroups" :key="grp.brand">
          <h3 class="md__section md__brand">{{ grp.brand }} <span>{{ grp.systems.length }}</span></h3>
          <div class="md__grid">
          <div v-for="s in grp.systems" :key="s.system" class="md__tile" role="button" tabindex="0" @click="go(s.system)" @keydown.enter="go(s.system)">
            <span v-if="s.owned" class="md__kind is-physical md__tile-owned" :title="'You own this console' + (s.hardware?.status ? ': ' + s.hardware.status : '')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><rect x="3" y="7" width="18" height="10" rx="3"/><path d="M7 12h3M8.5 10.5v3"/></svg>
            </span>
            <span class="md__tile-marks" @click.stop>
              <UiIconButton variant="ghost" :active="s.favourite" :title="s.favourite ? 'Unfavourite system' : 'Favourite system'" @click="toggleSystemFav(s)">
                <svg width="15" height="15" viewBox="0 0 24 24" :fill="s.favourite ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M12 3.5l2.6 5.3 5.9.9-4.2 4.1 1 5.8L12 16.9l-5.3 2.7 1-5.8L3.5 9.7l5.9-.9z"/></svg>
              </UiIconButton>
            </span>
            <img v-if="systemIcon(s.system)" :src="systemIcon(s.system)" class="md__tile-ic" alt="" />
            <span v-else class="md__tile-ic md__tile-letter">{{ systemName(s.system).slice(0, 1) }}</span>
            <span class="md__tile-name">{{ systemName(s.system) }} <UiCopyButton :text="systemName(s.system)" title="Copy system name" /></span>
            <span class="md__tile-count">{{ s.games }} game{{ s.games === 1 ? '' : 's' }}<template v-if="s.physical"> · {{ s.physical }} physical</template></span>
            <span v-if="s.nodes.length" class="md__tile-nodes">
              <img v-for="n in hostsFor(s.system)" :key="n" :src="ICONS[n]" alt=""
                   :class="{ 'is-idle': !s.nodes.includes(n) }"
                   :title="nodeName(n) + (s.nodes.includes(n) ? '' : ' (configured, no games yet)')" />
            </span>
          </div>
          </div>
         </template>
         <template v-if="systemFilter.trim()">
          <h3 class="md__section md__brand">Games <span>{{ gameHits.length }}</span><UiSpinner v-if="searching" :size="12" /></h3>
          <section v-for="[sys, list] in hitsBySystem" :key="sys" class="md__missing">
            <button class="md__section md__fold" :aria-expanded="!isFolded(sys, list.length)" @click="toggleFold(sys, list.length)">
              <svg class="md__fold-chev" :class="{ 'is-open': !isFolded(sys, list.length) }" width="12" height="12" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
              <img v-if="systemIcon(sys)" :src="systemIcon(sys)" class="md__missing-ic" alt="" />
              {{ systemName(sys) }} <span>{{ list.length }}</span>
            </button>
            <div v-if="!isFolded(sys, list.length)" class="md__cards md__cards--mini">
              <div v-for="h in list" :key="h.key" class="md__card" role="button" tabindex="0" @click="go(h.system, h.key)" @keydown.enter="go(h.system, h.key)">
                <span class="md__cover">
                  <img :src="catalogueApi.coverUrl(h.system, h.key)" alt="" loading="lazy" />
                </span>
                <span class="md__card-body">
                  <span class="md__card-title">{{ h.title }}</span>
                  <span v-if="h.kind === 'tool'" class="md__card-row"><span class="md__node">Tool</span></span>
                </span>
              </div>
            </div>
          </section>
          <p v-if="!searching && !gameHits.length" class="md__state">No games match "{{ systemFilter }}".</p>
         </template>
        </template>
      </div>
    </template>

    <!-- ── One system: games A-Z ── -->
    <template v-else>
      <!-- page header: where you are (left), what you can do here (right) -->
      <header class="md__bar">
        <div class="md__title-row">
          <button class="md__crumb" @click="go()">Media</button>
          <span class="md__crumb-sep">/</span>
          <img v-if="systemIcon(system)" :src="systemIcon(system)" class="md__head-ic" alt="" />
          <span class="md__head-title">{{ systemName(system) }}</span>
        </div>
        <!-- the nodes this console syncs from and copies to, then when and how -->
        <span class="md__sync">
          <span v-if="view?.hosts.length" class="md__hosts">
            <img v-for="n in view.hosts" :key="n" :src="ICONS[n]" alt=""
                 :class="{ 'is-idle': !hostsWithGames.has(n) }"
                 :title="nodeName(n) + (hostsWithGames.has(n) ? '' : ' (configured, no games yet)')" />
          </span>
          <span v-if="view?.syncedAt" class="md__synced">Synced {{ view.syncedAt.slice(0, 16).replace('T', ' ') }}</span>
          <UiButton :loading="syncing" loading-text="Syncing…" @click="sync(system)">Sync</UiButton>
          <span v-if="sendTargets.length" class="md__filter-menu">
            <UiButton :disabled="syncing" @click.stop="sendMenuOpen = !sendMenuOpen">Send all to ▾</UiButton>
            <div v-if="sendMenuOpen" class="md__menu md__menu--right" role="menu">
              <button v-for="t in sendTargets" :key="t.id" class="md__menu-item" :title="'Copy every game ' + t.name + ' doesn\'t have yet'"
                      @click="sendMenuOpen = false; sendAll(t.id, t.name)">
                <img v-if="ICONS[t.id]" :src="ICONS[t.id]" alt="" />{{ t.name }}
              </button>
            </div>
          </span>
        </span>
      </header>
      <!-- view toolbar: search takes the room left; filter, grouping and view are dropdowns -->
      <div class="md__toolbar">
        <input v-model="filter" class="md__filter md__search" type="search" placeholder="Search games" />
        <span class="md__filter-menu">
          <UiButton :class="{ 'is-on': activeFilters }" @click.stop="filterOpen = !filterOpen">
            Filter<template v-if="activeFilters"> · {{ activeFilters }}</template> ▾
          </UiButton>
          <div v-if="filterOpen" class="md__menu md__menu--right" role="menu">
            <label><input v-model="deletedOnly" type="checkbox" /> Deleted</label>
            <label><input v-model="onlyDigital" type="checkbox" /> Digital copies</label>
            <label><input v-model="favOnly" type="checkbox" /> Favourites</label>
            <label><input v-model="onlySaved" type="checkbox" /> Has a save</label>
            <label><input v-model="noCoverOnly" type="checkbox" /> No cover</label>
            <label><input v-model="onlyPhysical" type="checkbox" /> Physical copies</label>
          </div>
        </span>
        <span v-if="groupFields.length" class="md__group">
          <UiSelect v-model="groupBy">
            <option value="">No grouping</option>
            <option v-for="f in groupFields" :key="f" :value="f">Group by {{ FIELD_LABEL[f].toLowerCase() }}</option>
          </UiSelect>
        </span>
        <span class="md__view">
          <UiSelect :model-value="layout" @update:model-value="setLayout($event as 'cards' | 'list')">
            <option value="cards">Cards</option>
            <option value="list">List</option>
          </UiSelect>
        </span>
      </div>
      <!-- tabs share the toolbar's search and filters; active filters sit on the right as pills -->
      <UiSubTabs
        :model-value="kindTab"
        :tabs="[
          { key: 'game', label: 'Games', count: kindCount('game') },
          { key: 'tool', label: 'Tools', count: kindCount('tool') },
          { key: 'hardware', label: 'Hardware', count: hardwareCount },
        ]"
        @update:model-value="kindTab = $event as typeof kindTab"
      >
        <span v-if="activeFilters" class="md__pills">
          <button v-if="deletedOnly" class="md__pill" @click="deletedOnly = false">Deleted ✕</button>
          <button v-if="onlyDigital" class="md__pill" @click="onlyDigital = false">Digital copies ✕</button>
          <button v-if="favOnly" class="md__pill" @click="favOnly = false">Favourites ✕</button>
          <button v-if="onlySaved" class="md__pill" @click="onlySaved = false">Has a save ✕</button>
          <button v-if="noCoverOnly" class="md__pill" @click="noCoverOnly = false">No cover ✕</button>
          <button v-if="onlyPhysical" class="md__pill" @click="onlyPhysical = false">Physical copies ✕</button>
          <button class="md__pill-clear" @click="onlyDigital = onlyPhysical = favOnly = onlySaved = deletedOnly = noCoverOnly = false">Clear all</button>
        </span>
      </UiSubTabs>
      <!-- stage = the non-scrolling frame: the drawer pins to it, the body scrolls inside -->
      <div class="md__stage">
      <div class="md__body md__body--list" @click="gameKey && go(system)">
        <p v-if="actionError" class="md__state is-bad">{{ actionError }}</p>
        <p v-if="apiError" class="md__state is-bad">{{ apiError }}</p>
        <p v-else-if="loading && !view" class="md__state"><UiSpinner /> Loading…</p>
        <template v-for="sec in sections" :key="sec.label">
        <h3 v-if="sec.label" class="md__section">{{ sec.label }} <span>{{ sec.games.length }}</span></h3>
        <div v-if="layout === 'cards' && kindTab !== 'hardware'" class="md__cards">
          <div v-for="g in sec.games" :id="'media-row-' + g.key" :key="g.key"
               class="md__card" :class="{ 'is-open': g.key === gameKey, 'is-gone': onlyDeleted(g) }"
               role="button" tabindex="0"
               @click.stop="go(system, g.key)" @keydown.enter.self="go(system, g.key)">
            <!-- cover fills its box (zoomed, no margins); status rides its corners -->
            <span class="md__cover">
              <template v-if="coverSrc(g)">
                <img :src="coverSrc(g)" loading="lazy" alt="" class="md__cover-art" :class="{ 'is-loading': !coverLoaded[g.key] }"
                     @load="coverLoaded[g.key] = true" @error="g.cover = 'miss'" />
                <UiSpinner v-if="!coverLoaded[g.key]" class="md__cover-spin" :size="20" />
              </template>
              <img v-else-if="systemIcon(system)" :src="systemIcon(system)" class="md__cover-ic" alt="" />
              <span v-else class="md__cover-letter">{{ g.title.slice(0, 1) }}</span>
              <span v-if="g.regions.length" class="md__cover-tl">
                <span v-for="r in g.regions" :key="r" class="md__cover-chip" :title="r">{{ regionCode(r) }}</span>
              </span>
              <span class="md__cover-tr">
                <span v-if="g.favourite" class="md__cover-badge is-star" title="Favourite">★</span>
                <span v-if="g.saves.length" class="md__cover-badge" :title="'Save on ' + g.saves.map(nodeName).join(', ')">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M5 3h11l3 3v15H5z"/><path d="M8 3v5h7V3M8 21v-7h8v7"/></svg>
                </span>
                <span v-if="g.physical.length" class="md__cover-badge" :title="'Physical copy' + (g.physical[0].status ? ': ' + g.physical[0].status : '')">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2.5"/></svg>
                </span>
              </span>
              <span v-if="onlyDeleted(g)" class="md__cover-gone">Deleted</span>
            </span>
            <span class="md__card-body">
              <span class="md__card-title" :title="g.title">{{ g.title }}</span>
              <span v-if="variantSummary(g)" class="md__variants">{{ variantSummary(g) }}</span>
              <span v-if="g.nodes.length" class="md__card-nodes">
                <img v-for="n in g.nodes" :key="n" :src="ICONS[n]" :title="nodeName(n)" alt="" />
              </span>
            </span>
          </div>
        </div>
        <ul v-else class="md__list">
          <li v-for="g in sec.games" :id="'media-row-' + g.key" :key="g.key"
              class="md__row" :class="{ 'is-open': g.key === gameKey, 'is-gone': onlyDeleted(g) }"
              @click.stop="kindTab !== 'hardware' && go(system, g.key)">
            <span class="md__star" :class="{ 'is-on': g.favourite }">{{ g.favourite ? '★' : '' }}</span>
            <span class="md__title">{{ g.title }}</span>
            <span class="md__variants">{{ variantSummary(g) }}</span>
            <span class="md__badges">
              <span v-for="r in g.regions" :key="r" class="md__region">{{ r }}</span>
              <span v-for="n in g.nodes" :key="n" class="md__node" :title="nodeName(n)">
                <img v-if="ICONS[n]" :src="ICONS[n]" alt="" />{{ nodeName(n) }}
              </span>
              <span v-if="g.physical.length" class="md__kind is-physical" :title="'Physical copy' + (g.physical[0].status ? ': ' + g.physical[0].status : '')"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2.5"/></svg></span>
              <span v-if="g.saves.length" class="md__node is-save" :title="'Save on ' + g.saves.map(nodeName).join(', ')">Save</span>
              <span v-if="onlyDeleted(g)" class="md__node is-deleted">Deleted</span>
            </span>
          </li>
        </ul>
        </template>
      </div>
      <GameDrawer v-if="openGame && view" :system="view.system" :game="openGame" :nodes="nodes" :system-icon="systemIcon(system)"
                  :cover-version="coverVersion[openGame.key]"
                  @close="go(system)" @favourite="toggleFavourite(openGame, $event)" @cover-changed="coverChanged(openGame)" @relabeled="relabeled" @changed="load" />
      </div>
    </template>

    <Terminal v-if="syncOut" :title="termTitle" :output="syncOut" :card-style="termStyle" @close="syncOut = null" />
    <AdminCommand v-if="sendCommand" title="Send the games to the drive from Terminal" :commands="[sendCommand]" @close="sendCommand = ''" />
    <AdminCommand v-if="adminCommands.length && !syncing" title="Sync the PS2 drive from Terminal" :commands="adminCommands" @close="adminCommands = []" />
  </div>
</template>

<style scoped>
.md { position: relative; display: flex; flex-direction: column; height: 100%; background: var(--surface-2); font-family: var(--font-sans); color: var(--text); }
.md__bar { display: flex; align-items: center; gap: var(--sp-3); padding: var(--sp-3) var(--sp-5); background: var(--surface); border-bottom: 1px solid var(--line); flex-shrink: 0; flex-wrap: wrap; }
.md__actions { display: flex; justify-content: flex-end; align-items: center; gap: var(--sp-2); margin-bottom: var(--sp-4); }
/* same side as the games filter on a system page: right, next to the actions */
.md__missing { margin-bottom: var(--sp-4); background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-lg); overflow: hidden; }
.md__missing .md__section { padding: var(--sp-3) var(--sp-4); align-items: center; }
.md__fold { width: 100%; border: 0; background: none; font: inherit; cursor: pointer; text-align: left; }
.md__fold:hover { background: var(--surface-2); }
.md__fold-chev { color: var(--text-faint); transition: transform 0.12s; flex: none; }
.md__fold-chev.is-open { transform: rotate(90deg); }
.md__missing-ic { width: 22px; height: 22px; object-fit: contain; }
.md__missing .md__row { padding: 8px var(--sp-4); }
.md__missing .md__row:last-child { border-bottom: 0; }
/* the chat dock floats bottom-left over the page: leave room so the last system isn't hidden under it */
.md__missing:last-of-type { margin-bottom: 96px; }
/* back button: same pattern as the Translation tab's "‹ Projects" */
.md__title-row { display: flex; align-items: center; gap: var(--sp-2); margin-right: auto; min-width: 0; }
.md__crumb { font: inherit; font-size: 15px; color: var(--text-muted); background: none; border: 0; padding: 0; cursor: pointer; }
.md__crumb:hover { color: var(--text); }
.md__crumb-sep { color: var(--text-faint); }
.md__head-ic { width: 28px; height: 28px; object-fit: contain; }
.md__head-title { font-size: 16px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.md__synced { font-size: 12px; color: var(--text-faint); white-space: nowrap; }
.md__toolbar { display: flex; align-items: center; gap: var(--sp-2); padding: var(--sp-2) var(--sp-5); background: var(--surface); border-bottom: 1px solid var(--line); flex-shrink: 0; }
.md__search { flex: 1 1 auto; width: auto; min-width: 0; }
.md__view { width: 110px; flex: none; }
.md__view--wide { width: 140px; }
.md__pills { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-left: auto; padding: 4px 0; }
.md__pills--grid { justify-content: flex-end; margin: calc(-1 * var(--sp-2)) 0 var(--sp-3); }
.md__pill { font: inherit; font-size: 12px; padding: 3px 10px; color: var(--accent); background: var(--accent-soft, var(--surface-2)); border: 1px solid var(--line); border-radius: 999px; cursor: pointer; }
.md__pill-clear { font: inherit; font-size: 12px; color: var(--text-muted); background: none; border: 0; cursor: pointer; }
.md__pill-clear:hover { color: var(--text); }
.md__filter { font: inherit; font-size: 13px; padding: 6px 10px; width: min(240px, 100%); border: 1px solid var(--line); border-radius: var(--r-sm); background: var(--surface); color: var(--text); }
.md__filter:focus { outline: none; border-color: var(--accent); }
.md__hosts { display: inline-flex; align-items: center; gap: 8px; margin-right: var(--sp-2); }
.md__hosts img { width: 22px; height: 22px; object-fit: contain; }
.md__hosts img.is-idle { opacity: 0.35; filter: grayscale(1); }

.md__body { position: relative; flex: 1; min-height: 0; overflow-y: auto; padding: var(--sp-5) var(--sp-5) calc(var(--sp-5) + 80px); }   /* bottom: same room as the game list, clear of the mini chat */
.md__stage { position: relative; flex: 1; min-height: 0; display: flex; flex-direction: column; }
.md__body--list { padding: 0 0 80px; }
.md__sync { display: flex; align-items: center; gap: var(--sp-2); flex: 0 0 auto; }      /* room under the last row: the mini chat floats bottom-left */
.md__group { width: 170px; flex: none; }
.md__section { display: flex; align-items: baseline; gap: 8px; margin: 0; padding: var(--sp-4) var(--sp-5) 0; font-size: 13px; font-weight: 600; color: var(--text); }
.md__section span { font-family: var(--font-mono); font-size: 11px; font-weight: 400; color: var(--text-faint); }
.md__section + .md__list { margin-top: var(--sp-2); }
.md__layout { display: flex; align-items: center; gap: 2px; }
.md__layout-sep { width: 1px; height: 18px; margin: 0 6px; background: var(--line); }

.md__cards--mini { border-top: 1px solid var(--line); }
.md__cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: var(--sp-5); padding: var(--sp-5); }
.md__card { display: flex; flex-direction: column; text-align: left; outline: none; font: inherit; color: inherit; padding: 0; overflow: hidden; background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-lg); box-shadow: var(--shadow-sm); cursor: pointer; transition: border-color 0.1s, box-shadow 0.1s; }
.md__cover { position: relative; display: flex; align-items: center; justify-content: center; aspect-ratio: 3 / 4; overflow: hidden; background: var(--surface-3); }
.md__cover-art, .md__cards--mini .md__cover > img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.md__cover-art.is-loading { visibility: hidden; }
.md__cover-spin { position: absolute; top: 50%; left: 50%; margin: -10px 0 0 -10px; }
.md__cover-ic { width: 96px; height: 96px; object-fit: contain; }
.md__cover-letter { font-size: 44px; font-weight: 600; color: var(--text-faint); }
.md__cover-tl { position: absolute; top: 8px; left: 8px; right: 50%; display: flex; flex-wrap: wrap; gap: 4px; }
.md__cover-tr { position: absolute; top: 8px; right: 8px; display: flex; gap: 4px; }
.md__cover-chip, .md__cover-badge { font-size: 10px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text); background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-sm); padding: 2px 6px; box-shadow: var(--shadow-sm); }
.md__cover-badge { display: flex; align-items: center; justify-content: center; width: 24px; height: 24px; padding: 0; color: var(--text-muted); font-size: 13px; }
.md__cover-badge.is-star { color: var(--accent); }
.md__cover-gone { position: absolute; left: 8px; bottom: 8px; font-size: 11px; font-weight: 600; color: var(--bad); background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-sm); padding: 2px 6px; }
.md__card-body { display: flex; flex-direction: column; gap: 4px; padding: var(--sp-3) var(--sp-4) var(--sp-4); flex: 1; }
.md__card-title { font-size: 14.5px; font-weight: 600; line-height: 1.3; text-align: center; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.md__card-body .md__variants { text-align: center; }
.md__card-row { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; }
.md__card-nodes { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; margin-top: auto; padding-top: var(--sp-2); }
.md__card-nodes img { width: 28px; height: 28px; object-fit: contain; }
.md__filter-menu { position: relative; }
.md__menu { position: absolute; top: calc(100% + 4px); left: 0; z-index: 6; display: flex; flex-direction: column; gap: 2px; min-width: 180px; padding: 6px; background: var(--surface); border: 1px solid var(--line); border-radius: var(--r); box-shadow: var(--shadow-md, var(--shadow-sm)); }
.md__menu label { display: flex; align-items: center; gap: 8px; padding: 6px 8px; font-size: 13px; border-radius: var(--r-sm); cursor: pointer; white-space: nowrap; }
.md__menu label:hover, .md__menu-item:hover { background: var(--surface-2); }
.md__menu--right { left: auto; right: 0; }
.md__menu-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; font: inherit; font-size: 13px; color: var(--text); text-align: left; background: none; border: 0; border-radius: var(--r-sm); cursor: pointer; white-space: nowrap; }
.md__menu-item img { width: 20px; height: 20px; object-fit: contain; }
.md__state { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-muted); margin-bottom: var(--sp-4); }
.md__body--list .md__state { padding: var(--sp-4) var(--sp-5); margin: 0; }
.md__state.is-bad { color: var(--bad); }

.md__grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: var(--sp-4); }
.md__tile-marks { position: absolute; top: 8px; right: 8px; display: flex; align-items: center; gap: 4px; }
.md__tile-owned { position: absolute; top: 10px; left: 8px; }   /* owned: top-left corner, the star stays top-right */
.md__tile { position: relative; display: flex; flex-direction: column; align-items: center; gap: 4px; padding: var(--sp-5) var(--sp-4) var(--sp-4); text-align: center; font: inherit; color: inherit; background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-lg); box-shadow: var(--shadow-sm); cursor: pointer; transition: border-color 0.1s, box-shadow 0.1s; }
.md__tile:hover { border-color: var(--line-strong); box-shadow: var(--shadow); }
.md__tile-ic { width: 88px; height: 88px; object-fit: contain; margin-bottom: 8px; }
.md__tile-letter { display: flex; align-items: center; justify-content: center; border-radius: var(--r-lg); background: var(--surface-3); color: var(--text-faint); font-size: 34px; font-weight: 600; }
.md__tile-brand { font-size: 11px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-faint); }
.md__tile-name { font-size: 14px; font-weight: 600; display: inline-flex; align-items: center; gap: 2px; }
.md__brand { padding: var(--sp-5) 0 var(--sp-3); }
.md__brand:first-of-type { padding-top: 0; }
.md__tile-count { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); }
.md__tile-nodes { display: flex; justify-content: center; flex-wrap: wrap; gap: 10px; margin-top: 10px; min-height: 32px; }
.md__tile-nodes img { width: 32px; height: 32px; object-fit: contain; }
.md__tile-nodes img.is-idle { opacity: 0.35; filter: grayscale(1); }

.md__list { list-style: none; }
.md__row { display: flex; align-items: center; gap: var(--sp-3); padding: 9px var(--sp-5); border-bottom: 1px solid var(--line); background: var(--surface); cursor: pointer; }
.md__row:hover { background: var(--surface-2); }
.md__row.is-open { background: var(--accent-soft); }
.md__row.is-gone .md__title { color: var(--text-faint); text-decoration: line-through; }
.md__star { width: 12px; flex: 0 0 auto; color: var(--accent); font-size: 12px; }
.md__title { font-size: 13.5px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.md__variants { font-size: 12px; color: var(--text-faint); white-space: nowrap; }
.md__badges { display: flex; align-items: center; gap: 6px; margin-left: auto; flex-wrap: wrap; justify-content: flex-end; }
/* same badge as MetadataCard's region */
.md__region { font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-muted); background: var(--surface-2); border: 1px solid var(--line); border-radius: var(--r-sm); padding: 1px 6px; }
.md__node { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 600; padding: 2px 7px; border-radius: 999px; background: var(--surface-3); color: var(--text-muted); white-space: nowrap; }
.md__node img { width: 13px; height: 13px; object-fit: contain; }
.md__node.is-physical { background: var(--accent-soft); color: var(--accent-hover); }
/* digital / physical copy marks: a file and a disc */
.md__kind { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 6px; background: var(--surface-3); color: var(--text-muted); }
.md__kind.is-physical { background: var(--accent-soft); color: var(--accent-hover); }
.md__node.is-save { color: var(--ok); }
.md__node.is-deleted { color: var(--bad); background: transparent; border: 1px dashed var(--bad); }

.md__stats { margin: 0 0 var(--sp-3); font-size: 12.5px; color: var(--text-muted); }
@media (max-width: 640px) {
  .md__stats { display: none; }
  .md__bar, .md__row { padding-left: var(--sp-4); padding-right: var(--sp-4); }
  /* phone: header wraps (title / actions), toolbar = search on its own row, then the dropdowns */
  .md__bar { flex-wrap: wrap; }
  .md__synced, .md__bar .md__hosts { display: none; }
  /* two cards per row: smaller covers and tighter body */
  .md__cards { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--sp-3); padding: var(--sp-3); }
  .md__card-body { padding: var(--sp-2) var(--sp-2) var(--sp-3); }
  .md__card-title { font-size: 13px; }
  .md__card-nodes img { width: 22px; height: 22px; }
  .md__cover-badge { width: 20px; height: 20px; }
  .md__toolbar { flex-wrap: wrap; padding-left: var(--sp-4); padding-right: var(--sp-4); }
  .md__search { flex: 1 1 100%; }
  .md__group { flex: 1 1 0; width: auto; }
  /* systems grid: filter on its own full-width row, the two buttons share the next */
  .md__actions { flex-wrap: wrap; }
  .md__filter--grid { flex: 1 1 100%; width: 100%; }
  .md__action { flex: 1 1 0; }
  .md__row { flex-wrap: wrap; }
  .md__badges { margin-left: 24px; justify-content: flex-start; }
  .md__variants { display: none; }
}
</style>
