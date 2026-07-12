<script setup lang="ts">
import { useSlots, computed, ref, onMounted, onBeforeUnmount } from 'vue'
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

// Phone / narrow: drop the 2x2 grid and STACK the quadrants in DOM order (nw, ne, sw, se) as a
// scrollable column. The controller (se) is last -> lands under your thumbs -> and gets a tall
// min-height so it becomes a full-width touch pad (phone-as-controller). matchMedia (not a CSS
// query) because the desktop cells carry inline grid-column/row that a stylesheet can't override.
const isNarrow = ref(false)
let mq: MediaQueryList | null = null
function onMq(e: MediaQueryListEvent | MediaQueryList) { isNarrow.value = e.matches }
onMounted(() => {
  mq = window.matchMedia('(max-width: 640px)')
  onMq(mq)
  mq.addEventListener('change', onMq)
})
onBeforeUnmount(() => { mq?.removeEventListener('change', onMq) })

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

    <div class="ql-grid" :class="{ stacked: isNarrow }">
      <div v-if="has('nw')" class="quad" :style="isNarrow ? undefined : cellStyle('nw')"><slot name="nw" /></div>
      <div v-if="has('ne')" class="quad" :style="isNarrow ? undefined : cellStyle('ne')"><slot name="ne" /></div>
      <div v-if="shouldShowTelemetry" class="quad" :style="isNarrow ? undefined : cellStyle('sw')">
        <RoombaTelemetry :ip="roombaIp!" :active="active" />
      </div>
      <div class="quad quad--main" :style="isNarrow ? undefined : cellStyle('se')">
        <ControlKeyboard :active="active" :map-source="mapSource" :target="target" :mapping="mapping" :target-dev="targetDev" :narrow="isNarrow" @drive-error="$emit('drive-error', $event)" />
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

/* Phone / narrow: stack the quadrants in a scrollable column instead of the 2x2 grid.
   Each panel gets a usable height; the controller (se) dominates as the touch surface. */
.ql-grid.stacked {
  display: flex;
  flex-direction: column;
  grid-template-columns: none;
  grid-template-rows: none;
  overflow-y: auto;
  gap: 8px;
}
.ql-grid.stacked .quad {
  flex: 0 0 auto;
  min-height: 38vh;
  overflow: hidden;
}
.ql-grid.stacked .quad--main {
  min-height: 62vh;      /* the controller: the full-width phone pad */
}
</style>
