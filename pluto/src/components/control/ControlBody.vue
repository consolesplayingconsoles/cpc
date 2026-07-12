<script setup lang="ts">
import type { NodeMap } from '../../composables/useNodes'
import RobutekControl from './RobutekControl.vue'
import ClaudeControl from './ClaudeControl.vue'
import GoogleControl from './GoogleControl.vue'
import KinectControl from './KinectControl.vue'
import DreamPicoPortControl from './DreamPicoPortControl.vue'
import ControlLayout from './ControlLayout.vue'

defineProps<{
  active: boolean
  source: string
  target: string
  mapping: string
  targetDev: string
  roombaIp: string
  nodes?: NodeMap
  name?: string
  showOffline?: boolean
  sub?: string
}>()

defineEmits<{ 'drive-error': [string] }>()
</script>

<template>
  <RobutekControl v-if="source === 'dreame'" :key="source"
    :source="source" :target="target" :mapping="mapping" :target-dev="targetDev"
    :active="active" :nodes="nodes" :name="name || 'dreame'"
    @drive-error="$emit('drive-error', $event)" />
  <ControlLayout v-else-if="source === 'keyboard'" :key="source"
    :active="active" :map-source="source" :target="target" :mapping="mapping"
    :target-dev="targetDev" :roomba-ip="roombaIp"
    @drive-error="$emit('drive-error', $event)" />
  <ClaudeControl v-else-if="source === 'claude'" :key="source"
    :active="active" :nodes="nodes" :map-source="source" :target="target" :mapping="mapping"
    :target-dev="targetDev"
    @drive-error="$emit('drive-error', $event)" />
  <GoogleControl v-else-if="source === 'google'" :key="source"
    :active="active" :map-source="source" :target="target" :mapping="mapping"
    :target-dev="targetDev"
    @drive-error="$emit('drive-error', $event)" />
  <KinectControl v-else-if="source === 'kinect'" :key="source"
    :active="active" :nodes="nodes" :target="target" :mapping="mapping"
    :target-dev="targetDev"
    @drive-error="$emit('drive-error', $event)" />
  <DreamPicoPortControl v-else-if="source === 'dreampicoport'" :key="source"
    :sub="''" :active="active" :target="target" :mapping="mapping"
    :target-dev="targetDev" :roomba-ip="roombaIp"
    @drive-error="$emit('drive-error', $event)" />
</template>
