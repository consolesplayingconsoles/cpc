<script setup lang="ts">
// Canonical dropdown. Mirrors Control.vue's select (the established pattern) but on
// WHITE, not grey — a grey field reads as disabled; white reads as active/ready.
// v-model-able: <UiSelect v-model="x"><option …/></UiSelect>
defineProps<{ modelValue: string; disabled?: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()
</script>

<template>
  <select
    class="ui-select"
    :value="modelValue"
    :disabled="disabled"
    @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
  >
    <slot />
  </select>
</template>

<style scoped>
.ui-select {
  width: 100%;                     /* fill the container; the parent sets the width */
  font-family: var(--font-sans, inherit);
  font-size: 13px;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  padding: 6px 32px 6px 10px;
  cursor: pointer;
  /* the browser's own arrow sits against the edge: replaced by a chevron 12px in (both themes) */
  appearance: none; -webkit-appearance: none;
  background-repeat: no-repeat; background-position: right 12px center; background-size: 12px 12px;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'%3E%3Cpath d='M2.5 4.5L6 8l3.5-3.5' fill='none' stroke='%23565d6e' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
}
:global(:root[data-theme="dark"]) .ui-select {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'%3E%3Cpath d='M2.5 4.5L6 8l3.5-3.5' fill='none' stroke='%23bcc3d0' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
}
.ui-select:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.ui-select:disabled {
  color: var(--text-faint);
  background: var(--surface-2);   /* grey == disabled, by design */
  cursor: not-allowed;
}
</style>
