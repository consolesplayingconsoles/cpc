<script setup lang="ts">
// Canonical battery indicator: shell + fill bar + % text, coloured by level
// (--ok > 50 > --warn > 20 > --bad). Extracted from the Dreame vacuum's inline
// battery so the Roomba telemetry (and any future node) shows charge identically.
import { computed } from 'vue'

const props = defineProps<{ pct: number | null | undefined; charging?: boolean }>()

const color = computed(() => {
  const p = props.pct
  if (p === null || p === undefined) return 'var(--text-muted)'
  return p > 50 ? 'var(--ok)' : p > 20 ? 'var(--warn)' : 'var(--bad)'
})
</script>

<template>
  <span v-if="pct !== null && pct !== undefined" class="uib">
    <span class="uib-shell"><span class="uib-fill" :style="{ width: pct + '%', background: color }" /></span>
    <span class="uib-pct mono" :style="{ color }">{{ pct }}%<span v-if="charging" class="uib-chg" title="charging">&plus;</span></span>
  </span>
</template>

<style scoped>
.uib { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; }
.uib-shell { width: 34px; height: 8px; border-radius: 999px; background: var(--surface-3); overflow: hidden; }
.uib-fill { display: block; height: 100%; border-radius: 999px; transition: width 0.4s ease; }
.uib-pct { font-family: var(--font-mono); }
.uib-chg { color: var(--ok); font-weight: 700; margin-left: 1px; }
</style>
