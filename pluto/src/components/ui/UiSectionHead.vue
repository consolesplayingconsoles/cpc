<script setup lang="ts">
// A list's section header, foldable: caret, optional icon, title, count, then whatever the
// caller puts in the default slot (a status dot, a button). Extracted from the Media tab's
// folding sections (md__section md__fold) when the Homebrew console list became its second
// user, so both read as one system. The caret carries the state by its angle, never colour.
//   <UiSectionHead :title="sec.name" :icon="ICONS[sec.node]" :count="n" :open="shown" @toggle="…" />
defineProps<{
  title: string
  icon?: string | null
  count?: number | null      // shown beside the title, like the Media sections
  open: boolean
  label?: string             // what the title IS, for the button's hint ("console", "system")
}>()
defineEmits<{ toggle: [] }>()
</script>

<template>
  <h3 class="ui-sect">
    <button
      class="ui-sect__btn" :aria-expanded="open"
      :title="(open ? 'Fold ' : 'Unfold ') + title"
      @click="$emit('toggle')"
    >
      <svg class="ui-sect__chev" :class="{ 'is-open': open }" width="12" height="12" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <img v-if="icon" :src="icon" class="ui-sect__ic" alt="" />
      <span class="ui-sect__title">{{ title }}</span>
      <span v-if="count != null" class="ui-sect__count">{{ count }}</span>
      <slot />
    </button>
  </h3>
</template>

<style scoped>
.ui-sect { margin: 0; font-size: 13px; font-weight: 600; color: var(--text); }
.ui-sect__btn {
  display: flex; align-items: center; gap: 8px; width: 100%;
  padding: var(--sp-3) var(--sp-4);
  font: inherit; color: inherit; text-align: left;
  background: none; border: 0; cursor: pointer;
}
.ui-sect__btn:hover { background: var(--surface-2); }
.ui-sect__chev { flex: none; color: var(--text-faint); transition: transform 0.12s; }
.ui-sect__chev.is-open { transform: rotate(90deg); }
.ui-sect__ic { flex: none; width: 22px; height: 22px; object-fit: contain; }
.ui-sect__title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ui-sect__count { font-family: var(--font-mono); font-size: 11px; font-weight: 400; color: var(--text-faint); }
</style>
