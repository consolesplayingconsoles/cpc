<script setup lang="ts">
import RomCard from '../RomCard.vue'
import type { Game, CatalogueFile } from '../../api/catalogue'
import type { NodeMap } from '../../composables/useNodes'
import { ICONS } from '../../composables/useIcons'
import UiClose from '../ui/UiClose.vue'
import AdminCommand from './AdminCommand.vue'
import UiIconButton from '../ui/UiIconButton.vue'
import UiPill from '../ui/UiPill.vue'
import UiSpinner from '../ui/UiSpinner.vue'
import MetadataCard, { type GameMeta } from '../MetadataCard.vue'
import { catalogueApi } from '../../api/catalogue'
import { useRomActions } from '../../composables/useRomActions'
import { computed, onMounted, ref, toRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import { translationApi, type ProjectSummary } from '../../api/translation'
import { names } from '../../lib/catalogueNames'

// One game, everything we know about it: every copy (ROM files per node, grouped by
// variant) and every shelf copy. Regions, mods, translations and physical are ONE
// entry by design -- the grouping below is what makes that readable (where Batocera
// shows each file as its own game).
const props = defineProps<{ system: string; game: Game; nodes: NodeMap; systemIcon?: string; coverVersion?: number }>()
const emit = defineEmits<{ close: []; favourite: [on: boolean]; 'cover-changed': []; relabeled: []; changed: [] }>()

interface Group { label: string; kind: 'original' | 'translation' | 'mod'; versions: string[]; authors: string[]; files: CatalogueFile[] }

const groups = computed<Group[]>(() => {
  const by = new Map<string, Group>()
  for (const f of props.game.files) {
    let g = by.get(f.variant)
    if (!g) {
      const kind = !f.variants.length ? 'original' : f.variants.some(v => v.kind === 'mod') ? 'mod' : 'translation'
      g = { label: f.variant === 'original' ? 'Original' : f.variant, kind, versions: [], authors: [], files: [] }
      by.set(f.variant, g)
    }
    g.files.push(f)
    for (const v of f.variants) {
      if (v.version && !g.versions.includes(v.version)) g.versions.push(v.version)
      if (v.author && !g.authors.includes(v.author)) g.authors.push(v.author)
    }
  }
  const rank = { original: 0, translation: 1, mod: 2 }
  return [...by.values()].sort((a, b) => rank[a.kind] - rank[b.kind] || a.label.localeCompare(b.label))
})

// The translation workbench's header card, fed from the catalogue: header IDs as the
// product line, regions from the header. Title is the catalogue's (filename-derived).
const meta = computed<GameMeta>(() => ({
  title: props.game.title, titleHex: '', region: props.game.regions,
  product: props.game.ids.join(' · '), version: '', date: props.game.meta?.year ?? '',
  maker: [props.game.meta?.developer, props.game.meta?.publisher].filter((v, i, a) => v && a.indexOf(v) === i).join(' / '),
}))

const coverFailed = ref(false)
const coverLoaded = ref(false)
watch(() => props.game.key, () => { coverFailed.value = false; coverLoaded.value = false })
// The drawer stays mounted while you step from game to game: start each one at its top, or it
// opens scrolled (header and close button out of view) wherever the last game was left.
const drawerEl = ref<HTMLElement | null>(null)
watch(() => props.game.key, () => { if (drawerEl.value) drawerEl.value.scrollTop = 0 })
const coverSrc = computed(() => props.game.cover === 'miss' || coverFailed.value ? '' : catalogueApi.coverUrl(props.system, props.game.key, props.coverVersion))

// Your own cover (homebrew, hacks, anything libretro lacks): click the cover to upload.
// Stored in the catalogue and preferred over libretro art from then on.
const fileEl = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const uploadError = ref('')
// No cover yet: paste an image link and the API downloads it (same store as an upload).
const coverLink = ref('')
async function saveCoverLink() {
  const url = coverLink.value.trim()
  if (!url) return
  uploading.value = true
  uploadError.value = ''
  try {
    await catalogueApi.coverFromUrl(props.system, props.game.key, url)
    coverLink.value = ''
    coverFailed.value = false
    coverLoaded.value = false
    emit('cover-changed')
  } catch (err) {
    uploadError.value = (err as Error).message
  } finally {
    uploading.value = false
  }
}
watch(() => props.game.key, () => { coverLink.value = '' })

async function onPick(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  uploading.value = true
  uploadError.value = ''
  try {
    await catalogueApi.uploadCover(props.system, props.game.key, file)
    coverFailed.value = false
    coverLoaded.value = false
    emit('cover-changed')
  } catch (err) {
    uploadError.value = (err as Error).message
  } finally {
    uploading.value = false
    if (fileEl.value) fileEl.value.value = ''
  }
}

// ── Cross-tab links ──
const router = useRouter()

// A node row opens that node's drawer in Network (the node is the entry point there).
function openNode(id: string) {
  if (props.nodes[id]) router.push({ path: '/', query: { node: id } })
}

// A translation variant links to its Translation-tab project. Match on the
// disc's header ID + language (both stored by the project), then title + language.
const projects = ref<ProjectSummary[]>([])
onMounted(() => {
  translationApi.listProjects().then(r => { projects.value = (r.projects ?? []) as ProjectSummary[] }).catch(() => { /* no link then */ })
})
function projectFor(g: Group): ProjectSummary | null {
  if (g.kind !== 'translation') return null
  // lang = the ISO code the catalogue folded [T-Cat]/[T-Eng] into (config/languages.json)
  const lang = g.files[0]?.variants.find(v => v.kind === 'translation')?.lang ?? ''
  const sameLang = (p: ProjectSummary) => !!p.lang && p.lang.toLowerCase() === lang
  const pool = projects.value.filter(p => p.system === props.system && sameLang(p))
  return pool.find(p => p.meta?.product && props.game.ids.includes(p.meta.product))
    ?? pool.find(p => names.key(names.title(p.gameName)) === names.key(props.game.title))
    ?? null
}
function openProject(p: ProjectSummary) { router.push('/translation/' + encodeURIComponent(p.ns)) }

const KIND_LABEL = { original: 'Original', translation: 'Translation', mod: 'Mod' }

function nodeName(id: string) { return props.nodes[id]?.name ?? id }
function fileName(path: string) { return path.split('/').pop() ?? path }
function day(ts: string) { return ts ? ts.slice(0, 10) : '' }
function version(f: CatalogueFile) { return f.variants.map(v => v.version).filter(Boolean).join(' + ') }

// Label: Pluto's own name for the game (global, not per node); its art is matched on it.
const labelEditing = ref(false)
const labelText = ref('')
const labelBusy = ref(false)
const labelError = ref('')
watch(() => props.game.key, () => { labelEditing.value = false })
function editLabel() { labelEditing.value = !labelEditing.value; labelText.value = props.game.label || props.game.title; labelError.value = '' }
async function saveLabel() {
  const text = labelText.value.trim() === (props.game.fileTitle ?? props.game.title) ? '' : labelText.value.trim()
  if (text === (props.game.label || '')) { labelEditing.value = false; return }
  labelBusy.value = true
  try {
    await catalogueApi.setLabel(props.system, props.game.key, text)
    labelEditing.value = false
    emit('relabeled')
  } catch (e) {
    labelError.value = (e as Error).message
  } finally {
    labelBusy.value = false
  }
}
const focusEl = (el: unknown) => { if (el instanceof HTMLInputElement) el.focus() }

const { playTitle, play, quit, openFolder, actionError, sendTargets, send, sendCommand, sending } =
  useRomActions(toRef(props, 'system'), toRef(props, 'nodes'))
watch(() => props.game.key, () => { sendCommand.value = '' })

// Which copy's card the last action came from: its error shows on that card.
const active = ref<string | null>(null)
const key = (f: CatalogueFile) => f.node + '|' + f.path
function act(f: CatalogueFile, run: () => unknown) { active.value = key(f); actionError.value = ''; run() }
watch(() => props.game.key, () => { active.value = null })

// Delete: a Lab copy goes to the Trash, a copy on another node is removed for good (the confirm
// says so). The API refuses what a node can't do, and its message shows on the card.
async function deleteCopy(f: CatalogueFile) {
  const where = nodeName(f.node)
  const ask = f.node === 'lab'
    ? `Move "${fileName(f.path)}" to the Trash?`
    : `Delete "${fileName(f.path)}" from ${where}? There is no Trash there: it's gone for good.`
  if (!window.confirm(ask)) return
  actionError.value = ''
  try {
    await catalogueApi.deleteCopy(props.system, props.game.key, f.node, f.path)
    emit('changed')
  } catch (e) {
    actionError.value = (e as Error).message
  }
}

// A copy marked Deleted (gone from its node's disk) can be removed from the catalogue.
async function forget(f: CatalogueFile) {
  actionError.value = ''
  try {
    await catalogueApi.forget(props.system, props.game.key, f.node, f.path)
    emit('changed')
  } catch (e) {
    actionError.value = (e as Error).message
  }
}
</script>

<template>
  <aside ref="drawerEl" class="gd" @click.stop>
    <header class="gd__head">
      <button class="gd__cover" :class="{ 'gd__cover--art': coverSrc }" :title="game.cover === 'custom' ? 'Replace cover' : 'Upload cover'" :disabled="uploading" @click="fileEl?.click()">
        <template v-if="coverSrc">
          <img :src="coverSrc" alt="" :class="{ 'is-loading': !coverLoaded }" @load="coverLoaded = true" @error="coverFailed = true" />
          <UiSpinner v-if="!coverLoaded" class="gd__cover-spin" :size="20" />
        </template>
        <img v-else-if="systemIcon" :src="systemIcon" class="gd__cover-ic" alt="" />
        <template v-else>{{ game.title.slice(0, 1) }}</template>
        <span class="gd__cover-edit">{{ uploading ? 'Uploading…' : game.cover === 'custom' ? 'Replace' : 'Upload' }}</span>
        <input ref="fileEl" type="file" accept="image/png,image/jpeg,image/webp" hidden @change="onPick" />
      </button>
      <div class="gd__titles">
        <MetadataCard :meta="meta" wrap empty-text="" />
        <span v-if="game.meta?.genre" class="gd__genre">{{ game.meta.genre }}</span>
      </div>

      <div class="gd__tools">
        <UiIconButton variant="ghost" :active="!!game.label" :title="game.label ? 'Edit label' : 'Set label'" @click="editLabel">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M3 12.5V4a1 1 0 0 1 1-1h8.5l8.5 8.5-9.5 9.5z"/><circle cx="7.5" cy="7.5" r="1.3" fill="currentColor"/></svg>
        </UiIconButton>
        <UiIconButton variant="ghost" :active="game.favourite" :title="game.favourite ? 'Unfavourite' : 'Favourite'"
                      @click="emit('favourite', !game.favourite)">
          <svg width="16" height="16" viewBox="0 0 24 24" :fill="game.favourite ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M12 3.5l2.6 5.3 5.9.9-4.2 4.1 1 5.8L12 16.9l-5.3 2.7 1-5.8L3.5 9.7l5.9-.9z"/></svg>
        </UiIconButton>
        <UiClose title="Close (Esc)" @click="emit('close')" />
      </div>
    </header>

    <form v-if="labelEditing" class="gd__label-edit" @submit.prevent="saveLabel">
      <input :ref="focusEl" v-model="labelText" class="gd__label-input" :disabled="labelBusy"
             placeholder="Title (Region)" @keydown.esc.stop="labelEditing = false" />
      <UiSpinner v-if="labelBusy" :size="14" />
    </form>
    <p v-if="labelEditing" class="gd__label-hint">Enter saves · Esc cancels · empty resets to the file name</p>
    <p v-if="labelError" class="gd__upload-err">{{ labelError }}</p>
    <p v-if="game.label && !labelEditing" class="gd__label-hint">Label · files read as {{ game.fileTitle }}</p>
    <form v-if="!coverSrc" class="gd__label-edit" @submit.prevent="saveCoverLink">
      <input v-model="coverLink" class="gd__label-input" type="url" :disabled="uploading" placeholder="No cover: paste an image link, Enter" />
      <UiSpinner v-if="uploading" :size="14" />
    </form>
    <p v-if="uploadError" class="gd__upload-err">{{ uploadError }}</p>
    <p v-if="actionError && !active" class="gd__upload-err">{{ actionError }}</p>
    <AdminCommand v-if="sendCommand" title="Send to the PS2 drive from Terminal" :commands="[sendCommand]" @close="sendCommand = ''" />

    <section v-for="g in groups" :key="g.label" class="gd__sec">
      <div class="gd__group-head">
        <UiPill :tone="g.kind === 'original' ? 'idle' : 'accent'">{{ KIND_LABEL[g.kind] }}</UiPill>
        <span v-if="g.kind !== 'original'" class="gd__group-name">{{ g.label }}</span>
        <span v-if="g.authors.length" class="gd__group-meta">by {{ g.authors.join(', ') }}</span>
        <button v-if="projectFor(g)" class="gd__project" :title="'Open the ' + projectFor(g)!.ns + ' project'" @click="openProject(projectFor(g)!)">
          Open in Translation &rarr;
        </button>
      </div>

      <RomCard
        v-for="f in g.files" :key="f.node + f.path"
        :deleted="f.status === 'deleted'" play quit open remove
        :send-targets="sendTargets.filter(x => x.id !== f.node)" :send-busy="active === key(f) ? sending : null"
        :play-title="playTitle(f)" :quit-title="'Quit the running game on ' + nodeName(f.node)"
        :open-title="f.node === 'lab' ? 'Open folder' : 'Open folder (SMB)'"
        :remove-title="f.node === 'lab' ? 'Delete: move to the Trash' : 'Delete from ' + nodeName(f.node)"
        :error="active === key(f) ? actionError : null"
        @play="act(f, () => play(f))" @quit="act(f, () => quit(f))" @open="act(f, () => openFolder(f))"
        @send="id => act(f, () => send(f, id))" @remove="act(f, () => deleteCopy(f))" @forget="act(f, () => forget(f))"
      >
        <div class="gd__copy-head">
          <button class="gd__node-link" :title="'Open ' + nodeName(f.node) + ' in Network'" @click="openNode(f.node)">
            <img v-if="ICONS[f.node]" :src="ICONS[f.node]" class="gd__node-ic" alt="" />
            <span class="gd__node">{{ nodeName(f.node) }}</span>
          </button>
          <span v-if="f.card" class="gd__card" title="SD card this copy is on">{{ f.card }}</span>
          <span v-if="f.version" class="gd__ver" title="Release version">v{{ f.version }}</span>
          <span v-if="version(f)" class="gd__ver" :title="g.kind === 'original' ? '' : KIND_LABEL[g.kind] + ' version'">{{ g.kind === 'original' ? '' : KIND_LABEL[g.kind].toLowerCase() + ' ' }}v{{ version(f) }}</span>
          <span v-if="f.save.length" class="gd__save" :title="'Save on ' + f.save.map(nodeName).join(', ')">Save</span>
          <UiPill v-if="f.status === 'deleted'" tone="bad" class="gd__right" :title="'Last seen ' + day(f.lastSeen)">Deleted</UiPill>
        </div>
        <p class="gd__path" :class="{ 'is-gone': f.status === 'deleted' }" :title="f.path">{{ fileName(f.path) }}</p>
        <p class="gd__meta">
          <span v-for="r in f.regions" :key="r" class="gd__region">{{ r }}</span>
          <span v-if="f.id">{{ f.id }}</span>
          <span v-if="f.status === 'deleted'">last seen {{ day(f.lastSeen) }}</span>
        </p>
      </RomCard>
    </section>

    <section v-if="game.physical.length" class="gd__sec">
      <div class="gd__group-head"><UiPill tone="ok">Physical</UiPill></div>
      <div v-for="(p, i) in game.physical" :key="i" class="gd__file">
        <div class="gd__file-main">
          <span class="gd__node">{{ p.format || 'Physical copy' }}</span>
          <span v-if="p.id" class="gd__ver">{{ p.id }}</span>
          <UiPill v-if="p.status">{{ p.status }}</UiPill>
        </div>
        <p class="gd__path">{{ p.title }}</p>
        <p v-if="p.notes" class="gd__notes">{{ p.notes }}</p>
      </div>
    </section>

    <p v-if="game.saves.length" class="gd__foot">Saves on {{ game.saves.map(nodeName).join(', ') }}</p>
  </aside>
</template>

<style scoped>
.gd {
  position: absolute; top: 0; right: 0; bottom: 0;
  width: min(400px, 100%);
  z-index: 4;
  overflow-y: auto;
  background: var(--surface);
  border-left: 1px solid var(--line);
  box-shadow: -8px 0 28px rgba(26, 34, 51, 0.07);
  padding: 18px 18px 22px;
  font-family: var(--font-sans);
}
.gd__head { display: flex; gap: 12px; align-items: flex-start; }
/* Cover: libretro box art, lettered placeholder when none matched. */
.gd__cover img { width: 100%; height: 100%; object-fit: contain; }
.gd__cover { border: 0; padding: 0; font: inherit; cursor: pointer; }
.gd__cover-edit {
  position: absolute; left: 0; right: 0; bottom: 0; padding: 3px 0;
  font-size: 11px; font-weight: 600; color: #fff; background: rgba(26, 34, 51, 0.62);
  opacity: 0; transition: opacity 0.12s;
}
.gd__cover:hover .gd__cover-edit, .gd__cover:disabled .gd__cover-edit { opacity: 1; }
.gd__upload-err { margin: 8px 0 0; font-size: 12px; color: var(--bad); }
.gd__cover img.is-loading { visibility: hidden; position: absolute; }
.gd__cover-spin { position: absolute; top: 50%; left: 50%; margin: -10px 0 0 -10px; }
/* no art: the system icon at the system tile's size */
.gd__cover img.gd__cover-ic { width: 88px; height: 88px; }
.gd__cover {
  position: relative;
  flex: 0 0 auto; width: 96px; height: 128px; border-radius: var(--r); overflow: hidden;
  display: flex; align-items: center; justify-content: center;
  background: var(--surface-3); color: var(--text-faint); font-size: 26px; font-weight: 600;
}
.gd__head:has(.gd__cover--art) { flex-wrap: wrap; }
/* real art: its own full-width row under the title, never upscaled past its resolution */
.gd__cover.gd__cover--art { order: 1; flex: 0 0 100%; width: 100%; height: auto; min-height: 128px; background: transparent; }
.gd__cover--art img:not(.is-loading) { width: auto; height: auto; max-width: 100%; }
.gd__titles { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }
.gd__genre { font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 999px; background: var(--accent-soft); color: var(--accent-hover); }
/* same badge as MetadataCard's region */
.gd__region { font-family: var(--font-sans); font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-muted); background: var(--surface-2); border: 1px solid var(--line); border-radius: var(--r-sm); padding: 1px 6px; }
.gd__tools { display: flex; gap: 2px; flex: 0 0 auto; }

.gd__sec { margin-top: 18px; }
.gd__group-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.gd__group-name { font-size: 13px; font-weight: 600; color: var(--text); }
.gd__group-meta { font-size: 12px; color: var(--text-faint); }

.gd__file { padding: 8px 10px; margin-bottom: 6px; border: 1px solid var(--line); border-radius: 10px; }
.gd__file.is-deleted { border-style: dashed; }
.gd__file.is-deleted .gd__path { text-decoration: line-through; color: var(--text-faint); }
.gd__file-main { display: flex; align-items: center; gap: 8px; min-height: 26px; }
.gd__card { font-family: var(--font-mono); font-size: 10.5px; font-weight: 600; padding: 1px 6px; border-radius: 4px; background: var(--surface-3); color: var(--text-muted); }
.gd__node-link { display: inline-flex; align-items: center; gap: 8px; padding: 0; border: 0; background: none; font: inherit; color: inherit; cursor: pointer; }
.gd__node-link:hover .gd__node { color: var(--accent); text-decoration: underline; }
.gd__project { margin-left: auto; padding: 0; border: 0; background: none; font: inherit; font-size: 12px; font-weight: 600; color: var(--accent); cursor: pointer; }
.gd__project:hover { color: var(--accent-hover); text-decoration: underline; }
.gd__node-ic { width: 18px; height: 18px; object-fit: contain; }
.gd__node { font-size: 13px; font-weight: 600; color: var(--text); }
.gd__ver { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); }
.gd__save { font-size: 11px; font-weight: 600; color: var(--ok); }
.gd__path.is-gone { text-decoration: line-through; color: var(--text-faint); }
.gd__copy-head { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 8px; min-height: 22px; }
.gd__right { margin-left: auto; }

.gd__label-edit { display: flex; align-items: center; gap: 6px; margin-top: 12px; }
.gd__label-hint { margin: 6px 0 0; font-size: 11.5px; color: var(--text-faint); }
.gd__label-input { flex: 1; min-width: 0; font: inherit; font-size: 12.5px; padding: 5px 8px; color: var(--text); background: var(--surface); border: 1px solid var(--line-strong); border-radius: var(--r-sm); }
.gd__label-input:focus { outline: none; border-color: var(--accent); }
.gd__path { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); margin: 4px 0 0; word-break: break-all; }
.gd__meta { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; margin: 4px 0 0; font-family: var(--font-mono); font-size: 11px; color: var(--text-faint); }
.gd__meta:empty { display: none; }
.gd__notes { font-size: 12px; color: var(--text-muted); margin: 4px 0 0; }
.gd__foot { margin-top: 16px; font-size: 12px; color: var(--text-faint); }
/* phone: the drawer IS the screen (fixed over the app chrome), its own close stays on top */
@media (max-width: 640px) {
  .gd { position: fixed; inset: 0; width: 100%; z-index: 50; border-left: 0; box-shadow: none; }
  /* full-width art would push the files below the fold: cap it, keep its proportions */
  .gd__cover--art img:not(.is-loading) { max-height: 40vh; }
}
</style>
