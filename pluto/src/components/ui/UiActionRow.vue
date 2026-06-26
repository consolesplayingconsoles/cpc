<script setup lang="ts">
// Canonical full-width "action row" — the drawer/command menu row that was
// reimplemented as nd__act and cmd--btn. Owns the row FRAME (surface card, quiet
// border, hover, padding); the contents (icon, label, trailing note/arrow) are the
// caller's slot, styled by their own content classes.
//   <UiActionRow :disabled @click><svg class="nd__ic"/><span>Deploy</span></UiActionRow>
defineProps<{ disabled?: boolean }>()
</script>

<template>
  <button class="ui-row" :disabled="disabled"><slot /></button>
</template>

<style scoped>
.ui-row {
  display: flex; align-items: center; gap: 10px; width: 100%;
  margin-bottom: 8px; padding: 9px 12px;
  font-size: 14px; color: var(--text); text-align: left;
  background: var(--surface); border: 1px solid var(--line); border-radius: 10px;
  cursor: pointer;
  transition: background 0.1s, border-color 0.1s;
}
.ui-row:hover:not(:disabled) { background: var(--surface-2); border-color: var(--line-strong); }
.ui-row:disabled { opacity: 0.5; cursor: default; }
</style>
