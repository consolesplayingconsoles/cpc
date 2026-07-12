<script setup lang="ts">
import UiPill from './UiPill.vue'
import UiStatusDot from './UiStatusDot.vue'

defineProps<{ state: 'ok' | 'bad'; title?: string }>()
</script>

<template>
  <UiPill :tone="state">
    <UiStatusDot :state="state" :title="title" />
    <span>{{ state === 'ok' ? 'Online' : 'Offline' }}</span>
  </UiPill>
</template>
