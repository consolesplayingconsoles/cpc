<script setup lang="ts">
// Canonical button. secondary = the drawer's .nd__act (surface + quiet border,
// surface-2 on hover); primary = the terracotta accent. Pass variant; default
// secondary. <UiButton variant="primary" :disabled="…" @click="…">Create</UiButton>
defineProps<{ disabled?: boolean; variant?: 'primary' | 'secondary' }>()
</script>

<template>
  <button class="ui-btn" :class="`ui-btn--${variant || 'secondary'}`" :disabled="disabled">
    <slot />
  </button>
</template>

<style scoped>
.ui-btn {
  font-family: var(--font-sans, inherit);
  font-size: 13px;
  padding: 7px 14px;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: var(--surface);
  color: var(--text);
  cursor: pointer;
  transition: background 0.1s, border-color 0.1s, opacity 0.1s;
}
.ui-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.ui-btn--secondary:hover:not(:disabled) {
  background: var(--surface-2);
  border-color: var(--line-strong);
}
.ui-btn--primary {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-ink);
}
.ui-btn--primary:hover:not(:disabled) {
  background: var(--accent-hover);
  border-color: var(--accent-hover);
}
</style>
