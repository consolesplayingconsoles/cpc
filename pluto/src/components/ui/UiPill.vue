<script setup lang="ts">
// Canonical soft-badge pill: a status label pill, unifying RobutekControl's rb-pill
// (activity: clean/return/error/idle) and its separately-styled "Offline" dot+text into
// ONE consistent shape/tone vocabulary, also used by the Roomba telemetry.
defineProps<{ tone?: 'ok' | 'warn' | 'bad' | 'accent' | 'idle' }>()
</script>

<template>
  <span class="uip" :class="'is-' + (tone || 'idle')"><slot /></span>
</template>

<style scoped>
.uip {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 12px; font-weight: 600; padding: 3px 9px; border-radius: 999px;
  background: var(--surface-3); color: var(--text-muted);
}
.uip.is-ok     { background: var(--ok-soft, var(--surface-3)); color: var(--ok); }
.uip.is-warn   { background: var(--warn-soft, #fef3c7); color: var(--warn, #92580a); }
.uip.is-bad    { background: var(--bad-soft, #fee2e2); color: var(--bad); }
.uip.is-accent { background: var(--accent-soft); color: var(--accent-hover); }
.uip.is-idle   { background: var(--surface-3); color: var(--text-muted); }
</style>
