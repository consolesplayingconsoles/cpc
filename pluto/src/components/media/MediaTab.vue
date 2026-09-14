<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { NodeMap } from '../../composables/useNodes'
import { ICONS } from '../../composables/useIcons'
import { catalogueApi, type SystemSummary, type SystemView, type Game, type MissingCover } from '../../api/catalogue'
import consolesConfig from '../../../config/consoles.json'
import UiButton from '../ui/UiButton.vue'
import UiSpinner from '../ui/UiSpinner.vue'
import UiIconButton from '../ui/UiIconButton.vue'
import UiSelect from '../ui/UiSelect.vue'
import UiCopyButton from '../ui/UiCopyButton.vue'
import Terminal, { type TerminalOutput } from '../Terminal.vue'
import GameDrawer from './GameDrawer.vue'
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

// ── Missing covers: games with no image linked in the catalogue (no upload, no downloaded
// art), across all systems. Local only. Click one -> its drawer (upload, or the art fetch).
const missingOpen = ref(false)
const missing = ref<MissingCover[] | null>(null)
const missingLoading = ref(false)
async function toggleMissing() {
  missingOpen.value = !missingOpen.value
  if (!missingOpen.value || missingLoading.value) return
  missingLoading.value = true
  try {
    const r = await catalogueApi.missingCovers()
    missing.value = r.games
  } catch {
    apiError.value = 'Catalogue API unreachable'
  } finally {
    missingLoading.value = false
  }
}
// Per-system sections fold; big ones (MAME) start folded so the list stays scannable.
const missingFolded = ref<Record<string, boolean>>({})
const isFolded = (sys: string, n: number) => missingFolded.value[sys] ?? n > 20
function toggleFold(sys: string, n: number) { missingFolded.value[sys] = !isFolded(sys, n) }
const missingBySystem = computed(() => {
  const by = new Map<string, MissingCover[]>()
  for (const m of missing.value ?? []) by.set(m.system, [...(by.get(m.system) ?? []), m])
  return [...by.entries()].sort(([a], [b]) => systemName(a).localeCompare(systemName(b)))
})

// Grid filter: system name, brand or folder key ("sega", "dreamcast", "ngpc").
const systemFilter = ref('')

// Families: brand, then name. Systems without a brand (arcade) go last.
const sortedSystems = computed(() => [...systems.value].filter(s => {
  const q = systemFilter.value.trim().toLowerCase()
  return !q || [s.system, systemName(s.system), SYSTEMS[s.system]?.brand ?? ''].some(t => t.toLowerCase().includes(q))
}).sort((a, b) => {
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
watch(system, () => { favOnly.value = false; groupBy.value = '' })

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

// Card shortcuts: Play / Open folder act on the game's ROM when there is exactly ONE
// present copy; with several (regions, mods, nodes) they're disabled and the drawer picks.
const { emulator, canPlay, canOpen, play, openFolder } = useRomActions(system, nodesRef)
const soleRom = (g: Game) => {
  const present = g.files.filter(f => f.status === 'present')
  return present.length === 1 ? present[0] : null
}
const pickHint = (g: Game) => g.files.some(f => f.status === 'present') ? 'Several copies: open the game to pick one' : 'No copy present'

// System tiles + the system page show every node CONFIGURED for the system (nodeConsoles:
// capable), dimmed when it holds none of its games; game cards show only nodes where the
// game is PRESENT. Same source as the API's hosts list.
function hostsFor(sys: string): string[] {
  const nc = (consolesConfig.nodeConsoles ?? {}) as Record<string, string[]>
  return Object.keys(nc).filter(n => (nc[n].includes('*') || nc[n].includes(sys)) && ICONS[n]).sort()
}

const hostsWithGames = computed(() => new Set((view.value?.games ?? []).flatMap(g => g.nodes)))

const games = computed<Game[]>(() => {
  const q = filter.value.trim().toLowerCase()
  const all = (view.value?.games ?? []).filter(g => !favOnly.value || g.favourite)
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
const syncing = computed(() => syncOut.value?.ok === null)
function sync(target: string) {
  const startedAt = Date.now()
  syncOut.value = { raw: '', ok: null, step: target === '*' ? 'all systems' : systemName(target), startedAt }
  const es = new EventSource(catalogueApi.syncUrl(target))
  es.addEventListener('line', (e: MessageEvent) => {
    if (syncOut.value) syncOut.value = { ...syncOut.value, raw: syncOut.value.raw + e.data + '\n' }
  })
  es.addEventListener('done', (e: MessageEvent) => {
    es.close()
    const ok = e.data === 'ok'
    if (syncOut.value) syncOut.value = { ...syncOut.value, ok, step: ok ? 'done' : 'failed' }
    load()
  })
  es.onerror = () => {
    es.close()
    if (syncOut.value?.ok === null) syncOut.value = { ...syncOut.value, raw: syncOut.value.raw + '\n[connection lost]', ok: false, step: 'failed' }
  }
}
const termStyle = { right: '16px', bottom: '16px', width: 'min(560px, calc(100% - 32px))', height: '260px' }
</script>

<template>
  <div class="md">
    <!-- ── Grid: systems with games ── -->
    <template v-if="!system">
      <div class="md__body">
        <div class="md__actions">
          <input v-if="!missingOpen" v-model="systemFilter" class="md__filter md__filter--grid" type="search" placeholder="Filter systems" />
          <UiButton :class="{ 'is-on': missingOpen }" @click="toggleMissing">
            {{ missingOpen ? 'All systems' : 'Missing covers' }}<template v-if="missing && !missingOpen"> ({{ missing.length }})</template>
          </UiButton>
          <UiButton variant="primary" :loading="syncing" loading-text="Syncing…" @click="sync('*')">Sync all</UiButton>
        </div>
        <template v-if="missingOpen">
          <p v-if="missingLoading" class="md__state"><UiSpinner /> Checking covers…</p>
          <p v-else-if="missing && !missing.length" class="md__state">Every game has a cover.</p>
          <section v-for="[sys, list] in missingBySystem" :key="sys" class="md__missing">
            <button class="md__section md__fold" :aria-expanded="!isFolded(sys, list.length)" @click="toggleFold(sys, list.length)">
              <svg class="md__fold-chev" :class="{ 'is-open': !isFolded(sys, list.length) }" width="12" height="12" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
              <img v-if="systemIcon(sys)" :src="systemIcon(sys)" class="md__missing-ic" alt="" />
              {{ systemName(sys) }} <span>{{ list.length }}</span>
            </button>
            <ul v-if="!isFolded(sys, list.length)" class="md__list">
              <li v-for="m in list" :key="m.key" class="md__row" @click="go(m.system, m.key)">
                <span class="md__title">{{ m.title }}</span>
              </li>
            </ul>
          </section>
        </template>
        <p v-if="apiError" class="md__state is-bad">{{ apiError }}</p>
        <p v-else-if="loading && !systems.length" class="md__state"><UiSpinner /> Loading catalogue…</p>
        <p v-else-if="!systems.length" class="md__state">No games yet. Sync all to build the catalogue.</p>
        <p v-if="!missingOpen && systems.length && !sortedSystems.length" class="md__state">No system matches "{{ systemFilter }}".</p>
        <template v-if="!missingOpen">
         <template v-for="grp in brandGroups" :key="grp.brand">
          <h3 class="md__section md__brand">{{ grp.brand }} <span>{{ grp.systems.length }}</span></h3>
          <div class="md__grid">
          <div v-for="s in grp.systems" :key="s.system" class="md__tile" role="button" tabindex="0" @click="go(s.system)" @keydown.enter="go(s.system)">
            <img v-if="systemIcon(s.system)" :src="systemIcon(s.system)" class="md__tile-ic" alt="" />
            <span v-else class="md__tile-ic md__tile-letter">{{ systemName(s.system).slice(0, 1) }}</span>
            <span class="md__tile-name">{{ systemName(s.system) }} <UiCopyButton :text="systemName(s.system)" title="Copy system name" /></span>
            <span class="md__tile-count">{{ s.games }} game{{ s.games === 1 ? '' : 's' }}<template v-if="s.physical"> · {{ s.physical }} physical</template></span>
            <span class="md__tile-nodes">
              <img v-for="n in hostsFor(s.system)" :key="n" :src="ICONS[n]" alt=""
                   :class="{ 'is-idle': !s.nodes.includes(n) }"
                   :title="nodeName(n) + (s.nodes.includes(n) ? '' : ' (configured, no games yet)')" />
            </span>
          </div>
          </div>
         </template>
        </template>
      </div>
    </template>

    <!-- ── One system: games A-Z ── -->
    <template v-else>
      <header class="md__bar">
        <div class="md__title-row">
          <UiButton class="md__back" @click="go()">‹ Media</UiButton>
          <img v-if="systemIcon(system)" :src="systemIcon(system)" class="md__head-ic" alt="" />
          <span class="md__head-name">
            <span v-if="SYSTEMS[system]?.brand" class="md__tile-brand">{{ SYSTEMS[system].brand }}</span>
            <span class="md__head-title">{{ systemName(system) }}</span>
          </span>
        </div>
        <input v-model="filter" class="md__filter" type="search" placeholder="Filter games" />
        <span v-if="groupFields.length" class="md__group">
          <UiSelect v-model="groupBy">
            <option value="">No grouping</option>
            <option v-for="f in groupFields" :key="f" :value="f">Group by {{ FIELD_LABEL[f].toLowerCase() }}</option>
          </UiSelect>
        </span>
        <span class="md__layout">
          <UiIconButton variant="ghost" :active="favOnly" title="Favourites only" @click="favOnly = !favOnly">
            <svg width="15" height="15" viewBox="0 0 24 24" :fill="favOnly ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M12 3.5l2.6 5.3 5.9.9-4.2 4.1 1 5.8L12 16.9l-5.3 2.7 1-5.8L3.5 9.7l5.9-.9z"/></svg>
          </UiIconButton>
          <span class="md__layout-sep" />
          <UiIconButton variant="ghost" :active="layout === 'cards'" title="Cards" @click="setLayout('cards')">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/></svg>
          </UiIconButton>
          <UiIconButton variant="ghost" :active="layout === 'list'" title="List" @click="setLayout('list')">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M5 6h14M5 12h14M5 18h14"/></svg>
          </UiIconButton>
        </span>
        <UiButton :loading="syncing" loading-text="Syncing…" @click="sync(system)">Sync</UiButton>
      </header>
      <div class="md__meta-bar">
        <span v-if="view">{{ view.games.length }} games</span>
        <span v-if="view?.hosts.length" class="md__hosts">
          <img v-for="n in view.hosts" :key="n" :src="ICONS[n]" alt=""
               :class="{ 'is-idle': !hostsWithGames.has(n) }"
               :title="nodeName(n) + (hostsWithGames.has(n) ? '' : ' (configured, no games yet)')" />
        </span>
        <span v-if="view?.syncedAt">Synced {{ view.syncedAt.slice(0, 16).replace('T', ' ') }}</span>
      </div>
      <!-- stage = the non-scrolling frame: the drawer pins to it, the body scrolls inside -->
      <div class="md__stage">
      <div class="md__body md__body--list" @click="gameKey && go(system)">
        <p v-if="apiError" class="md__state is-bad">{{ apiError }}</p>
        <p v-else-if="loading && !view" class="md__state"><UiSpinner /> Loading…</p>
        <template v-for="sec in sections" :key="sec.label">
        <h3 v-if="sec.label" class="md__section">{{ sec.label }} <span>{{ sec.games.length }}</span></h3>
        <div v-if="layout === 'cards'" class="md__cards">
          <div v-for="g in sec.games" :id="'media-row-' + g.key" :key="g.key"
               class="md__card" :class="{ 'is-open': g.key === gameKey, 'is-gone': onlyDeleted(g) }"
               role="button" tabindex="0"
               @click.stop="go(system, g.key)" @keydown.enter.self="go(system, g.key)">
            <span class="md__cover">
              <template v-if="coverSrc(g)">
                <img :src="coverSrc(g)" loading="lazy" alt="" :class="{ 'is-loading': !coverLoaded[g.key] }"
                     @load="coverLoaded[g.key] = true" @error="g.cover = 'miss'" />
                <UiSpinner v-if="!coverLoaded[g.key]" class="md__cover-spin" :size="20" />
              </template>
              <img v-else-if="systemIcon(system)" :src="systemIcon(system)" class="md__tile-ic md__cover-ic" alt="" />
              <span v-else class="md__cover-letter">{{ g.title.slice(0, 1) }}</span>
              <span v-if="g.favourite" class="md__card-star">★</span>
            </span>
            <span class="md__card-body">
              <span class="md__card-title">{{ g.title }} <UiCopyButton :text="g.title" title="Copy title" /></span>
              <span v-if="variantSummary(g)" class="md__variants">{{ variantSummary(g) }}</span>
              <span v-if="g.regions.length" class="md__card-row">
                <span v-for="r in g.regions" :key="r" class="md__region">{{ r }}</span>
              </span>
              <span class="md__card-row md__card-foot">
                <img v-for="n in g.nodes" :key="n" :src="ICONS[n]" :title="nodeName(n)" class="md__card-node" alt="" />
                <span v-if="g.physical.length" class="md__node is-physical">Physical</span>
                <span v-if="g.saves.length" class="md__node is-save" :title="'Save on ' + g.saves.map(nodeName).join(', ')">Save</span>
                <span v-if="onlyDeleted(g)" class="md__node is-deleted">Deleted</span>
              </span>
              <span class="md__card-actions" @click.stop>
                <UiIconButton :disabled="!soleRom(g) || !canPlay(soleRom(g)!)"
                              :title="soleRom(g) ? (canPlay(soleRom(g)!) ? 'Play in ' + emulator?.name : 'Not playable from here') : pickHint(g)"
                              @click="play(soleRom(g)!)">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13a.8.8 0 0 0 1.2.7l10.4-6.5a.8.8 0 0 0 0-1.4L9.2 4.8A.8.8 0 0 0 8 5.5z"/></svg>
                </UiIconButton>
                <UiIconButton :disabled="!soleRom(g) || !canOpen(soleRom(g)!)"
                              :title="soleRom(g) ? (canOpen(soleRom(g)!) ? 'Open folder' : 'No folder access') : pickHint(g)"
                              @click="openFolder(soleRom(g)!)">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
                </UiIconButton>
              </span>
            </span>
          </div>
        </div>
        <ul v-else class="md__list">
          <li v-for="g in sec.games" :id="'media-row-' + g.key" :key="g.key"
              class="md__row" :class="{ 'is-open': g.key === gameKey, 'is-gone': onlyDeleted(g) }"
              @click.stop="go(system, g.key)">
            <span class="md__star" :class="{ 'is-on': g.favourite }">{{ g.favourite ? '★' : '' }}</span>
            <span class="md__title">{{ g.title }}</span>
            <span class="md__variants">{{ variantSummary(g) }}</span>
            <span class="md__badges">
              <span v-for="r in g.regions" :key="r" class="md__region">{{ r }}</span>
              <span v-for="n in g.nodes" :key="n" class="md__node" :title="nodeName(n)">
                <img v-if="ICONS[n]" :src="ICONS[n]" alt="" />{{ nodeName(n) }}
              </span>
              <span v-if="g.physical.length" class="md__node is-physical">Physical</span>
              <span v-if="g.saves.length" class="md__node is-save" :title="'Save on ' + g.saves.map(nodeName).join(', ')">Save</span>
              <span v-if="onlyDeleted(g)" class="md__node is-deleted">Deleted</span>
            </span>
          </li>
        </ul>
        </template>
      </div>
      <GameDrawer v-if="openGame && view" :system="view.system" :game="openGame" :nodes="nodes" :system-icon="systemIcon(system)"
                  :cover-version="coverVersion[openGame.key]"
                  @close="go(system)" @favourite="toggleFavourite(openGame, $event)" @cover-changed="coverChanged(openGame)" @relabeled="relabeled" />
      </div>
    </template>

    <Terminal v-if="syncOut" title="sync" :output="syncOut" :card-style="termStyle" @close="syncOut = null" />
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
.md__title-row { display: flex; align-items: center; gap: var(--sp-2); margin-right: auto; }
.md__back { margin-right: 12px; }
.md__head-ic { width: 32px; height: 32px; object-fit: contain; }
.md__head-name { display: flex; flex-direction: column; line-height: 1.2; }
.md__head-title { font-size: 15px; font-weight: 600; }
.md__filter { font: inherit; font-size: 13px; padding: 6px 10px; width: min(240px, 100%); border: 1px solid var(--line); border-radius: var(--r-sm); background: var(--surface); color: var(--text); }
.md__filter:focus { outline: none; border-color: var(--accent); }
.md__hosts { display: inline-flex; align-items: center; gap: 8px; }
.md__hosts img { width: 22px; height: 22px; object-fit: contain; }
.md__hosts img.is-idle { opacity: 0.35; filter: grayscale(1); }
.md__meta-bar { display: flex; align-items: center; gap: var(--sp-4); padding: 6px var(--sp-5); font-size: 12px; color: var(--text-faint); border-bottom: 1px solid var(--line); background: var(--surface); flex-wrap: wrap; }

.md__body { position: relative; flex: 1; min-height: 0; overflow-y: auto; padding: var(--sp-5); }
.md__stage { position: relative; flex: 1; min-height: 0; display: flex; flex-direction: column; }
.md__body--list { padding: 0; }
.md__group { width: 170px; }
.md__section { display: flex; align-items: baseline; gap: 8px; margin: 0; padding: var(--sp-4) var(--sp-5) 0; font-size: 13px; font-weight: 600; color: var(--text); }
.md__section span { font-family: var(--font-mono); font-size: 11px; font-weight: 400; color: var(--text-faint); }
.md__section + .md__list { margin-top: var(--sp-2); }
.md__layout { display: flex; align-items: center; gap: 2px; }
.md__layout-sep { width: 1px; height: 18px; margin: 0 6px; background: var(--line); }

.md__cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: var(--sp-4); padding: var(--sp-5); }
.md__card { display: flex; flex-direction: column; text-align: left; outline: none; font: inherit; color: inherit; padding: 0; overflow: hidden; background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-lg); box-shadow: var(--shadow-sm); cursor: pointer; transition: border-color 0.1s, box-shadow 0.1s; }
.md__card:hover, .md__card:focus-visible { border-color: var(--line-strong); box-shadow: var(--shadow); }
.md__card.is-open { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
.md__card.is-gone .md__card-title { color: var(--text-faint); text-decoration: line-through; }
.md__cover { position: relative; display: flex; align-items: center; justify-content: center; aspect-ratio: 4 / 3; max-width: 100%; background: var(--surface-3); }
.md__cover img { width: 100%; height: 100%; object-fit: contain; padding: var(--sp-2); }
.md__cover img.is-loading { visibility: hidden; }
.md__cover-spin { position: absolute; top: 50%; left: 50%; margin: -10px 0 0 -10px; }
/* no art: the system icon, exactly as on the system tile */
.md__cover img.md__cover-ic { width: 88px; height: 88px; padding: 0; margin: 0; }
.md__cover-letter { font-size: 40px; font-weight: 600; color: var(--text-faint); }
.md__card-star { position: absolute; top: 6px; right: 8px; color: var(--accent); font-size: 16px; }
.md__card-body { display: flex; flex-direction: column; gap: 6px; padding: var(--sp-3); flex: 1; }
.md__card-title { font-size: 14px; font-weight: 600; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.md__card-row { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; }
.md__card-foot { margin-top: auto; padding-top: 4px; justify-content: center; gap: 6px 10px; }
.md__card-node { width: 30px; height: 30px; object-fit: contain; }
.md__card-actions { display: flex; justify-content: center; gap: 8px; padding-top: 6px; border-top: 1px solid var(--line); }
.md__state { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-muted); margin-bottom: var(--sp-4); }
.md__body--list .md__state { padding: var(--sp-4) var(--sp-5); margin: 0; }
.md__state.is-bad { color: var(--bad); }

.md__grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: var(--sp-4); }
.md__tile { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: var(--sp-5) var(--sp-4) var(--sp-4); text-align: center; font: inherit; color: inherit; background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-lg); box-shadow: var(--shadow-sm); cursor: pointer; transition: border-color 0.1s, box-shadow 0.1s; }
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
.md__node.is-save { color: var(--ok); }
.md__node.is-deleted { color: var(--bad); background: transparent; border: 1px dashed var(--bad); }

@media (max-width: 640px) {
  .md__bar, .md__row { padding-left: var(--sp-4); padding-right: var(--sp-4); }
  .md__row { flex-wrap: wrap; }
  .md__badges { margin-left: 24px; justify-content: flex-start; }
  .md__variants { display: none; }
}
</style>
