<script setup lang="ts">
// "Needs admin" dialog: Pluto can't touch a root-only drive (the PS2 HDD), so it hands you the
// Terminal command that does. The command reports back to the catalogue when it finishes.
import UiButton from '../ui/UiButton.vue'
import UiCopyButton from '../ui/UiCopyButton.vue'
import UiModal from '../ui/UiModal.vue'

defineProps<{ title: string; commands: string[] }>()
defineEmits<{ close: [] }>()
</script>

<template>
  <UiModal :title="title" @close="$emit('close')">
    <p class="ac__note">This needs admin rights, so Pluto can't run it. Copy it into Terminal: the catalogue updates when it's done.</p>
    <div v-for="c in commands" :key="c" class="ac__line">
      <code>{{ c }}</code>
      <UiCopyButton :text="c" title="Copy command" />
    </div>
    <template #actions>
      <UiButton @click="$emit('close')">Close</UiButton>
    </template>
  </UiModal>
</template>

<style scoped>
.ac__note { margin: 0 0 var(--sp-3); font-size: 13px; color: var(--text-muted); }
.ac__line {
  display: flex; align-items: flex-start; gap: 6px;
  padding: 8px 10px; margin-top: var(--sp-2);
  background: var(--surface-2); border: 1px solid var(--line); border-radius: var(--r-sm);
}
.ac__line code { flex: 1; min-width: 0; font-family: var(--font-mono); font-size: 11.5px; word-break: break-all; color: var(--text); }
</style>
