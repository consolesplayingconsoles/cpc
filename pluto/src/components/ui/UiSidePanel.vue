<script setup lang="ts">
// Canonical left side panel for list + detail pages: collapsible (a round toggle rides the
// panel's right edge and stays on-screen when collapsed) and resizable (drag the edge).
// Extracted from the Dreame Past Cleans table when the Homebrew list became its second
// user. The parent must be position: relative. Width is remembered per page when
// storageKey is given (cpc.<page>.<leaf>, e.g. cpc.homebrew.listWidth).
//   <UiSidePanel :width="320" storage-key="cpc.homebrew.listWidth" label="list">...</UiSidePanel>
import { ref, onUnmounted } from 'vue'

const props = withDefaults(defineProps<{
  width?: number          // default width, px
  min?: number
  max?: number
  storageKey?: string
  label?: string          // for the toggle's title: "Collapse list"
}>(), { width: 280, min: 200, max: 640, label: 'list' })

const collapsed = ref(false)
const w = ref(props.width)
if (props.storageKey) {
  try {
    const saved = Number(localStorage.getItem(props.storageKey))
    if (saved >= props.min && saved <= props.max) w.value = saved
  } catch { /* storage blocked */ }
}

const dragging = ref(false)
let stopDrag: (() => void) | null = null
function startDrag(e: PointerEvent) {
  const startX = e.clientX
  const startW = w.value
  dragging.value = true
  const move = (ev: PointerEvent) => { w.value = Math.min(props.max, Math.max(props.min, startW + ev.clientX - startX)) }
  const up = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
    document.body.style.cursor = ''
    dragging.value = false
    stopDrag = null
    if (props.storageKey) try { localStorage.setItem(props.storageKey, String(w.value)) } catch { /* ignore */ }
  }
  document.body.style.cursor = 'col-resize'
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
  stopDrag = up
}
onUnmounted(() => stopDrag?.())
</script>

<template>
  <div class="ui-side" :class="{ collapsed, dragging }" :style="{ width: (collapsed ? 0 : w) + 'px' }">
    <aside class="ui-side__panel"><slot /></aside>
    <div v-if="!collapsed" class="ui-side__grip" title="Drag to resize" @pointerdown.prevent="startDrag" />
    <button
      class="ui-side__toggle" :style="{ left: collapsed ? '8px' : (w - 12) + 'px' }"
      :title="(collapsed ? 'Expand ' : 'Collapse ') + label"
      @click="collapsed = !collapsed"
    >{{ collapsed ? '›' : '‹' }}</button>
  </div>
</template>

<style scoped>
.ui-side { position: relative; flex-shrink: 0; transition: width 0.18s ease; }
.ui-side.dragging { transition: none; }
.ui-side__panel {
  height: 100%; display: flex; flex-direction: column; overflow: hidden;
  background: var(--surface); border-right: 1px solid var(--line);
}
.ui-side.collapsed .ui-side__panel { border-right: 0; }
.ui-side__grip { position: absolute; top: 0; right: -3px; width: 6px; height: 100%; cursor: col-resize; z-index: 4; }
.ui-side__grip:hover, .ui-side.dragging .ui-side__grip { background: var(--accent-soft); }
.ui-side__toggle {
  position: absolute; top: 12px; z-index: 5; width: 24px; height: 24px;
  display: grid; place-items: center; border: 1px solid var(--line); border-radius: 50%;
  background: var(--surface); color: var(--text-muted); cursor: pointer; box-shadow: var(--shadow-sm);
  font-size: 14px; transition: left 0.18s ease;
}
.ui-side.dragging .ui-side__toggle { transition: none; }
.ui-side__toggle:hover { color: var(--accent); border-color: var(--accent); }
</style>
