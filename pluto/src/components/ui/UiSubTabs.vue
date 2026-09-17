<script setup lang="ts">
// Canonical sub-tab bar: the underlined tabs under a page header, each with an optional
// mono count. Extracted from the Media tab (Games / Tools / Hardware) when the Homebrew
// tab (Mods / Games / Tools) became its second user. Anything page-specific that shares
// the bar (e.g. Media's active-filter pills) goes in the default slot, after the tabs.
//   <UiSubTabs v-model="kind" :tabs="[{ key: 'mods', label: 'Mods', count: 14 }]" />
defineProps<{ modelValue: string; tabs: { key: string; label: string; count?: number }[] }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()
</script>

<template>
  <nav class="ui-subtabs">
    <button
      v-for="t in tabs" :key="t.key"
      class="ui-subtab" :class="{ 'is-on': t.key === modelValue }"
      @click="emit('update:modelValue', t.key)"
    >{{ t.label }}<span v-if="t.count !== undefined">{{ t.count }}</span></button>
    <slot />
  </nav>
</template>

<style scoped>
.ui-subtabs { display: flex; align-items: center; gap: var(--sp-4); padding: 0 var(--sp-5); background: var(--surface); border-bottom: 1px solid var(--line); flex-shrink: 0; }
.ui-subtab { font: inherit; font-size: 13px; font-weight: 600; padding: 8px 2px; color: var(--text-muted); background: none; border: 0; border-bottom: 2px solid transparent; cursor: pointer; }
.ui-subtab span { font-family: var(--font-mono); font-size: 11px; font-weight: 400; color: var(--text-faint); margin-left: 4px; }
.ui-subtab:hover { color: var(--text); }
.ui-subtab.is-on { color: var(--text); border-bottom-color: var(--accent); }
@media (max-width: 640px) {
  .ui-subtabs { flex-wrap: wrap; padding-left: var(--sp-4); padding-right: var(--sp-4); }
}
</style>
