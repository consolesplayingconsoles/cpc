<script setup lang="ts">
import type { Game, CatalogueFile } from '../../api/catalogue'
import type { NodeMap } from '../../composables/useNodes'
import { ICONS } from '../../composables/useIcons'
import UiClose from '../ui/UiClose.vue'
import UiIconButton from '../ui/UiIconButton.vue'
import UiPill from '../ui/UiPill.vue'
import UiSpinner from '../ui/UiSpinner.vue'
import MetadataCard, { type GameMeta } from '../MetadataCard.vue'
import { catalogueApi } from '../../api/catalogue'
import { useRomActions } from '../../composables/useRomActions'
import { computed, ref, toRef, watch } from 'vue'

// One game, everything we know about it: every copy (ROM files per node, grouped by
// variant) and every shelf copy. Regions, mods, translations and physical are ONE
// entry by design -- the grouping below is what makes that readable (where Batocera
// shows each file as its own game).
const props = defineProps<{ system: string; game: Game; nodes: NodeMap; systemIcon?: string; coverVersion?: number }>()
const emit = defineEmits<{ close: []; favourite: [on: boolean]; 'cover-changed': [] }>()

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
const coverSrc = computed(() => props.game.cover === 'miss' || coverFailed.value ? '' : catalogueApi.coverUrl(props.system, props.game.key, props.coverVersion))

// Your own cover (homebrew, hacks, anything libretro lacks): click the cover to upload.
// Stored in the catalogue and preferred over libretro art from then on.
const fileEl = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const uploadError = ref('')
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

const KIND_LABEL = { original: 'Original', translation: 'Translation', mod: 'Mod' }

function nodeName(id: string) { return props.nodes[id]?.name ?? id }
function fileName(path: string) { return path.split('/').pop() ?? path }
function day(ts: string) { return ts ? ts.slice(0, 10) : '' }
function version(f: CatalogueFile) { return f.variants.map(v => v.version).filter(Boolean).join(' + ') }

const { emulator, canPlay, canOpen, play, openFolder, actionError } =
  useRomActions(toRef(props, 'system'), toRef(props, 'nodes'))
</script>

<template>
  <aside class="gd" @click.stop>
    <header class="gd__head">
      <button class="gd__cover" :title="game.cover === 'custom' ? 'Replace cover' : 'Upload cover'" :disabled="uploading" @click="fileEl?.click()">
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
        <UiIconButton variant="ghost" :active="game.favourite" :title="game.favourite ? 'Unfavourite' : 'Favourite'"
                      @click="emit('favourite', !game.favourite)">
          <svg width="16" height="16" viewBox="0 0 24 24" :fill="game.favourite ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M12 3.5l2.6 5.3 5.9.9-4.2 4.1 1 5.8L12 16.9l-5.3 2.7 1-5.8L3.5 9.7l5.9-.9z"/></svg>
        </UiIconButton>
        <UiClose title="Close (Esc)" @click="emit('close')" />
      </div>
    </header>

    <p v-if="uploadError" class="gd__upload-err">{{ uploadError }}</p>
    <p v-if="actionError" class="gd__upload-err">{{ actionError }}</p>

    <section v-for="g in groups" :key="g.label" class="gd__sec">
      <div class="gd__group-head">
        <UiPill :tone="g.kind === 'original' ? 'idle' : 'accent'">{{ KIND_LABEL[g.kind] }}</UiPill>
        <span v-if="g.kind !== 'original'" class="gd__group-name">{{ g.label }}</span>
        <span v-if="g.authors.length" class="gd__group-meta">by {{ g.authors.join(', ') }}</span>
      </div>

      <div v-for="f in g.files" :key="f.node + f.path" class="gd__file" :class="{ 'is-deleted': f.status === 'deleted' }">
        <div class="gd__file-main">
          <img v-if="ICONS[f.node]" :src="ICONS[f.node]" class="gd__node-ic" alt="" />
          <span class="gd__node">{{ nodeName(f.node) }}</span>
          <UiPill v-if="f.status === 'deleted'" tone="bad" :title="'Last seen ' + day(f.lastSeen)">Deleted</UiPill>
          <span v-if="f.version" class="gd__ver" title="Release version">v{{ f.version }}</span>
          <span v-if="version(f)" class="gd__ver" :title="g.kind === 'original' ? '' : KIND_LABEL[g.kind] + ' version'">{{ g.kind === 'original' ? '' : KIND_LABEL[g.kind].toLowerCase() + ' ' }}v{{ version(f) }}</span>
          <span v-if="f.save.length" class="gd__save" :title="'Save on ' + f.save.map(nodeName).join(', ')">Save</span>
          <UiIconButton v-if="canPlay(f)" class="gd__open" :title="'Play in ' + emulator?.name" @click="play(f)">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13a.8.8 0 0 0 1.2.7l10.4-6.5a.8.8 0 0 0 0-1.4L9.2 4.8A.8.8 0 0 0 8 5.5z"/></svg>
          </UiIconButton>
          <UiIconButton v-if="canOpen(f)" :class="{ 'gd__open': !canPlay(f) }" :title="f.node === 'lab' ? 'Open folder' : 'Open folder (SMB)'" @click="openFolder(f)">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
          </UiIconButton>
        </div>
        <p class="gd__path" :title="f.path">{{ fileName(f.path) }}</p>
        <p class="gd__meta">
          <span v-for="r in f.regions" :key="r" class="gd__region">{{ r }}</span>
          <span v-if="f.id">{{ f.id }}</span>
          <span v-if="f.status === 'deleted'">last seen {{ day(f.lastSeen) }}</span>
        </p>
      </div>
    </section>

    <section v-if="game.physical.length" class="gd__sec">
      <div class="gd__group-head"><UiPill tone="ok">Physical</UiPill></div>
      <div v-for="(p, i) in game.physical" :key="i" class="gd__file">
        <div class="gd__file-main">
          <span class="gd__node">{{ p.format || 'Physical copy' }}</span>
          <span v-if="p.id" class="gd__ver">{{ p.id }}</span>
        </div>
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
.gd__node-ic { width: 18px; height: 18px; object-fit: contain; }
.gd__node { font-size: 13px; font-weight: 600; color: var(--text); }
.gd__ver { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); }
.gd__save { font-size: 11px; font-weight: 600; color: var(--ok); }
.gd__open { margin-left: auto; }
.gd__path { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); margin: 4px 0 0; word-break: break-all; }
.gd__meta { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; margin: 4px 0 0; font-family: var(--font-mono); font-size: 11px; color: var(--text-faint); }
.gd__meta:empty { display: none; }
.gd__notes { font-size: 12px; color: var(--text-muted); margin: 4px 0 0; }
.gd__foot { margin-top: 16px; font-size: 12px; color: var(--text-faint); }
</style>
