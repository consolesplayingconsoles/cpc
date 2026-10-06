<script setup lang="ts">
// The Homebrew tab: projects the /homebrew API discovers under nodes/local/<node>/homebrew,
// split into Mods / Games / Tools sub-tabs. Sub-tab and item ride the URL
// (/homebrew/mods/<node>/<game>/<mod>, /homebrew/games/<node>/<name>) so a reload keeps
// them. No polling: the list loads when the tab is first shown and on Refresh.
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useRuns } from '../../composables/useRuns'
import { useRunDurations } from '../../composables/useRunDurations'
import UiButton from '../ui/UiButton.vue'
import HomebrewHead from './HomebrewHead.vue'
import UiSidePanel from '../ui/UiSidePanel.vue'
import UiPill from '../ui/UiPill.vue'
import UiStatusDot from '../ui/UiStatusDot.vue'
import UiSectionHead from '../ui/UiSectionHead.vue'
import UiSubTabs from '../ui/UiSubTabs.vue'
import { ICONS } from '../../composables/useIcons'
import { catalogueApi } from '../../api/catalogue'
import {
  listItems, saveParams, stopItem, openFolder, startItem, streamUrl, setFavourite, forgetRun,
  type HomebrewItem, type HomebrewKind,
} from '../../api/homebrew'

const props = defineProps<{ active: boolean }>()
const route = useRoute()
const router = useRouter()

const KINDS: { kind: HomebrewKind; label: string }[] = [
  { kind: 'mods', label: 'Mods' },
  { kind: 'games', label: 'Games' },
  { kind: 'tools', label: 'Tools' },
]
const kind = computed<HomebrewKind>(() => {
  const k = route.name === 'homebrew' ? route.params.kind : undefined
  return k === 'games' || k === 'tools' ? k : 'mods'
})
function setKind(k: HomebrewKind) { router.push({ name: 'homebrew', params: { kind: k } }) }

const all = ref<HomebrewItem[]>([])
const items = computed(() => all.value.filter(i => i.kind === kind.value))
const counts = computed(() => Object.fromEntries(KINDS.map(k => [k.kind, all.value.filter(i => i.kind === k.kind).length])))
const loading = ref(false)
const error = ref('')
const loaded = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    all.value = await listItems()
    loaded.value = true
    // A build still running (started before a reload, or in another tab): pick its console back up
    for (const it of all.value) {
      if (it.running && !runs.value[it.node]) follow(it, it.runningSend ?? undefined, true)
    }
  } catch (e) {
    error.value = `API unreachable: ${(e as Error).message}`
  } finally {
    loading.value = false
  }
}
watch(() => props.active, (on) => { if (on && !loaded.value) load() }, { immediate: true })

const coverUrl = (it: HomebrewItem) => it.game?.listed ? catalogueApi.coverUrl(it.game.system, it.game.key) : null
const mediaLink = (it: HomebrewItem) => it.game?.listed ? `/media/${it.game.system}/${it.game.key}` : null

// node -> group (game, mods only; '' otherwise) -> items.
const sections = computed(() => {
  const byNode = new Map<string, { name: string; groups: Map<string, HomebrewItem[]> }>()
  for (const it of items.value) {
    const sec = byNode.get(it.node) ?? { name: it.nodeName, groups: new Map<string, HomebrewItem[]>() }
    const key = it.group ?? ''
    sec.groups.set(key, [...(sec.groups.get(key) ?? []), it])
    byNode.set(it.node, sec)
  }
  return [...byNode.entries()].map(([node, sec]) => ({
    node, name: sec.name,
    groups: [...sec.groups.entries()].map(([g, list]) =>
      [g, list] as [string, HomebrewItem[]]),
  }))
})

// ── favourites ───────────────────────────────────────────────────────────────
// Starred items (what you are working on) are pinned on top of the list, across consoles,
// and stay in their console below too. Stored with the game favourites, as Media does.
const favourites = computed(() => items.value.filter(i => i.favourite)
  .sort((a, b) => a.title.localeCompare(b.title)))
async function toggleFavourite(it: HomebrewItem) {
  it.favourite = !it.favourite
  try { await setFavourite(it.id, it.favourite) } catch { it.favourite = !it.favourite }
}

// ── folded consoles ──────────────────────────────────────────────────────────
// A console section folds away, so a node you are not working on stops pushing the
// others off the list. Kept per viewer (cpc.<domain>.<leaf>). Folding hides the rows and
// nothing else: what is selected stays open on the right, and a folded console says how
// many items it holds and whether something in it is building.
const FOLDED_KEY = 'cpc.homebrew.folded'
const folded = ref<string[]>([])
try { folded.value = JSON.parse(localStorage.getItem(FOLDED_KEY) || '[]') } catch { /* ignore */ }
function toggleFold(node: string) {
  folded.value = folded.value.includes(node) ? folded.value.filter(n => n !== node) : [...folded.value, node]
  try { localStorage.setItem(FOLDED_KEY, JSON.stringify(folded.value)) } catch { /* ignore */ }
}
const shown = (sec: { node: string }) => !folded.value.includes(sec.node)
const countOf = (sec: { groups: [string, HomebrewItem[]][] }) =>
  sec.groups.reduce((n, [, list]) => n + list.length, 0)

// ── selection (URL, remembered across tabs) ──────────────────────────────────
// The URL carries the pick, but leaving the tab drops it, so the last one is kept
// in localStorage (cpc.<domain>.<leaf>) and reopened when we come back.
const SELECTED_KEY = 'cpc.homebrew.selected'
const selectedId = computed(() => {
  if (route.name !== 'homebrew') return null
  const rest = route.params.rest
  const parts = (Array.isArray(rest) ? rest : rest ? [rest] : []).filter(Boolean)
  if (!parts.length) return null
  const [node, ...tail] = parts
  return [node, kind.value, ...tail].join('/')
})
const selected = computed(() => items.value.find(i => i.id === selectedId.value) ?? null)

function open(it: HomebrewItem, replace = false) {
  const rest = it.group ? [it.node, it.group, it.name] : [it.node, it.name]
  const to = { name: 'homebrew', params: { kind: it.kind, rest } }
  if (replace) router.replace(to)
  else router.push(to)
}
// Nothing picked (or a stale URL): reopen the last pick, else the first item in list order.
watch([sections, selected, () => props.active], () => {
  if (!props.active || !loaded.value || selected.value || route.name !== 'homebrew') return
  let last: string | null = null
  try { last = localStorage.getItem(SELECTED_KEY) } catch { /* ignore */ }
  const it = items.value.find(i => i.id === last) ?? sections.value[0]?.groups[0]?.[1][0]
  if (it) open(it, true)
})

// A params file sits either in the item's own folder (show just ".env") or in its game's
// folder above it (show "<game>/.env"): the rest is the project path the header prints.
function envLabel(pp: string) {
  const base = selected.value?.path ?? ''
  if (pp.startsWith(base + '/')) return pp.slice(base.length + 1)
  const parts = pp.split('/')
  return parts.slice(-2).join('/')
}

// ── params form ───────────────────────────────────────────────────────────────
const draft = ref<Record<string, string>>({})
watch(selected, (it) => {
  draft.value = Object.fromEntries((it?.params ?? []).map(p => [p.key, p.value]))
  if (it) try { localStorage.setItem(SELECTED_KEY, it.id) } catch { /* ignore */ }
}, { immediate: true })
const dirty = computed(() => !!selected.value?.params.some(p => draft.value[p.key] !== p.value))
const saving = ref(false)
const saveError = ref('')

async function save(): Promise<boolean> {
  const it = selected.value
  if (!it || !dirty.value) return true
  saving.value = true
  saveError.value = ''
  try {
    await saveParams(it.id, draft.value)
    // reload the whole list: mods of one game share a .env, so their values changed too
    all.value = await listItems()
    return true
  } catch (e) {
    saveError.value = (e as Error).message
    return false
  } finally {
    saving.value = false
  }
}

// ── actions + terminal ────────────────────────────────────────────────────────
// How long this item's last successful build or send took, so the terminal can show a
// "~last" next to the live timer: a disc build is ten minutes of near-silence while the
// image and its EDC/ECC are written, which looks hung without a reference. Build and send
// are timed apart, since a send adds the copy to the console.
const { durations: lastRuns, remember: rememberRun } = useRunDurations('cpc.homebrew.lastMs')
const runKey = (itemId: string, node?: string | null) => itemId + ':' + (node || 'build')

const { openRun } = useRuns()
// One run per console at a time (builds of one console can share a toolchain and its
// caches); different consoles build side by side, each in its own terminal tab.
// console (item.node) -> the run: which item, and where it is sending (null = a build).
const runs = ref<Record<string, { id: string; sendTo: string | null }>>({})
const streams: Record<string, EventSource> = {}
const isRunning = (id: string) => Object.values(runs.value).some(r => r.id === id)
const runOf = (it: HomebrewItem) => (runs.value[it.node]?.id === it.id ? runs.value[it.node] : null)

// Build: build, publish to Lab, sync (it shows up in Media). Send: rebuild and send it to the
// node, then open the game in Media, as the Translation tab's build does.
async function build(node?: string) {
  const it = selected.value
  if (!it || runs.value[it.node]) return
  if (!(await save())) return
  follow(it, node, false)
}

// Open a terminal on the item's run. attach: follow a run that is already going (the API
// replays its console from the start); otherwise this starts it.
function follow(it: HomebrewItem, node: string | undefined, attach: boolean) {
  const target = node ? it.sendTargets.find(t => t.id === node) : null
  const output = openRun(target ? `Send ${it.name} to ${target.name}` : `Build ${it.name}`,
    { raw: '', ok: null, step: 'build', startedAt: Date.now() },
    { lastMs: lastRuns.value[runKey(it.id, node)] ?? null,
      // once it ends ok: Play what it just built, the same as the item's Start button
      after: { label: 'Play', run: () => startItem(it.id) },
      // closing the tab (or Clear done) drops the finished job in the API too
      onClose: () => { forgetRun(it.id).catch(() => { /* the API may be down: nothing to drop */ }) } })
  const consoleId = it.node
  runs.value = { ...runs.value, [consoleId]: { id: it.id, sendTo: node ?? null } }
  const finish = () => {
    streams[consoleId]?.close()
    delete streams[consoleId]
    const rest = { ...runs.value }
    delete rest[consoleId]
    runs.value = rest
  }
  let mediaPath: string | null = null
  const es = new EventSource(streamUrl(it.id, node, attach))
  streams[consoleId] = es
  es.addEventListener('media', (e: MessageEvent) => { mediaPath = e.data })
  es.addEventListener('line', (e: MessageEvent) => {
    output.value = { ...output.value, raw: output.value.raw + e.data + '\n' }
  })
  es.addEventListener('step', (e: MessageEvent) => {
    output.value = { ...output.value, step: e.data }
  })
  es.addEventListener('done', (e: MessageEvent) => {
    finish()
    if (e.data === 'none') {                         // it ended before we got there
      output.value = { ...output.value, ok: null, step: 'done', raw: output.value.raw + '[finished before this page attached]' }
      load(); return
    }
    const ok = e.data === 'ok'
    const stopped = e.data === 'failed:-15'          // SIGTERM from Stop
    output.value = {
      ...output.value, ok, step: ok ? 'done' : stopped ? 'stopped' : 'failed',
      raw: ok ? output.value.raw : output.value.raw + (stopped ? '\n[stopped]' : `\n[${e.data}]`),
    }
    if (ok) rememberRun(runKey(it.id, node), Date.now() - output.value.startedAt)
    load()   // the build recorded a new output
    if (ok && mediaPath) router.push(mediaPath)
  })
  es.onerror = () => {
    finish()
    if (output.value.ok === null) {
      output.value = { ...output.value, ok: false, step: 'failed', raw: output.value.raw + '\n[connection lost]' }
    }
  }
}

async function stop() {
  const it = selected.value
  if (it && isRunning(it.id)) {
    try { await stopItem(it.id) } catch { /* the stream reports the outcome */ }
  }
}

// ── start the last build from its dev tree ─────────────────────────────────────
const startError = ref('')
const starting = ref(false)
async function start() {
  if (!selected.value) return
  startError.value = ''
  starting.value = true
  try { await startItem(selected.value.id) } catch (e) { startError.value = (e as Error).message } finally { starting.value = false }
}
watch(selectedId, () => { startError.value = ''; openError.value = '' })
const cardError = computed(() => startError.value || openError.value || null)

// ── open folder ───────────────────────────────────────────────────────────────
const openError = ref('')
async function openDir() {
  if (!selected.value) return
  openError.value = ''
  try { await openFolder(selected.value.id) } catch (e) { openError.value = (e as Error).message }
}

const EMPTY: Record<HomebrewKind, string> = {
  mods: 'No mods found. A mod is a folder with build.sh at nodes/local/<node>/homebrew/mods/<game>/<mod>/.',
  games: 'No games found. A game is a folder with build.sh at nodes/local/<node>/homebrew/games/<game>/.',
  tools: 'No tools found. A tool is a folder with build.sh at nodes/local/<node>/homebrew/tools/<tool>/.',
}
</script>

<template>
  <div class="hb">
    <header class="hb__bar">
      <h2 class="hb__heading">Homebrew</h2>
      <UiButton variant="secondary" :loading="loading" loading-text="Refreshing" @click="load">Refresh</UiButton>
    </header>
    <UiSubTabs
      :model-value="kind"
      :tabs="KINDS.map(k => ({ key: k.kind, label: k.label, count: counts[k.kind] ?? 0 }))"
      @update:model-value="setKind($event as HomebrewKind)"
    />

    <div class="hb__stage">
      <UiSidePanel :width="320" storage-key="cpc.homebrew.listWidth" label="list">
      <nav class="hb__list">
        <div v-if="error" class="hb__state hb__state--bad">{{ error }}</div>
        <div v-else-if="loaded && !items.length" class="hb__state">{{ EMPTY[kind] }}</div>
        <!-- what you are working on: starred items on top, across consoles -->
        <section v-if="favourites.length" class="hb__node hb__favs">
          <h4 class="hb__group"><span class="hb__group-title">Favourites</span></h4>
          <div
            v-for="it in favourites" :key="'fav-' + it.id" role="button" tabindex="0"
            class="hb__row" :class="{ 'is-open': it.id === selectedId }"
            @click="open(it)" @keydown.enter="open(it)"
          >
            <button class="hb__fav is-on" title="Unfavourite" @click.stop="toggleFavourite(it)">★</button>
            <img v-if="ICONS[it.node]" :src="ICONS[it.node]" class="hb__fav-ic" :alt="it.nodeName" :title="it.nodeName" />
            <!-- no group heading up here, so the row says what the mod patches itself. The
                 console is the icon (named in its title), spelled out only without one. -->
            <span class="hb__row-title">
              {{ it.game?.title ? it.game.title + ': ' + it.title : it.title }}{{ ICONS[it.node] ? '' : ' (' + it.nodeName + ')' }}
            </span>
            <UiPill v-if="it.release" :tone="it.release.stable ? 'ok' : 'idle'">v{{ it.release.version }}</UiPill>
            <UiPill v-else-if="it.noRelease" tone="warn" class="hb__private" :title="'Never released: ' + it.noRelease">Private: {{ it.noRelease }}</UiPill>
            <UiPill v-else tone="idle">Unreleased</UiPill>
            <span class="hb__row-name">{{ it.name }}</span>
            <UiStatusDot v-if="isRunning(it.id)" state="ok" title="Running" />
          </div>
        </section>
        <section v-for="sec in sections" :key="sec.node" class="hb__node" :class="{ 'is-folded': !shown(sec) }">
          <UiSectionHead
            class="hb__node-head"
            :title="sec.name" :icon="ICONS[sec.node]" :count="countOf(sec)"
            :open="shown(sec)" @toggle="toggleFold(sec.node)"
          >
            <UiStatusDot v-if="!shown(sec) && sec.groups.some(([, l]) => l.some(i => isRunning(i.id)))" state="ok" title="A build is running in here" />
          </UiSectionHead>
          <template v-if="shown(sec)">
          <template v-for="[group, list] in sec.groups" :key="group">
            <h4 v-if="group" class="hb__group">
              <span class="hb__group-title">{{ list[0].game?.title ?? group }}</span>
              <span class="hb__group-dir">{{ group }}</span>
            </h4>
            <div
              v-for="it in list" :key="it.id" role="button" tabindex="0"
              class="hb__row" :class="{ 'is-open': it.id === selectedId }"
              @click="open(it)" @keydown.enter="open(it)"
            >
              <button class="hb__fav" :class="{ 'is-on': it.favourite }" :title="it.favourite ? 'Unfavourite' : 'Favourite'"
                      @click.stop="toggleFavourite(it)">{{ it.favourite ? '★' : '☆' }}</button>
              <span class="hb__row-title">{{ it.title }}</span>
              <UiPill v-if="it.release" :tone="it.release.stable ? 'ok' : 'idle'">v{{ it.release.version }}</UiPill>
              <!-- never publishable (someone else's IP) reads differently from not yet released -->
              <UiPill v-else-if="it.noRelease" tone="warn" class="hb__private" :title="'Never released: ' + it.noRelease">Private: {{ it.noRelease }}</UiPill>
              <UiPill v-else tone="idle">Unreleased</UiPill>
              <span class="hb__row-name">{{ it.name }}</span>
              <UiStatusDot v-if="isRunning(it.id)" state="ok" title="Running" />
            </div>
          </template>
          </template>
        </section>
      </nav>
      </UiSidePanel>

      <main class="hb__detail">
        <div v-if="!selected" class="hb__state" />
        <template v-else>
          <HomebrewHead
            :item="selected" :icon="ICONS[selected.node]"
            :cover-url="coverUrl(selected)" :media-link="mediaLink(selected)"
            :send-targets="selected.sendTargets" :send-busy="runOf(selected)?.sendTo ?? null"
            :busy="!!runs[selected.node]" :building="!!runOf(selected) && !runOf(selected)?.sendTo"
            :running="isRunning(selected.id)"
            :build-title="selected.game?.listed ? 'Build, publish to Lab and sync the catalogue' : 'Build'"
            :error="cardError"
            @build="build()" @play="start" @open-output="openDir" @send="id => build(id)"
            @stop="stop" @open-dir="openDir"
          />
          <p v-if="openError" class="hb__state--bad">{{ openError }}</p>

          <section v-if="selected.params.length" class="hb__params">
            <div class="hb__params-head">
              <h3 class="hb__section">Parameters</h3>
              <!-- the header already says the project folder: name only what differs,
                   which for a mod's own .env is the file and for a game's shared one the
                   folder it is shared from -->
              <code v-for="pp in selected.paramsPaths" :key="pp" class="hb__path" :title="pp">{{ envLabel(pp) }}</code>
            </div>
            <label v-for="p in selected.params" :key="p.key" class="hb__param">
              <span class="hb__key">{{ p.key }}<UiPill v-if="p.scope === 'game'" tone="idle" class="hb__shared" title="Shared by every mod of this game">shared</UiPill></span>
              <input v-model="draft[p.key]" class="hb__input" :placeholder="p.default" spellcheck="false" />
              <span v-if="p.help" class="hb__help">{{ p.help }}</span>
            </label>
            <div class="hb__save">
              <span v-if="saveError" class="hb__state--bad">{{ saveError }}</span>
              <span v-else-if="dirty" class="hb__hint">Unsaved: saved automatically when you run an action</span>
              <UiButton variant="secondary" :disabled="!dirty" :loading="saving" loading-text="Saving" @click="save">Save</UiButton>
            </div>
          </section>
          <p v-else class="hb__hint">No parameters (add a .env.sample next to build.sh to get a form here).</p>
        </template>
      </main>
    </div>

  </div>
</template>

<style scoped>
.hb { position: relative; display: flex; flex-direction: column; height: 100%; background: var(--surface-2); font-family: var(--font-sans); color: var(--text); }
.hb__bar { display: flex; align-items: center; gap: var(--sp-3); padding: var(--sp-3) var(--sp-5); background: var(--surface); border-bottom: 1px solid var(--line); flex-shrink: 0; }
.hb__heading { margin: 0 auto 0 0; font-size: 16px; font-weight: 600; }
.hb__stage { position: relative; flex: 1; min-height: 0; display: flex; }
.hb__list { flex: 1; min-height: 0; overflow-y: auto; padding-bottom: 96px; }   /* frame (surface, edge border) comes from UiSidePanel */
.hb__node { padding-bottom: var(--sp-3); }
.hb__node.is-folded { padding-bottom: 0; }   /* folded: the header IS the block, no gap under it */
/* The header is UiSectionHead (the Media tab's folding sections); this only frames it:
   one console per block, a line between them, the console's surface behind the title. */
.hb__node-head { background: var(--surface-2); border-bottom: 1px solid var(--line); }
.hb__node + .hb__node .hb__node-head { border-top: 1px solid var(--line); }
.hb__group { display: flex; align-items: center; gap: var(--sp-2); margin: 0; padding: var(--sp-3) var(--sp-4) var(--sp-1); font-size: 12.5px; font-weight: 600; color: var(--text); min-width: 0; }
.hb__group-title { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.hb__group-dir { margin-left: auto; font-family: var(--font-mono); font-size: 10.5px; font-weight: 400; color: var(--text-faint); white-space: nowrap; }
.hb__row { display: flex; align-items: baseline; gap: var(--sp-2); width: 100%; padding: 7px var(--sp-4) 7px var(--sp-5); font: inherit; text-align: left; color: var(--text); background: none; border: 0; cursor: pointer; }
.hb__row:hover { background: var(--surface-2); }
/* favourite toggle, as on a Media row: always there, filled when starred */
.hb__fav { border: 0; background: transparent; padding: 0; font: inherit; font-size: 12px; line-height: 1; cursor: pointer; color: var(--accent);
           width: 12px; flex: 0 0 auto; align-self: center; margin-right: calc(var(--sp-3) - var(--sp-2)); }   /* as .md__star: centred, 12px, --sp-3 to the title */
.hb__fav:not(.is-on) { color: var(--text-faint); }
.hb__fav-ic { width: 14px; height: 14px; object-fit: contain; align-self: center; flex: none; }
.hb__row.is-open { background: var(--accent-soft); }
/* "Private: Intellectual Property" is longer than the panel: let the pill clip, not the row */
.hb__private { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-block; }
.hb__row-title { font-size: 13.5px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.hb__row-name { font-family: var(--font-mono); font-size: 11px; color: var(--text-faint); white-space: nowrap; margin-left: auto; }
.hb__detail { flex: 1; min-width: 0; overflow-y: auto; padding: var(--sp-5) var(--sp-5) 340px; }   /* bottom: clear of the floating terminal */
.hb__path { font-family: var(--font-mono); font-size: 11.5px; color: var(--text-faint); word-break: break-all; }
.hb__params { padding: var(--sp-4); background: var(--surface); border: 1px solid var(--line); border-radius: var(--r-lg); box-shadow: var(--shadow-sm); }
.hb__params-head { display: flex; align-items: baseline; flex-wrap: wrap; gap: var(--sp-3); margin-bottom: var(--sp-3); }
.hb__shared { margin-left: 6px; }
.hb__section { margin: 0; font-size: 13px; font-weight: 600; }
.hb__param { display: grid; grid-template-columns: minmax(180px, 240px) 1fr; column-gap: var(--sp-3); row-gap: 2px; align-items: center; padding: var(--sp-2) 0; border-top: 1px solid var(--line); }
.hb__key { font-family: var(--font-mono); font-size: 12px; color: var(--text); word-break: break-all; }
.hb__input { font-family: var(--font-mono); font-size: 12.5px; padding: 6px 8px; border: 1px solid var(--line); border-radius: var(--r-sm); background: var(--surface); color: var(--text); min-width: 0; }
.hb__input:focus { outline: none; border-color: var(--accent); }
.hb__help { grid-column: 2; font-size: 12px; color: var(--text-faint); }
.hb__save { display: flex; align-items: center; justify-content: flex-end; gap: var(--sp-3); margin-top: var(--sp-3); }
.hb__hint { font-size: 12px; color: var(--text-faint); }
.hb__state { padding: var(--sp-4) var(--sp-5); font-size: 13px; color: var(--text-muted); }
.hb__state--bad { color: var(--bad); font-size: 12.5px; }
</style>
