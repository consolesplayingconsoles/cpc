<script setup lang="ts">
// Capture source screen: the live capture panel and nothing else -- same panel
// Claude/Google embed, without the chat wrapper (cf. ClaudeControl.vue, which
// fills NW with the Guide Dog feed). Anything else on this stage is target-owned
// and mounted by ControlLayout (e.g. the Kindle output for the kindle target).
import ControlCapture from './ControlCapture.vue'
import ControlLayout from './ControlLayout.vue'

defineProps<{
  active:     boolean
  mapSource:  string
  target:     string
  targetId?:  string
  mapping:    string
  targetDev?: string
}>()
const emit = defineEmits<{ 'drive-error': [string] }>()
</script>

<template>
  <ControlLayout :active="active" :map-source="mapSource" :target="target" :target-id="targetId"
    :mapping="mapping" :target-dev="targetDev || ''" :max-cells="['ne']"
    @drive-error="emit('drive-error', $event)">
    <!-- NE: live feed + session controls -->
    <template #ne>
      <ControlCapture
        :active="active"
        :map-source="mapSource" :target="target" :mapping="mapping" :target-dev="targetDev"
        @drive-error="emit('drive-error', $event)" />
    </template>
  </ControlLayout>
</template>
