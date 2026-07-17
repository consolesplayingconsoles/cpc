<script setup lang="ts">
import { useSlots, computed, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import ControlKeyboard from './ControlKeyboard.vue'
import RoombaTelemetry from './RoombaTelemetry.vue'
import RoombaCamera from './RoombaCamera.vue'

type Cell = 'nw' | 'ne' | 'sw' | 'se'

interface Props {
  active: boolean
  mapSource: string
  target: string
  mapping: string
  targetDev: string
  roombaIp?: string
  // Which quad(s) hold a live video feed and get a fullscreen (take-over-the-stage)
  // button. Parents pass their video slot (kinect -> nw, claude/google -> ne); the
  // roomba camera (auto-rendered in NE) opts itself in below.
  maxCells?: Cell[]
}

const props = defineProps<Props>()

const shouldShowTelemetry = computed(() => props.target === 'roomba' && props.roombaIp)
defineEmits<{ 'drive-error': [msg: string] }>()

const slots = useSlots()
// NE gets the roomba camera when target is roomba AND the source hasn't claimed the slot
// (keyboard + DreamPicoPort both leave NE free). Mirrors the SW=telemetry hardcode.
const shouldShowCamera = computed(() =>
  props.target === 'roomba' && !!props.targetDev && !slots['ne'])

// Hold-to-listen: the controller's X (verb 'listen') emits here; we relay it to the camera panel
// so it plays the camera audio while held. Purely local -- never touches the Roomba.
const listening = ref(false)

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
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  mq?.removeEventListener('change', onMq)
  window.removeEventListener('keydown', onKey)
})

// ── fullscreen: one video quad takes over the whole 2x2 stage ──────────────
// The grid is ControlLayout's, so the take-over lives here (single owner) rather
// than in each video panel. Maximizing spans the picked cell across both columns
// and rows and hides its siblings (they stay MOUNTED via display:none so live
// streams / capture sessions aren't torn down).
const maxCell = ref<Cell | null>(null)
const maxCells = computed<Set<Cell>>(() => {
  const s = new Set<Cell>(props.maxCells ?? [])
  if (shouldShowCamera.value) s.add('ne')   // roomba camera opts itself in
  return s
})
// No fullscreen on the phone/narrow layout -- it's already a scrollable stack.
const canMax = (cell: Cell) => !isNarrow.value && maxCells.value.has(cell)
function toggleMax(cell: Cell) { maxCell.value = maxCell.value === cell ? null : cell }
function onKey(e: KeyboardEvent) { if (e.key === 'Escape' && maxCell.value) maxCell.value = null }
// Drop out of fullscreen if the maxed cell stops being maximizable, we go narrow,
// or the surface deactivates -- so we never strand a hidden-siblings layout.
watch([maxCells, isNarrow], () => {
  if (maxCell.value && (!maxCells.value.has(maxCell.value) || isNarrow.value)) maxCell.value = null
})
watch(() => props.active, (on) => { if (!on) maxCell.value = null })

const has = (n: string) => {
  if (n === 'se') return true  // SE is always hardcoded
  if (n === 'sw') return shouldShowTelemetry.value  // SW (telemetry) rendered if target is roomba
  if (n === 'ne') return !!slots['ne'] || shouldShowCamera.value  // NE: source slot or the camera
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
  if (maxCell.value) {
    return cell === maxCell.value
      ? { gridColumn: '1 / span 2', gridRow: '1 / span 2' }
      : { display: 'none' }
  }
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
      <div v-if="has('nw')" class="quad" :style="isNarrow ? undefined : cellStyle('nw')">
        <button v-if="canMax('nw')" class="quad-max" :class="{ on: maxCell === 'nw' }"
          @click="toggleMax('nw')"
          :title="maxCell === 'nw' ? 'Exit fullscreen (Esc)' : 'Fullscreen'"
          :aria-label="maxCell === 'nw' ? 'Exit fullscreen' : 'Fullscreen'">
          <svg v-if="maxCell === 'nw'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="4 14 10 14 10 20" /><polyline points="20 10 14 10 14 4" /><line x1="14" y1="10" x2="21" y2="3" /><line x1="3" y1="21" x2="10" y2="14" /></svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="15 3 21 3 21 9" /><polyline points="9 21 3 21 3 15" /><line x1="21" y1="3" x2="14" y2="10" /><line x1="3" y1="21" x2="10" y2="14" /></svg>
        </button>
        <slot name="nw" />
      </div>
      <div v-if="has('ne')" class="quad" :style="isNarrow ? undefined : cellStyle('ne')">
        <button v-if="canMax('ne')" class="quad-max" :class="{ on: maxCell === 'ne' }"
          @click="toggleMax('ne')"
          :title="maxCell === 'ne' ? 'Exit fullscreen (Esc)' : 'Fullscreen'"
          :aria-label="maxCell === 'ne' ? 'Exit fullscreen' : 'Fullscreen'">
          <svg v-if="maxCell === 'ne'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="4 14 10 14 10 20" /><polyline points="20 10 14 10 14 4" /><line x1="14" y1="10" x2="21" y2="3" /><line x1="3" y1="21" x2="10" y2="14" /></svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="15 3 21 3 21 9" /><polyline points="9 21 3 21 3 15" /><line x1="21" y1="3" x2="14" y2="10" /><line x1="3" y1="21" x2="10" y2="14" /></svg>
        </button>
        <slot name="ne"><RoombaCamera v-if="shouldShowCamera" :node="targetDev" :active="active" :listening="listening" /></slot>
      </div>
      <div v-if="shouldShowTelemetry" class="quad" :style="isNarrow ? undefined : cellStyle('sw')">
        <RoombaTelemetry :ip="roombaIp!" :active="active" />
      </div>
      <div class="quad quad--main" :style="isNarrow ? undefined : cellStyle('se')">
        <ControlKeyboard :active="active" :map-source="mapSource" :target="target" :mapping="mapping" :target-dev="targetDev" :narrow="isNarrow" @drive-error="$emit('drive-error', $event)" @listen="listening = $event" />
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
  position: relative;
  display: flex;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

/* Fullscreen toggle: a corner overlay on video quads. Subtle until hovered/focused,
   forced visible while that quad is maximized so restore is always reachable. */
.quad-max {
  position: absolute;
  /* Sit inside the panel's own padding so the button lands on the video content,
     not overhanging into the panel margin. Panels pad their screen by ~sp-3/sp-4. */
  top: var(--sp-4);
  right: var(--sp-4);
  z-index: 4;
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-sm);
  background: rgba(0, 0, 0, 0.45);
  color: #fff;
  cursor: pointer;
  opacity: 0.5;
  transition: opacity 0.12s, background 0.12s;
}
.quad:hover .quad-max,
.quad-max:focus-visible,
.quad-max.on {
  opacity: 1;
}
.quad-max:hover {
  background: rgba(0, 0, 0, 0.72);
}
.quad-max svg {
  width: 15px;
  height: 15px;
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
