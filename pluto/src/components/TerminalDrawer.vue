<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import Terminal from './Terminal.vue'
import UiSidePanel from './ui/UiSidePanel.vue'
import { useRuns } from '../composables/useRuns'

// The terminal drawer: every run (deploy, build, send, sync) as a tab in one left drawer on
// every Pluto tab, so a run started on one page is still there from another. Opens itself when
// a run starts; closed, it leaves a handle on the left edge while any run is listed. It takes
// the mini chat's corner, so App hides the chat dock while it is open.
const { runs, activeId, open, closeRun, clearDone, focus, setMaxRuns } = useRuns()

const active  = computed(() => runs.value.find(r => r.id === activeId.value) ?? runs.value[runs.value.length - 1] ?? null)
const running = computed(() => runs.value.filter(r => r.output.value.ok === null).length)
const done    = computed(() => runs.value.length - running.value)

// Tabs shrink to TAB_MIN and never scroll: the row's width sets how many runs are kept
// (useRuns closes the oldest past that). Measured whenever the row is shown or resized.
const TAB_MIN = 84, TAB_GAP = 2
const tabsEl = ref<HTMLElement | null>(null)
const ro = new ResizeObserver(([e]) => setMaxRuns(Math.floor((e.contentRect.width + TAB_GAP) / (TAB_MIN + TAB_GAP))))
watch(tabsEl, (el, prev) => { if (prev) ro.unobserve(prev); if (el) ro.observe(el) })
onBeforeUnmount(() => ro.disconnect())

const fill = { inset: '0', borderRadius: '0', border: '0', boxShadow: 'none' }
</script>

<template>
  <!-- resizable like the other left panels (drag the right edge); width kept per viewer -->
  <div v-if="open && runs.length" class="td" @click.stop>
   <UiSidePanel :width="640" :min="360" :max="1100" storage-key="cpc.terminal.width" :collapsible="false">
    <header class="td__head">
      <div ref="tabsEl" class="td__tabs" role="tablist">
        <button
          v-for="r in runs"
          :key="r.id"
          class="td__tab"
          :class="{ 'td__tab--active': r.id === active?.id }"
          role="tab"
          :aria-selected="r.id === active?.id"
          :title="r.title"
          @click="focus(r.id)"
        >
          <!-- state by shape, not colour: spinner / tick / cross -->
          <span v-if="r.output.value.ok === null" class="td__state td__state--run" aria-label="running" />
          <svg v-else-if="r.output.value.ok" class="td__state" width="12" height="12" viewBox="0 0 16 16" aria-label="done"><path d="M3 8.5l3.2 3L13 4.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <svg v-else class="td__state td__state--err" width="12" height="12" viewBox="0 0 16 16" aria-label="failed"><path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
          <span class="td__label">{{ r.title }}</span>
          <span class="td__x" title="Close" @click.stop="closeRun(r.id)">
            <svg width="10" height="10" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
          </span>
        </button>
      </div>
      <button v-if="done" class="td__clear" title="Close every finished run; running ones stay" @click="clearDone">Clear done</button>
      <button class="td__btn" title="Hide terminal" @click="open = false">
        <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3.5L5.5 8l4.5 4.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
    </header>
    <div class="td__body">
      <Terminal
        v-if="active"
        :key="active.id"
        :title="active.title"
        :output="active.output.value"
        :last-ms="active.lastMs"
        :card-style="fill"
        @close="closeRun(active.id)"
      />
    </div>
   </UiSidePanel>
  </div>

  <button
    v-else-if="runs.length"
    class="td-handle"
    :title="running ? `Terminal: ${running} running` : 'Terminal'"
    @click.stop="open = true"
  >
    <svg width="15" height="15" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 4.5l3.5 3.5L3 11.5M8.5 12H13" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
    <span v-if="running" class="td__state td__state--run" aria-hidden="true" />
    <span class="td-handle__count">{{ running ? running : runs.length }}</span>
  </button>
</template>

<style scoped>
.td {
  position: absolute; top: 0; left: 0; bottom: 0; z-index: 5;
  max-width: 100%;
  display: flex;
  box-shadow: 8px 0 30px rgba(26, 34, 51, 0.18);
}
.td__head {
  flex: none; display: flex; align-items: stretch; gap: 4px;
  padding: 6px 6px 0 6px;
  background: var(--surface-2);
  border-bottom: 1px solid var(--line);
}
.td__tabs { flex: 1; min-width: 0; display: flex; gap: 2px; overflow: hidden; }
/* Tabs share the row: they shrink as more open (full name in the tooltip) down to a floor
   that still shows the state and a few letters (TAB_MIN); past that the oldest closes. */
.td__tab {
  flex: 0 1 auto; min-width: 84px; max-width: 200px;
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 6px 6px 10px;
  font-family: var(--font-sans); font-size: 12px; font-weight: 600;
  color: var(--text-muted); background: transparent;
  border: 1px solid transparent; border-bottom: 0;
  border-radius: var(--r-sm) var(--r-sm) 0 0;
  cursor: pointer;
}
.td__tab:hover { color: var(--text); background: var(--surface-3); }
.td__tab--active,
.td__tab--active:hover { color: var(--text); background: var(--surface); border-color: var(--line); }
.td__tab:focus { outline: none; }
.td__tab:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.td__label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.td__x {
  flex: none; margin-left: auto;
  display: flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; border-radius: 4px; color: var(--text-faint);
}
.td__x:hover { color: var(--text); background: var(--surface-3); }

.td__state { flex: none; }
.td__state--run {
  width: 10px; height: 10px; border-radius: 50%;
  border: 2px solid currentColor; border-right-color: transparent;
  animation: td-spin 0.9s linear infinite;
}
@keyframes td-spin { to { transform: rotate(360deg) } }
@media (prefers-reduced-motion: reduce) { .td__state--run { animation: none; border-right-color: currentColor; border-style: dotted; } }

.td__btn {
  flex: none; align-self: center; margin-bottom: 6px;
  display: flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; padding: 0;
  color: var(--text-muted); background: transparent;
  border: 0; border-radius: 6px; cursor: pointer;
}
.td__btn:hover { color: var(--accent); background: var(--surface-3); }
.td__clear {
  flex: none; align-self: center; margin-bottom: 6px;
  padding: 4px 9px;
  font-family: var(--font-sans); font-size: 12px; font-weight: 600;
  color: var(--text-muted); background: transparent;
  border: 1px solid var(--line); border-radius: 6px; cursor: pointer;
  white-space: nowrap;
}
.td__clear:hover { color: var(--accent); border-color: var(--accent); }
.td__body { flex: 1; min-height: 0; position: relative; }

/* Closed: a tab at the top of the left edge, clear of the chat dock in the bottom corner (and
   above it where a short window makes them meet; the full chat overlay, later in the DOM, still
   covers it). */
.td-handle {
  position: absolute; left: 0; top: 16px; z-index: 6;
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  padding: 10px 6px;
  font-family: var(--font-mono); font-size: 11px; font-weight: 600;
  color: var(--text-muted); background: var(--surface);
  border: 1px solid var(--line); border-left: 0;
  border-radius: 0 var(--r-sm) var(--r-sm) 0;
  box-shadow: var(--shadow-sm);
  cursor: pointer;
}
.td-handle:hover { color: var(--accent); border-color: var(--accent); }
.td-handle__count { font-variant-numeric: tabular-nums; }
</style>
