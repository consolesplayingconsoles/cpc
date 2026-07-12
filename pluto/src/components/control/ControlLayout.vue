<script setup lang="ts">
import { useSlots, computed } from 'vue'
import ControlKeyboard from './ControlKeyboard.vue'
import RoombaTelemetry from './RoombaTelemetry.vue'

interface Props {
  active: boolean
  mapSource: string
  target: string
  mapping: string
  targetDev: string
  roombaIp?: string
}

const props = defineProps<Props>()

const shouldShowTelemetry = computed(() => props.target === 'roomba' && props.roombaIp)
defineEmits<{ 'drive-error': [msg: string] }>()

const slots = useSlots()
const has = (n: string) => {
  if (n === 'se') return true  // SE is always hardcoded
  if (n === 'sw') return shouldShowTelemetry.value  // SW (telemetry) rendered if target is roomba
  return !!slots[n]
}

const leftUsed  = () => has('nw') || has('sw')
const rightUsed = () => has('ne') || has('se')

// grid-row: fill the column, spanning down when the sibling cell is empty.
function rows(sibling: string, top: boolean) {
  if (!has(sibling)) return '1 / span 2'      // only cell in the column -> full height
  return top ? '1' : '2'
}
// grid-column: hold your column, but claim the whole width if the other column is empty.
function cols(mine: boolean) {
  const other = mine ? rightUsed() : leftUsed()
  if (!other) return '1 / span 2'             // other column empty -> full width
  return mine ? '1' : '2'
}

function cellStyle(cell: 'nw' | 'ne' | 'sw' | 'se') {
  const mine = cell === 'nw' || cell === 'sw'
  const top  = cell === 'nw' || cell === 'ne'
  const sibling = cell === 'nw' ? 'sw' : cell === 'sw' ? 'nw' : cell === 'ne' ? 'se' : 'ne'
  return { gridColumn: cols(mine), gridRow: rows(sibling, top) }
}
</script>

<template>
  <div class="ql">
    <div v-if="has('header')" class="ql-header"><slot name="header" /></div>

    <div class="ql-grid">
      <div v-if="has('nw')" class="quad" :style="cellStyle('nw')"><slot name="nw" /></div>
      <div v-if="has('ne')" class="quad" :style="cellStyle('ne')"><slot name="ne" /></div>
      <div v-if="shouldShowTelemetry" class="quad" :style="cellStyle('sw')">
        <RoombaTelemetry :ip="roombaIp!" :active="active" />
      </div>
      <div class="quad" :style="cellStyle('se')">
        <ControlKeyboard :active="active" :map-source="mapSource" :target="target" :mapping="mapping" :target-dev="targetDev" @drive-error="$emit('drive-error', $event)" />
      </div>
    </div>

    <div v-if="has('footer')" class="ql-footer"><slot name="footer" /></div>
  </div>
</template>

<style scoped>
.ql {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.ql-header,
.ql-footer {
  flex: 0 0 auto;
}

.ql-grid {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 1px;
}

/* Each cell is a stretched grid item; its content fills it (height:100% resolves against
   the definite track). min-* lets the track shrink instead of overflowing. */
.quad {
  display: flex;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

.quad > * {
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
}
</style>
