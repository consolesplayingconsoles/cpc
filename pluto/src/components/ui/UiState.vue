<script setup lang="ts">
// A page's one-line status: loading, searching, nothing found, an error. Every list in Pluto
// says these the same way, so they come from here rather than each page's own <p>.
import UiSpinner from './UiSpinner.vue'

defineProps<{
  loading?: boolean                 // spinner in front: something is on its way
  tone?: 'muted' | 'bad'            // bad = an error, in the error colour
}>()
</script>

<template>
  <p class="ui-state" :class="{ 'is-bad': tone === 'bad' }" role="status">
    <UiSpinner v-if="loading" :size="14" />
    <slot />
  </p>
</template>

<style scoped>
.ui-state {
  display: flex; align-items: center; gap: 8px;
  margin: 0 0 var(--sp-4);
  font-size: 13px; color: var(--text-muted);
}
.ui-state.is-bad { color: var(--bad); }
</style>
