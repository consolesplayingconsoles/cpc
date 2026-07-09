<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { NodeMap } from '../../composables/useNodes'
import type { Connection } from '../../composables/useConnections'
import { useDeploy } from '../../composables/useDeploy'
import { API_BASE } from '../../composables/useNodes'
import { BUBBLE_R } from '../../composables/bubbleConstants'
import NodeBubble from './NodeBubble.vue'
import NodeDrawer from './NodeDrawer.vue'
import DeployTerminal from '../DeployTerminal.vue'
import RecentActivity from '../RecentActivity.vue'

import { useMessages } from '../../composables/useMessages'
import { ICONS } from '../../composables/useIcons'
import layout from '../../../config/layout.json'

const props = defineProps<{ nodes: NodeMap; connections: Connection[] }>()
const emit = defineEmits<{ 'open-tab': [tab: string] }>()

// Shared chat feed (module-level singleton in useMessages — no second poll started).
// Powers the bottom-left "Recent Activity" tail so a command fired from a node
// drawer can show its reply without leaving the diagram.
const { messages } = useMessages()

// Diagram geometry lives in layout.json (hand-edited, like connections.json). The
// gateway is the origin everything hangs off — only its spot on the canvas is fixed
// here (assumed 0,0 from the config's side). The cloud hub sits directly below it
// (same x) at layout.cloudDy; every other node is an [dx, dy] offset from its anchor.
const ORIGIN = { x: 450, y: 270 }
const CLOUD  = { x: ORIGIN.x, y: ORIGIN.y + layout.cloudDy }

function buildLayout(): Record<string, { x: number; y: number }> {
  const out: Record<string, { x: number; y: number }> = { gateway: ORIGIN, cloud: CLOUD }
  for (const [id, off] of Object.entries(layout.fromGateway)) {
    const [dx, dy] = off as [number, number]
    out[id] = { x: ORIGIN.x + dx, y: ORIGIN.y + dy }
  }
  for (const [id, off] of Object.entries(layout.fromCloud)) {
    const [dx, dy] = off as [number, number]
    out[id] = { x: CLOUD.x + dx, y: CLOUD.y + dy }
  }
  return out
}
const LAYOUT = buildLayout()

const {
  deploying, deployOutput, lastDurations, lastDeployedAt,
  deploy, clearOutput,
} = useDeploy(() => props.nodes)

const activeMenu  = ref<string | null>(null)
const hoveredNode = ref<string | null>(null)

const presentNodes = computed(() => Object.keys(props.nodes).filter(id => LAYOUT[id]))

// Which Pluto node is THIS instance — so we can flag it with a "You are here" marker
// on a map this big. Lab under vite, C2 in the deployed dist (same gate as the drawer).
const selfId = import.meta.env.DEV ? 'lab' : 'pluto'

// ── Pan & zoom ───────────────────────────────────────────────────────────────
// Fit-to-view by default (scale 1 = the whole map, the zoomed-out overview the
// diagram is laid out for). Zoom is a CSS transform on the SVG layers (origin
// top-left); getScreenCTM picks up CSS transforms, so the deploy terminal stays
// aligned at any zoom. Wheel zooms toward the cursor; drag pans once zoomed in.
// A transform (rather than the viewBox) avoids the `meet` letterbox letting
// content spill past the viewBox into the margins instead of actually zooming.
const ZOOM_MAX = 3
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)
const zoomedIn = computed(() => zoom.value > 1.001)
const zoomStyle = computed(() => ({
  transform: `translate(${panX.value}px, ${panY.value}px) scale(${zoom.value})`,
  transformOrigin: '0 0',
}))

const clampN = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v))
function clampPan() {
  const w = wrapEl.value?.clientWidth ?? 0
  const h = wrapEl.value?.clientHeight ?? 0
  panX.value = clampN(panX.value, w * (1 - zoom.value), 0)
  panY.value = clampN(panY.value, h * (1 - zoom.value), 0)
}
// keep the point under (cxr,cyr) — wrap-relative px — fixed while scaling
function zoomToward(cxr: number, cyr: number, factor: number) {
  const z0 = zoom.value
  const z1 = clampN(z0 * factor, 1, ZOOM_MAX)
  panX.value = cxr - ((cxr - panX.value) / z0) * z1
  panY.value = cyr - ((cyr - panY.value) / z0) * z1
  zoom.value = z1
  if (z1 === 1) { panX.value = 0; panY.value = 0 }
  clampPan()
}
function onWheel(e: WheelEvent) {
  const r = wrapEl.value?.getBoundingClientRect()
  if (!r) return
  zoomToward(e.clientX - r.left, e.clientY - r.top, e.deltaY < 0 ? 1.15 : 1 / 1.15)
}
function zoomIn()    { const r = wrapEl.value?.getBoundingClientRect(); if (r) zoomToward(r.width / 2, r.height / 2, 1.3) }
function zoomOut()   { const r = wrapEl.value?.getBoundingClientRect(); if (r) zoomToward(r.width / 2, r.height / 2, 1 / 1.3) }
function resetView() { zoom.value = 1; panX.value = 0; panY.value = 0 }

// drag-to-pan (only when zoomed in). Track movement so a real drag doesn't also
// fire the background "close menu" click.
let panning = false, panMoved = false, lastX = 0, lastY = 0
function onPanDown(e: PointerEvent) {
  if (!zoomedIn.value) return
  panning = true; panMoved = false; lastX = e.clientX; lastY = e.clientY
}
function onPanMove(e: PointerEvent) {
  if (!panning) return
  if (Math.abs(e.clientX - lastX) + Math.abs(e.clientY - lastY) > 3) panMoved = true
  panX.value += e.clientX - lastX
  panY.value += e.clientY - lastY
  lastX = e.clientX; lastY = e.clientY
  clampPan()
}
function onPanUp() { panning = false }

const visibleEdges = computed(() =>
  props.connections
    .filter(c => props.nodes[c.from] && props.nodes[c.to] && LAYOUT[c.from] && LAYOUT[c.to])
    .map(c => {
      const ax = LAYOUT[c.from].x, ay = LAYOUT[c.from].y
      const bx = LAYOUT[c.to].x,   by = LAYOUT[c.to].y
      const dx = bx - ax, dy = by - ay
      const len = Math.sqrt(dx * dx + dy * dy)
      const ux = dx / len, uy = dy / len
      const flowing = (activeMenu.value === c.from || activeMenu.value === c.to)
        && (deployOutput.value[c.from]?.ok || deployOutput.value[c.to]?.ok)
      return {
        key:   `${c.from}-${c.to}`,
        label: c.label,
        pillW: c.label.length * 5.5 + 12,
        mx:    (ax + bx) / 2 - uy * 14,
        my:    (ay + by) / 2 + ux * 14,
        x1: ax + ux * BUBBLE_R, y1: ay + uy * BUBBLE_R,
        x2: bx - ux * BUBBLE_R, y2: by - uy * BUBBLE_R,
        up:           props.nodes[c.from]?.status === 'up' && props.nodes[c.to]?.status === 'up',
        unconfigured: props.nodes[c.from]?.status === 'unconfigured' || props.nodes[c.to]?.status === 'unconfigured',
        // a link into the cloud cluster — drawn in the accent, not up/down green/grey
        cloud:        props.nodes[c.from]?.status === 'cloud' || props.nodes[c.to]?.status === 'cloud',
        flowing: !!flowing,
      }
    })
)

function isUnconfigured(id: string) { return props.nodes[id]?.status === 'unconfigured' }
function isClickable(id: string) {
  // Every real node opens its drawer (even down/unconfigured, and the gateway —
  // it carries the same IP/status data worth inspecting). Only the virtual cloud
  // hub is excluded (no IP, pure topology anchor).
  return id !== 'cloud' && !!props.nodes[id]
}

const STATUS_LABEL: Record<string, string> = { up: 'Online', down: 'Offline', cloud: 'Linked', unconfigured: 'Not configured' }
const peekNode = computed(() => hoveredNode.value ? props.nodes[hoveredNode.value] : null)

function openSmb(id: string) {
  // Open the share on THIS machine — the one viewing the dashboard — not on the
  // API host. Pluto now runs headless on the EEE PC where xdg-open is useless;
  // and opening client-side means the SMB traffic flows straight from here to
  // the share host (a console, the EEE PC, ...), never through Pluto. The OS
  // handles the smb:// scheme (Finder mounts it on macOS); the anchor click
  // keeps it inside the user gesture so the browser delegates instead of blocking.
  const url = props.nodes[id]?.smb
  if (!url) return
  const a = document.createElement('a')
  a.href = url
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
}

// Open the strategic config dir in the IDE on the Lab machine (dev escape hatch).
async function openConfig() {
  await fetch(`${API_BASE}/config/open`, { method: 'POST' })
}

// The deploy terminal floats over the map (closable), not in the drawer — so the
// drawer stays lean and the stream survives closing/switching drawers. It tracks
// the node you deployed, independent of which drawer (if any) is open.
const deployTermId = ref<string | null>(null)
function startDeploy(id: string) { deployTermId.value = id; deploy(id) }
function closeDeployTerm() {
  if (deployTermId.value) clearOutput(deployTermId.value)
  deployTermId.value = null
}
const floatingDeploy = computed(() => {
  const id = deployTermId.value
  if (!id) return null
  const output = deployOutput.value[id]
  if (!output) return null
  return { id, output, lastMs: lastDurations.value[id] ?? null }
})
// Right-aligned + wide, so it doesn't block the centre of the map and long log
// lines don't wrap. Offsets to clear the open drawer (300px) or the zoom column.
const floatTermStyle = computed(() => ({
  position: 'absolute',
  right: activeMenu.value ? '316px' : '56px',
  bottom: '16px',
  width: 'min(540px, 46%)',
  maxHeight: '46%',
  zIndex: '5',
}))

function closeMenu() {
  if (panMoved) { panMoved = false; return }   // a pan-drag, not a real click
  activeMenu.value = null
}
function toggleMenu(id: string) {
  if (!isClickable(id)) return
  activeMenu.value === id ? closeMenu() : (activeMenu.value = id)
}

// ── Hover peek positioning ───────────────────────────────────────────────────
// The read-only peek is anchored to the hovered node, reusing getScreenCTM so it
// lands right at any pan/zoom. You don't pan mid-hover, so position once when the
// hovered node changes rather than tracking continuously.
const wrapEl    = ref<HTMLDivElement | null>(null)
const svgEl     = ref<SVGSVGElement | null>(null)
const peekStyle = ref<Record<string, string>>({ display: 'none' })
const PEEK_W    = 196

function updatePeekPos() {
  const id = hoveredNode.value
  const svg = svgEl.value, wrap = wrapEl.value
  if (!id || id === activeMenu.value || !svg || !wrap || !LAYOUT[id]) { peekStyle.value = { display: 'none' }; return }
  const ctm = svg.getScreenCTM(); if (!ctm) return
  const pt = svg.createSVGPoint(); pt.x = LAYOUT[id].x; pt.y = LAYOUT[id].y
  const sp = pt.matrixTransform(ctm), wr = wrap.getBoundingClientRect()
  const nodeX = sp.x - wr.left, nodeY = sp.y - wr.top
  const bubblePx = BUBBLE_R * ctm.a
  let left = nodeX + bubblePx + 10
  if (left + PEEK_W > wr.width - 8) left = nodeX - bubblePx - 10 - PEEK_W
  peekStyle.value = { left: `${Math.max(8, left)}px`, top: `${Math.max(8, nodeY - 18)}px`, width: `${PEEK_W}px` }
}

watch(hoveredNode, () => nextTick(updatePeekPos))
</script>

<template>
  <div
    ref="wrapEl"
    class="diagram-wrap"
    :class="{ 'is-pannable': zoomedIn }"
    @click="closeMenu"
    @wheel.prevent="onWheel"
    @pointerdown="onPanDown"
    @pointermove="onPanMove"
    @pointerup="onPanUp"
    @pointerleave="onPanUp"
  >
    <!-- z-1: edges + all idle nodes -->
    <svg
      ref="svgEl"
      viewBox="0 0 1000 820"
      :style="zoomStyle"
      xmlns="http://www.w3.org/2000/svg"
      class="diagram diagram--bg"
      preserveAspectRatio="xMidYMid meet"
    >
      <g>
        <line
          v-for="e in visibleEdges" :key="e.key"
          :x1="e.x1" :y1="e.y1" :x2="e.x2" :y2="e.y2"
          :stroke="e.cloud ? 'var(--accent)' : e.up ? 'var(--color-up)' : 'var(--color-down)'"
          stroke-width="1.5"
          :stroke-dasharray="e.flowing ? '4 4' : '6 4'"
          :class="{ 'edge-flowing': e.flowing }"
          :opacity="e.unconfigured ? 0.32 : e.cloud ? 0.5 : e.up ? 0.8 : 0.48"
        />
        <g
          v-for="e in visibleEdges" :key="'lbl-' + e.key"
          :transform="`translate(${e.mx}, ${e.my})`"
          :opacity="e.up || e.cloud ? 1 : 0.4"
        >
          <rect
            :x="-e.pillW / 2" y="-8"
            :width="e.pillW" height="13"
            rx="6"
            fill="#1a1a1a"
            opacity="0.82"
          />
          <text y="2" text-anchor="middle" class="edge-label">{{ e.label }}</text>
        </g>
      </g>
      <g
        v-for="id in presentNodes" :key="id"
        :transform="`translate(${LAYOUT[id].x}, ${LAYOUT[id].y})`"
        :class="['node', isClickable(id) ? 'node--clickable' : '']"
        @mouseenter="isClickable(id) && (hoveredNode = id)"
        @mouseleave="hoveredNode === id && (hoveredNode = null)"
      >
        <NodeBubble
          :id="id"
          :node="nodes[id]"
          :icon="ICONS[id]"
          :is-hovered="hoveredNode === id"
          :is-unconfigured="isUnconfigured(id)"
          @toggle="toggleMenu(id)"
        />
        <!-- "You are here" — flags the Pluto instance you're currently viewing -->
        <g v-if="id === selfId" class="yah" style="pointer-events:none">
          <rect x="-47" y="-72" width="94" height="20" rx="10" fill="var(--accent)"/>
          <text x="0" y="-58" text-anchor="middle" class="yah-text">You are here</text>
          <path d="M-6 -52 L6 -52 L0 -44 Z" fill="var(--accent)"/>
        </g>
      </g>
    </svg>

    <!-- hover peek: read-only status, anchored to the node (no actions) -->
    <div
      v-if="peekNode && hoveredNode !== activeMenu"
      class="peek"
      :style="peekStyle"
    >
      <div class="peek__name">{{ peekNode.name }}</div>
      <div class="peek__status">
        <span class="peek__dot" :class="'peek__dot--' + peekNode.status"></span>
        {{ STATUS_LABEL[peekNode.status] ?? peekNode.status }}
      </div>
      <div v-if="hoveredNode && lastDurations[hoveredNode]" class="peek__last">
        Last deploy ~{{ Math.round(lastDurations[hoveredNode] / 1000) }}s
      </div>
      <div class="peek__hint">Click to manage &rarr;</div>
    </div>

    <!-- node drawer (click): full C2 — status + actions + deploy terminal -->
    <Transition name="drawer">
      <NodeDrawer
        v-if="activeMenu && nodes[activeMenu]"
        :id="activeMenu"
        :node="nodes[activeMenu]"
        :nodes="nodes"
        :icon="ICONS[activeMenu]"
        :deploying="deploying === activeMenu"
        :last-ms="lastDurations[activeMenu] ?? null"
        :last-at="lastDeployedAt[activeMenu] ?? null"
        @close="closeMenu"
        @deploy="startDeploy(activeMenu)"
        @open-smb="openSmb(activeMenu)"
        @open-config="openConfig"
        @open-tab="emit('open-tab', 'robutek')"
      />
    </Transition>

    <!-- deploy terminal: floats over the map (closable), out of the drawer -->
    <DeployTerminal
      v-if="floatingDeploy"
      :console-id="floatingDeploy.id"
      :output="floatingDeploy.output"
      :last-ms="floatingDeploy.lastMs"
      :card-style="floatTermStyle"
      @close="closeDeployTerm"
    />

    <!-- recent activity tail (bottom-left): a peek at the chat feed so a command
         fired from a node drawer shows its reply without leaving the diagram -->
    <div class="activity-dock">
      <RecentActivity :messages="messages" @expand="emit('open-tab', 'chat')" />
    </div>

    <!-- zoom controls (fit-to-view by default; zoom in for detail, then pan) -->
    <div class="zoom-controls" @click.stop>
      <button class="zoom-btn" @click="zoomIn"  title="Zoom in">+</button>
      <button class="zoom-btn" @click="zoomOut" :disabled="!zoomedIn" title="Zoom out">&#8722;</button>
      <button class="zoom-btn" @click="resetView" :disabled="!zoomedIn" title="Fit to view">
        <svg width="13" height="13" viewBox="0 0 16 16" aria-hidden="true">
          <path d="M2 6V2h4M14 6V2h-4M2 10v4h4M14 10v4h-4"
                fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>
        </svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
/* Fit-to-view by default (the whole map zoomed out); pan/zoom drives the viewBox,
   so nothing overflows and we never need a scrollbar. */
.diagram-wrap { position: relative; width: 100%; height: 100%; overflow: hidden; touch-action: none; }
.diagram-wrap.is-pannable { cursor: grab; }
.diagram-wrap.is-pannable:active { cursor: grabbing; }
.diagram {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  display: block;
  pointer-events: none;
}

/* recent-activity dock — mirrors .zoom-controls but on the bottom-left */
.activity-dock {
  position: absolute;
  left: 16px;
  bottom: 16px;
  z-index: 2;
}

/* zoom control cluster — quiet glass chips, bottom-right */
.zoom-controls {
  position: absolute;
  right: 16px;
  bottom: 16px;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.zoom-btn {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-mono);
  font-size: 17px;
  font-weight: 600;
  line-height: 1;
  color: var(--text, #1a2233);
  background: var(--tab-track);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid var(--line);
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s, opacity 0.15s;
}
.zoom-btn:hover:not(:disabled) { background: var(--surface-3); }
.zoom-btn:disabled { opacity: 0.38; cursor: default; }
.zoom-btn:focus         { outline: none; }
.zoom-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.diagram--bg     { z-index: 1; }
.diagram--active { z-index: 3; }
.diagram .node   { pointer-events: auto; }
.node            { cursor: default; }
.node--clickable { cursor: pointer; }
/* "You are here" marker — a small accent badge that gently bobs over the current
   instance's Pluto node, so you can orient on a big map. */
.yah { animation: yahBob 1.8s ease-in-out infinite; }
.yah-text {
  font-family: var(--font-sans);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.03em;
  fill: var(--accent-ink, #fff);
}
@keyframes yahBob {
  0%, 100% { transform: translateY(0); }
  50%      { transform: translateY(-3px); }
}
.edge-label {
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 600;
  fill: #ccccca;
  pointer-events: none;
  letter-spacing: 0.04em;
}
.edge-flowing {
  stroke: #3deb76 !important;
  stroke-width: 2px;
  animation: pipePacketDash 0.8s linear infinite;
}
@keyframes pipePacketDash {
  to { stroke-dashoffset: -20; }
}

/* hover peek — read-only, anchored, never intercepts pointer events */
.peek {
  position: absolute;
  z-index: 4;
  pointer-events: none;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 12px;
  box-shadow: 0 6px 22px rgba(26, 34, 51, 0.10);
  padding: 10px 12px;
}
.peek__name   { font-size: 13px; font-weight: 600; color: var(--text); }
.peek__status { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-muted); margin-top: 4px; }
.peek__dot    { width: 7px; height: 7px; border-radius: 50%; background: var(--color-secondary); }
.peek__dot--up    { background: var(--color-up); }
.peek__dot--down  { background: var(--color-down); }
.peek__dot--cloud { background: var(--accent); }
.peek__last { font-size: 11px; color: var(--text-faint); margin-top: 4px; }
.peek__hint { font-size: 11px; color: var(--text-faint); margin-top: 8px; padding-top: 7px; border-top: 1px solid var(--line); }

/* drawer slide-in */
.drawer-enter-active, .drawer-leave-active { transition: transform 0.22s ease; }
.drawer-enter-from, .drawer-leave-to       { transform: translateX(100%); }
</style>
