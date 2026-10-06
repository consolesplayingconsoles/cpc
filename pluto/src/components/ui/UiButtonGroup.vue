<script setup lang="ts">
// A labelled box of buttons: "Send to [wii][dc]", "Build [▶][📁]". The box says the buttons
// inside it are one job, which a bare row of icons does not. Extracted from SendButtons when
// the Homebrew header wanted its build actions grouped the same way, so there is one such
// box in the app rather than two that drift apart.
//   <UiButtonGroup label="Build"><UiIconButton …/></UiButtonGroup>
defineProps<{
  label?: string
  bare?: boolean          // no box: the buttons stand on their own (a caller with no label)
  disabled?: boolean      // greys the label; the buttons disable themselves
}>()
</script>

<template>
  <div class="ui-bgroup" :class="{ 'is-disabled': disabled, 'is-bare': bare }">
    <span v-if="label" class="ui-bgroup__label">{{ label }}</span>
    <slot />
  </div>
</template>

<style scoped>
.ui-bgroup {
  display: inline-flex; align-items: center; gap: 2px;
  padding: 2px 4px 2px 10px;
  border: 1px solid var(--line); border-radius: var(--r); background: var(--surface);
}
.ui-bgroup.is-bare { padding: 0; border: 0; background: none; }
.ui-bgroup__label { margin-right: 4px; font-size: 12px; font-weight: 600; color: var(--text-muted); white-space: nowrap; }
.ui-bgroup.is-disabled .ui-bgroup__label { color: var(--text-faint); }
</style>
