<script setup lang="ts">
// The Homebrew detail header: what this item IS (cover or console icon, title, console and
// base game, release state, path) and what you can DO with it (build, play, send, open the
// build folder), with the last build's details beside the buttons.
//
// The actions used to sit in a card of their own BELOW the header, which read as a second
// subject on the page. They are the same RomCard as the Media drawer's copies -- passed
// `flat` so it draws no frame of its own inside this one -- so there is one definition of
// those buttons and the catalogue is untouched.
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import type { HomebrewItem } from '../../api/homebrew'
import RomCard from '../RomCard.vue'
import UiPill from '../ui/UiPill.vue'
import UiInfoTip from '../ui/UiInfoTip.vue'

const props = defineProps<{
  item: HomebrewItem
  icon?: string | null          // the console's avatar
  coverUrl?: string | null      // the base game's cover, when it is a catalogued game
  mediaLink?: string | null     // where that game lives in Media
  sendTargets: { id: string; name: string }[]
  sendBusy?: string | null
  busy?: boolean                // this console is already running something
  building?: boolean
  running?: boolean             // the item itself is running (Stop is offered)
  buildTitle?: string
  error?: string | null
}>()
defineEmits<{ build: []; play: []; openOutput: []; send: [node: string]; stop: []; openDir: [] }>()

function hideImg(e: Event) { (e.target as HTMLImageElement).style.display = 'none' }

// GitHub's own counts (each release's assets), as of the last fetch: cached by the API for
// ten minutes; the tab's Refresh asks again.
const downloads = computed(() => props.item.release?.downloads ?? null)
const checked = computed(() => downloads.value?.checked.replace('T', ' ').slice(0, 16) ?? '')
</script>

<template>
  <header class="hbh">
    <div class="hbh__top">
      <RouterLink v-if="mediaLink && coverUrl" :to="mediaLink" class="hbh__cover-link" :title="'Open ' + item.game?.title + ' in Media'">
        <img :src="coverUrl" class="hbh__cover" alt="" @error="hideImg" />
      </RouterLink>
      <img v-else-if="icon" :src="icon" class="hbh__ic" alt="" />

      <div class="hbh__body">
        <div class="hbh__line">
          <h2 class="hbh__title">{{ item.title }}</h2>
          <RouterLink v-if="item.game?.listed" :to="`/media/${item.game.system}`" class="hbh__link" :title="'Open ' + item.nodeName + ' in Media'">{{ item.nodeName }}</RouterLink>
          <span v-else>{{ item.nodeName }}</span>
          <template v-if="item.game">
            <span class="hbh__sep">/</span>
            <RouterLink v-if="mediaLink" :to="mediaLink" class="hbh__link">{{ item.game.title }}</RouterLink>
            <span v-else>{{ item.game.title }}</span>
          </template>
          <template v-else-if="item.group"><span class="hbh__sep">/</span> {{ item.group }}</template>
          <a
            v-if="item.release" class="hbh__release"
            :href="item.release.url" target="_blank" rel="noopener" :title="item.release.name"
          ><UiPill :tone="item.release.stable ? 'ok' : 'idle'">{{ item.release.stable ? 'Released' : 'Pre-release' }} v{{ item.release.version }} ↗</UiPill></a>
          <UiPill v-else-if="item.noRelease" tone="warn" :title="'Never released: ' + item.noRelease">Private: {{ item.noRelease }}</UiPill>
          <UiPill v-else tone="idle">Unreleased</UiPill>

          <!-- downloads are the release's, so they read beside it: the number, and the
               per-version split in the tip rather than strung across the card -->
          <span v-if="downloads" class="hbh__dl">
            <b>{{ downloads.total }}</b> downloads
            <UiInfoTip>
              <template v-if="item.release?.bundledWith.length">
                Released together with {{ item.release.bundledWith.join(', ') }}, so these count the whole release.<br />
              </template>
              <template v-for="v in downloads.versions" :key="v.url">
                <a :href="v.url" target="_blank" rel="noopener" :title="v.name">v{{ v.version }}</a>{{ v.prerelease ? ' (pre-release)' : '' }}: {{ v.count }}<br />
              </template>
              Counted by GitHub, as of {{ checked }}.
            </UiInfoTip>
          </span>
        </div>

        <!-- What you came here to do, so it gets its own row under the title at a size
           to match. RomCard draws the buttons (the same ones the Media drawer uses for
           a copy); `flat` keeps it frameless inside this header. -->
        <RomCard
          flat group="Build" build play open :stop="running"
          :send-targets="sendTargets" :send-busy="sendBusy ?? null"
          :busy="busy" :building="building"
          :build-title="buildTitle"
          play-title="Start the last build from its dev tree in the desktop emulator (no rebuild)"
          open-title="Open the project folder"
          :error="error ?? null"
          class="hbh__actions"
          @build="$emit('build')" @play="$emit('play')" @open="$emit('openOutput')"
          @send="id => $emit('send', id)" @stop="$emit('stop')"
        />

        <p v-if="item.description" class="hbh__desc">{{ item.description }}</p>

      </div>
    </div>
  </header>
</template>

<style scoped>
/* ONE block: a card like every other surface here (--surface, --line, --r-lg,
   --shadow-sm, as the params block below it). Everything about the item lives inside
   that single padding -- the actions on the title's own line, the build beside the
   path -- so the page has one subject, not a header followed by cards about it. */
.hbh {
  padding: var(--sp-4);
  background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--r-lg); box-shadow: var(--shadow-sm);
}
.hbh__top { display: flex; align-items: flex-start; gap: var(--sp-4); }
.hbh__cover-link { flex: none; line-height: 0; }
.hbh__cover { width: 148px; height: auto; max-height: 208px; object-fit: contain; border-radius: var(--r); box-shadow: var(--shadow); }
.hbh__ic { flex: none; width: 56px; height: 56px; object-fit: contain; }
.hbh__body { min-width: 0; flex: 1; }
.hbh__line { display: flex; align-items: center; gap: var(--sp-2); flex-wrap: wrap; font-size: 13px; color: var(--text-muted); }
.hbh__title { margin: 0; font-size: 20px; font-weight: 600; line-height: 1.2; }
.hbh__sep { color: var(--text-faint); }
.hbh__link { color: var(--text-muted); text-decoration: none; border-bottom: 1px dotted var(--line-strong); }
.hbh__link:hover { color: var(--accent); border-bottom-color: var(--accent); }
.hbh__release { text-decoration: none; }
/* the row you came for: bigger hit areas than the icon buttons wear elsewhere */
.hbh__actions { margin: var(--sp-3) 0 0; }
/* the two boxes sit side by side: stacked, their different widths read as a ragged edge */
.hbh__actions :deep(.rom-card__actions) { gap: var(--sp-2); }
.hbh__actions :deep(button) { min-width: 38px; min-height: 38px; }
.hbh__actions :deep(svg) { width: 19px; height: 19px; }
.hbh__actions :deep(.send-box) { padding: 4px 6px 4px 12px; }
.hbh__actions :deep(.send-label) { font-size: 13px; }
.hbh__actions :deep(.send-ic) { width: 22px; height: 22px; }
.hbh__desc { margin: var(--sp-2) 0 0; font-size: 13.5px; line-height: 1.55; color: var(--text-muted); }
/* the count is data, so the number is mono and the word around it stays quiet */
.hbh__dl { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; color: var(--text-faint); }
.hbh__dl b { font-family: var(--font-mono); font-size: 12.5px; font-weight: 600; color: var(--text-muted); }
</style>
