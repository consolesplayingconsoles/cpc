<script setup lang="ts">
import type { NodeMap } from '../../composables/useNodes'
import RobutekControl from './RobutekControl.vue'
import ClaudeControl from './ClaudeControl.vue'
import GoogleControl from './GoogleControl.vue'
import CaptureControl from './CaptureControl.vue'
import KinectControl from './KinectControl.vue'
import NokiaControl from './NokiaControl.vue'
import GamepadControl from './GamepadControl.vue'
import ControlLayout from './ControlLayout.vue'

defineProps<{
  active: boolean
  source: string
  target: string       // the drive SINK
  targetId?: string    // the selected target's id (a display target drives nothing)
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
    :active="active" :map-source="source" :target="target" :target-id="targetId" :mapping="mapping"
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
  <CaptureControl v-else-if="source === 'capture'" :key="source"
    :active="active" :map-source="source" :target="target" :target-id="targetId" :mapping="mapping"
    :target-dev="targetDev"
    @drive-error="$emit('drive-error', $event)" />
  <KinectControl v-else-if="source === 'kinect'" :key="source"
    :active="active" :nodes="nodes" :target="target" :mapping="mapping"
    :target-dev="targetDev"
    @drive-error="$emit('drive-error', $event)" />
  <NokiaControl v-else-if="source === 'nokia'" :key="source"
    :active="active" :nodes="nodes" :target="target" :mapping="mapping"
    :target-dev="targetDev" :roomba-ip="roombaIp"
    @drive-error="$emit('drive-error', $event)" />
  <GamepadControl v-else-if="source === 'gamepad'" :key="source"
    :sub="''" :active="active" :target="target" :mapping="mapping"
    :target-dev="targetDev" :roomba-ip="roombaIp"
    @drive-error="$emit('drive-error', $event)" />
</template>
