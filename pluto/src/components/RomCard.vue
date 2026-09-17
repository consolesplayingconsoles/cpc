<script setup lang="ts">
// One ROM copy as a card: the caller's body (who/where/what, default slot) over an action bar.
// Extracted from the Media drawer's copy card when the Homebrew tab's dev build became its
// second user. Every action is opt-in by flag and only emits: the caller runs it, and when a
// node can't do something the API's message comes back as `error`, shown under the bar.
// Build, Stop and Delete are hidden unless asked for (Media never builds; Homebrew never deletes).
//   <RomCard play open :send-targets="t" @play="…" @open="…" @send="id => …">…body…</RomCard>
import SendButtons from './SendButtons.vue'
import UiButton from './ui/UiButton.vue'
import UiSpinner from './ui/UiSpinner.vue'
import UiIconButton from './ui/UiIconButton.vue'

withDefaults(defineProps<{
  deleted?: boolean        // a copy gone from its node: the only action left is forget
  build?: boolean
  play?: boolean
  quit?: boolean
  open?: boolean
  remove?: boolean
  stop?: boolean           // show Stop (while something runs)
  sendTargets?: { id: string; name: string }[]
  sendBusy?: string | null
  busy?: boolean           // something runs: disable the actions that would start another
  building?: boolean       // the build itself runs: Build shows its spinner
  buildTitle?: string
  playTitle?: string
  quitTitle?: string
  openTitle?: string
  removeTitle?: string
  error?: string | null
}>(), {
  sendTargets: () => [], sendBusy: null, buildTitle: 'Build', playTitle: 'Play', quitTitle: 'Quit the running game',
  openTitle: 'Open folder', removeTitle: 'Delete', error: null,
})
defineEmits<{ build: []; play: []; quit: []; open: []; send: [node: string]; remove: []; stop: []; forget: [] }>()
</script>

<template>
  <div class="rom-card" :class="{ 'is-deleted': deleted }">
    <div class="rom-card__body"><slot /></div>
    <div class="rom-card__actions">
      <template v-if="!deleted">
        <UiIconButton v-if="build" variant="ghost" :disabled="busy" :title="building ? 'Building…' : buildTitle" @click="$emit('build')">
          <UiSpinner v-if="building" :size="14" />
          <svg v-else width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 3.5l6 6-2.5 2.5-6-6z"/><path d="M13.2 7.8L4 17a1.9 1.9 0 0 0 2.7 2.7l9.2-9.2"/></svg>
        </UiIconButton>
        <UiIconButton v-if="play" variant="ghost" :title="playTitle" @click="$emit('play')">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13a.8.8 0 0 0 1.2.7l10.4-6.5a.8.8 0 0 0 0-1.4L9.2 4.8A.8.8 0 0 0 8 5.5z"/></svg>
        </UiIconButton>
        <UiIconButton v-if="quit" variant="ghost" :title="quitTitle" @click="$emit('quit')">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>
        </UiIconButton>
        <UiIconButton v-if="open" variant="ghost" :title="openTitle" @click="$emit('open')">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
        </UiIconButton>
        <SendButtons :targets="sendTargets" :disabled="busy" :busy="sendBusy" @send="id => $emit('send', id)" />
        <UiButton v-if="stop" variant="secondary" @click="$emit('stop')">Stop</UiButton>
        <UiIconButton v-if="remove" variant="ghost" class="rom-card__right" :title="removeTitle" @click="$emit('remove')">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>
        </UiIconButton>
      </template>
      <UiIconButton v-else variant="ghost" class="rom-card__right" title="Remove from the catalogue" @click="$emit('forget')">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/></svg>
      </UiIconButton>
    </div>
    <p v-if="error" class="rom-card__err">{{ error }}</p>
  </div>
</template>

<style scoped>
.rom-card { margin-bottom: 8px; border: 1px solid var(--line); border-radius: var(--r-lg); background: var(--surface); overflow: hidden; }
.rom-card.is-deleted { border-style: dashed; }
.rom-card__body { padding: 10px 12px 8px; }
.rom-card__actions { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; padding: 4px 6px; border-top: 1px solid var(--line); background: var(--surface-2); }
.rom-card__right { margin-left: auto; }
.rom-card__err { margin: 0; padding: 6px 12px; font-size: 12px; color: var(--bad); border-top: 1px solid var(--line); background: var(--surface); }
</style>
