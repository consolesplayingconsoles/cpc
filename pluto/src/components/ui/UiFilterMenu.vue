<script setup lang="ts">
// A "Filter · n ▾" button that opens a menu of checkboxes. Extracted from the Media tab, which
// had it inline twice, when the Homebrew list became its second user. It owns only the open
// state and the outside-click close: what the checkboxes ARE, and what ticking them does,
// belongs to the caller, who puts <label><input type="checkbox" /> ...</label> rows in the
// slot (a <span class="ui-fmenu__sep"> between groups is a heading).
//   <UiFilterMenu :count="activeFilters"> <label>...</label> </UiFilterMenu>
import { onMounted, onUnmounted, ref } from 'vue'
import UiButton from './UiButton.vue'

defineProps<{
  count?: number            // ticked filters, shown beside the label
  align?: 'left' | 'right'  // which edge of the button the menu hangs from (right by default)
}>()

const open = ref(false)
const root = ref<HTMLElement | null>(null)
function away(e: MouseEvent) {
  if (open.value && !root.value?.contains(e.target as Node)) open.value = false
}
onMounted(() => document.addEventListener('click', away))
onUnmounted(() => document.removeEventListener('click', away))
</script>

<template>
  <span ref="root" class="ui-fmenu">
    <UiButton @click.stop="open = !open">
      Filter<template v-if="count"> · {{ count }}</template> ▾
    </UiButton>
    <div v-if="open" class="ui-fmenu__menu" :class="{ 'is-left': align === 'left' }" role="menu">
      <slot />
    </div>
  </span>
</template>

<style scoped>
.ui-fmenu { position: relative; }
.ui-fmenu__menu {
  position: absolute; top: calc(100% + 4px); right: 0; z-index: 6;
  display: flex; flex-direction: column; gap: 2px; min-width: 180px; max-height: 70vh; overflow-y: auto; padding: 6px;
  background: var(--surface); border: 1px solid var(--line); border-radius: var(--r);
  box-shadow: var(--shadow-md, var(--shadow-sm));
}
.ui-fmenu__menu.is-left { right: auto; left: 0; }
.ui-fmenu__menu :slotted(label) { display: flex; align-items: center; gap: 8px; padding: 6px 8px; font-size: 13px; border-radius: var(--r-sm); cursor: pointer; white-space: nowrap; }
.ui-fmenu__menu :slotted(label:hover) { background: var(--surface-2); }
.ui-fmenu__menu :slotted(.ui-fmenu__sep) { margin: 4px 0 0; padding: 4px 6px 0; border-top: 1px solid var(--line); font-size: 11px; font-weight: 600; color: var(--text-faint); }
.ui-fmenu__menu :slotted(.ui-fmenu__sep:first-child) { margin-top: 0; padding-top: 0; border-top: 0; }   /* a leading heading needs no rule above it */
</style>
