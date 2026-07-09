<script setup lang="ts">
import { useSlots } from 'vue'

const slots = useSlots()
const has = (n: string) => !!slots[n]

// Plain functions (not computeds): a slot appearing/disappearing at runtime -- e.g.
// Robutek's NE clip toggling on load -- isn't a tracked reactive dep, so the placement
// must be recomputed on every render. Called from the template, they always see the
// current slot set.
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
      <div v-if="has('sw')" class="quad" :style="cellStyle('sw')"><slot name="sw" /></div>
      <div v-if="has('se')" class="quad" :style="cellStyle('se')"><slot name="se" /></div>
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
