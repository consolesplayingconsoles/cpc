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
import UiIconButton from '../ui/UiIconButton.vue'
import RomCard from '../RomCard.vue'
import UiSidePanel from '../ui/UiSidePanel.vue'
import UiPill from '../ui/UiPill.vue'
import UiStatusDot from '../ui/UiStatusDot.vue'
import UiSubTabs from '../ui/UiSubTabs.vue'
import { ICONS } from '../../composables/useIcons'
import { catalogueApi } from '../../api/catalogue'
import {
  listItems, saveParams, stopItem, openFolder, startItem, streamUrl,
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
  } catch (e) {
    error.value = `API unreachable: ${(e as Error).message}`
  } finally {
    loading.value = false
  }
}
watch(() => props.active, (on) => { if (on && !loaded.value) load() }, { immediate: true })

const coverUrl = (it: HomebrewItem) => it.game?.listed ? catalogueApi.coverUrl(it.game.system, it.game.key) : null
const mediaLink = (it: HomebrewItem) => it.game?.listed ? `/media/${it.game.system}/${it.game.key}` : null
const hideImg = (e: Event) => { (e.target as HTMLElement).style.display = 'none' }

// node -> group (game, mods only; '' otherwise) -> items. Within a game, vanilla (the
// unmodified rebuild every mod is measured against) comes first.
const isVanilla = (it: HomebrewItem) => it.kind === 'mods' && it.name === 'vanilla'
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
      [g, [...list].sort((a, b) => Number(isVanilla(b)) - Number(isVanilla(a)))] as [string, HomebrewItem[]]),
  }))
})

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
const runningId = ref<string | null>(null)
let es: EventSource | null = null

// Build: build, publish to Lab, sync (it shows up in Media). Send: rebuild and send it to the
// node, then open the game in Media, as the Translation tab's build does.
const sendingTo = ref<string | null>(null)
async function build(node?: string) {
  const it = selected.value
  if (!it || runningId.value) return
  if (!(await save())) return
  const target = node ? it.sendTargets.find(t => t.id === node) : null
  const output = openRun(target ? `Send ${it.name} to ${target.name}` : `Build ${it.name}`,
    { raw: '', ok: null, step: 'build', startedAt: Date.now() },
    { lastMs: lastRuns.value[runKey(it.id, node)] ?? null })
  runningId.value = it.id
  sendingTo.value = node ?? null
  let mediaPath: string | null = null
  es = new EventSource(streamUrl(it.id, node))
  es.addEventListener('media', (e: MessageEvent) => { mediaPath = e.data })
  es.addEventListener('line', (e: MessageEvent) => {
    output.value = { ...output.value, raw: output.value.raw + e.data + '\n' }
  })
  es.addEventListener('step', (e: MessageEvent) => {
    output.value = { ...output.value, step: e.data }
  })
  es.addEventListener('done', (e: MessageEvent) => {
    es?.close(); es = null
    const ok = e.data === 'ok'
    const stopped = e.data === 'failed:-15'          // SIGTERM from Stop
    output.value = {
      ...output.value, ok, step: ok ? 'done' : stopped ? 'stopped' : 'failed',
      raw: ok ? output.value.raw : output.value.raw + (stopped ? '\n[stopped]' : `\n[${e.data}]`),
    }
    if (ok) rememberRun(runKey(it.id, node), Date.now() - output.value.startedAt)
    runningId.value = null
    sendingTo.value = null
    load()   // the build recorded a new output
    if (ok && mediaPath) router.push(mediaPath)
  })
  es.onerror = () => {
    es?.close(); es = null
    if (output.value.ok === null) {
      output.value = { ...output.value, ok: false, step: 'failed', raw: output.value.raw + '\n[connection lost]' }
    }
    runningId.value = null
    sendingTo.value = null
  }
}

async function stop() {
  if (runningId.value) {
    try { await stopItem(runningId.value) } catch { /* the stream reports the outcome */ }
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
async function openOutput() {
  if (!selected.value) return
  openError.value = ''
  try { await openFolder(selected.value.id, true) } catch (e) { openError.value = (e as Error).message }
}

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
        <section v-for="sec in sections" :key="sec.node" class="hb__node">
          <h3 class="hb__node-head">
            <img v-if="ICONS[sec.node]" :src="ICONS[sec.node]" class="hb__node-ic" alt="" />
            {{ sec.name }}
          </h3>
          <template v-for="[group, list] in sec.groups" :key="group">
            <h4 v-if="group" class="hb__group">
              <span class="hb__group-title">{{ list[0].game?.title ?? group }}</span>
              <span class="hb__group-dir">{{ group }}</span>
            </h4>
            <button
              v-for="it in list" :key="it.id"
              class="hb__row" :class="{ 'is-open': it.id === selectedId, 'is-vanilla': isVanilla(it) }"
              @click="open(it)"
            >
              <span class="hb__row-title">{{ isVanilla(it) ? 'Vanilla' : it.title }}</span>
              <UiPill v-if="it.release" :tone="it.release.stable ? 'accent' : 'idle'">v{{ it.release.version }}</UiPill>
              <UiPill v-else tone="idle">Unreleased</UiPill>
              <span class="hb__row-name">{{ it.name }}</span>
              <UiStatusDot v-if="it.id === runningId" state="ok" title="Running" />
            </button>
          </template>
        </section>
      </nav>
      </UiSidePanel>

      <main class="hb__detail">
        <div v-if="!selected" class="hb__state" />
        <template v-else>
          <div class="hb__title-row">
            <RouterLink v-if="mediaLink(selected)" :to="mediaLink(selected)!" class="hb__cover-link" :title="'Open ' + selected.game?.title + ' in Media'">
              <img :src="coverUrl(selected)!" class="hb__cover" alt="" @error="hideImg" />
            </RouterLink>
            <img v-else-if="ICONS[selected.node]" :src="ICONS[selected.node]" class="hb__head-ic" alt="" />
            <div class="hb__titles">
              <h2 class="hb__title">{{ selected.title }}</h2>
              <div class="hb__sub">
                <img v-if="ICONS[selected.node]" :src="ICONS[selected.node]" class="hb__sub-ic" alt="" />
                <RouterLink v-if="selected.game?.listed" :to="`/media/${selected.game.system}`" class="hb__game-link" :title="'Open ' + selected.nodeName + ' in Media'">{{ selected.nodeName }}</RouterLink>
                <span v-else>{{ selected.nodeName }}</span>
                <template v-if="selected.game">
                  <span class="hb__sep">/</span>
                  <RouterLink v-if="mediaLink(selected)" :to="mediaLink(selected)!" class="hb__game-link">{{ selected.game.title }}</RouterLink>
                  <span v-else>{{ selected.game.title }}</span>
                </template>
                <template v-else-if="selected.group"><span class="hb__sep">/</span> {{ selected.group }}</template>
                <a
                  v-if="selected.release" class="hb__release"
                  :href="selected.release.url" target="_blank" rel="noopener" :title="selected.release.name"
                ><UiPill :tone="selected.release.stable ? 'accent' : 'idle'">{{ selected.release.stable ? 'Released' : 'Pre-release' }} v{{ selected.release.version }} ↗</UiPill></a>
                <UiPill v-else tone="idle">Unreleased</UiPill>
              </div>
              <div class="hb__path-row">
                <code class="hb__path">{{ selected.path }}</code>
                <UiIconButton title="Open folder" @click="openDir">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
                </UiIconButton>
              </div>
            </div>
          </div>
          <p v-if="openError" class="hb__state--bad">{{ openError }}</p>
          <p v-if="selected.description" class="hb__desc">{{ selected.description }}</p>

          <RomCard
            build play open :stop="runningId === selected.id"
            :send-targets="selected.sendTargets" :send-busy="sendingTo"
            :busy="!!runningId" :building="runningId === selected.id && !sendingTo"
            :build-title="selected.game?.listed ? 'Build, publish to Lab and sync the catalogue' : 'Build'"
            play-title="Start the last build from its dev tree in the desktop emulator (no rebuild)"
            open-title="Open the build folder"
            :error="cardError"
            class="hb__dev"
            @build="build()" @play="start" @open="openOutput" @send="id => build(id)" @stop="stop"
          >
            <div class="hb__dev-head">
              <span class="hb__dev-title">{{ selected.title }}</span>
              <span class="hb__dev-kind">dev build</span>
              <span v-if="selected.output" class="hb__hint">{{ selected.output.at.replace('T', ' ') }}</span>
            </div>
            <code v-if="selected.output" class="hb__path">{{ selected.output.path }}</code>
            <p v-else class="hb__hint">Not built yet.</p>
          </RomCard>

          <section v-if="selected.params.length" class="hb__params">
            <div class="hb__params-head">
              <h3 class="hb__section">Parameters</h3>
              <code v-for="pp in selected.paramsPaths" :key="pp" class="hb__path">{{ pp }}</code>
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
.hb__node + .hb__node { border-top: 8px solid var(--surface-3); }   /* a console break reads stronger than anything inside a section */
.hb__node-head { display: flex; align-items: center; gap: 10px; margin: 0; padding: var(--sp-3) var(--sp-4); font-size: 14px; font-weight: 600; white-space: nowrap; background: var(--surface-2); border-bottom: 1px solid var(--line); }
.hb__node-ic { width: 34px; height: 34px; object-fit: contain; }
.hb__group { display: flex; align-items: center; gap: var(--sp-2); margin: 0; padding: var(--sp-3) var(--sp-4) var(--sp-1); font-size: 12.5px; font-weight: 600; color: var(--text); min-width: 0; }
.hb__group-title { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.hb__group-dir { margin-left: auto; font-family: var(--font-mono); font-size: 10.5px; font-weight: 400; color: var(--text-faint); white-space: nowrap; }
.hb__row { display: flex; align-items: baseline; gap: var(--sp-2); width: 100%; padding: 7px var(--sp-4) 7px var(--sp-5); font: inherit; text-align: left; color: var(--text); background: none; border: 0; cursor: pointer; }
.hb__row:hover { background: var(--surface-2); }
.hb__row.is-open { background: var(--accent-soft); }
.hb__row-title { font-size: 13.5px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.hb__row-name { font-family: var(--font-mono); font-size: 11px; color: var(--text-faint); white-space: nowrap; margin-left: auto; }
.hb__row.is-vanilla .hb__row-title { font-style: italic; color: var(--text-muted); }
.hb__release { text-decoration: none; }
.hb__sub { display: flex; align-items: center; gap: var(--sp-2); flex-wrap: wrap; font-size: 13px; color: var(--text-muted); }
.hb__detail { flex: 1; min-width: 0; overflow-y: auto; padding: var(--sp-5) var(--sp-5) 340px; }   /* bottom: clear of the floating terminal */
.hb__title-row { display: flex; align-items: flex-start; gap: var(--sp-4); }
.hb__path-row { display: flex; align-items: center; gap: var(--sp-2); margin-top: var(--sp-1); }
.hb__head-ic { width: 72px; height: 72px; object-fit: contain; }
.hb__cover-link { flex: none; line-height: 0; }
.hb__cover { width: 220px; height: auto; max-height: 300px; object-fit: contain; border-radius: var(--r); box-shadow: var(--shadow); }
.hb__sub-ic { width: 26px; height: 26px; object-fit: contain; }
.hb__sep { color: var(--text-faint); }
.hb__game-link { color: var(--text-muted); text-decoration: none; border-bottom: 1px dotted var(--line-strong); }
.hb__game-link:hover { color: var(--accent); border-bottom-color: var(--accent); }
.hb__titles { min-width: 0; flex: 1; }
.hb__title { margin: 0 0 var(--sp-1); font-size: 20px; font-weight: 600; }
.hb__path { font-family: var(--font-mono); font-size: 11.5px; color: var(--text-faint); word-break: break-all; }
.hb__desc { margin: var(--sp-3) 0 0; font-size: 13.5px; line-height: 1.55; color: var(--text-muted); }
.hb__dev { margin: var(--sp-4) 0 var(--sp-5); }
.hb__dev-head { display: flex; align-items: baseline; gap: var(--sp-2); margin-bottom: 2px; }
.hb__dev-title { font-size: 13px; font-weight: 600; }
.hb__dev-kind { font-size: 12px; color: var(--text-muted); }
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
