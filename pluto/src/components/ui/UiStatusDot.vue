<script setup lang="ts">
// Canonical online/offline (or ok/warn/bad) status dot. Sits ALONGSIDE a UiPill in one
// status area (not a separate one) -- e.g. reachability dot + activity pill together.
defineProps<{ state: 'ok' | 'warn' | 'bad' | 'off'; title?: string }>()
</script>

<template>
  <span class="uisd" :class="'is-' + state" :title="title" />
</template>

<style scoped>
.uisd { display: inline-block; width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.uisd.is-ok   { background: var(--ok); }
.uisd.is-warn { background: var(--warn); }
.uisd.is-bad  { background: var(--bad); }
.uisd.is-off  { background: var(--text-faint); }
</style>
