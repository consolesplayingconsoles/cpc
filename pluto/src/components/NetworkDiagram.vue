<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import type { NodeMap } from '../composables/useNodes'
import type { Connection } from '../composables/useConnections'
import { useDeploy } from '../composables/useDeploy'
import { API_BASE } from '../composables/useNodes'
import { BUBBLE_R, BUBBLE_OPEN } from '../composables/bubbleConstants'
import NodeBubble from './NodeBubble.vue'
import DeployTerminal from './DeployTerminal.vue'
import AchievementToast from './AchievementToast.vue'

import { ICONS } from '../composables/useIcons'

const props = defineProps<{ nodes: NodeMap; connections: Connection[] }>()

// Two anchors drive the whole map; every other node is placed RELATIVE to one of
// them, so moving an anchor slides its entire cluster (and keeps the geometry easy
// to reason about). GATEWAY anchors the LAN — the hub everything fans out from,
// with Pi/Pluto as sub-hubs flanking it and the consoles around the rim. CLOUD
// anchors the cloud "solar system": a separate subgraph that hangs off the gateway
// (one trunk down) and fans out to the off-network service buddies. Tune these two
// points (and the dx/dy offsets) to reflow the diagram.
const GATEWAY = { x: 500, y: 350 }
const CLOUD   = { x: 500, y: 700 }

const fromGw    = (dx: number, dy: number) => ({ x: GATEWAY.x + dx, y: GATEWAY.y + dy })
const fromCloud = (dx: number, dy: number) => ({ x: CLOUD.x + dx,   y: CLOUD.y + dy })

const LAYOUT: Record<string, { x: number; y: number }> = {
  // LAN — relative to the gateway hub
  gateway:  GATEWAY,
  pi:       fromGw(-300,    0),   // sub-hub, left of the gateway
  pluto:    fromGw( 250,    0),   // control-plane host, right of the gateway
  vmu:      fromGw(-150, -235),
  dc:       fromGw( 150, -235),
  gba:      fromGw(-500, -230),
  wii:      fromGw(-320, -230),
  ws:       fromGw(-500,  -50),
  ps3:      fromGw( 350, -230),
  birdbuddy:fromGw(-180,  175),
  dreame:   fromGw( 150,  175),
  batocera: fromGw( 345,  175),
  saturn:   fromGw(-500,  120),   // Sega retro — bridged via the Pi, like the WonderSwan
  megadrive:fromGw(-350,  215),   // the older sister
  // cloud subgraph — relative to the cloud hub
  cloud:         CLOUD,
  cloud_storage: fromCloud(-200, 25),
  claude:        fromCloud( 200, 25),
}

const {
  deploying, deployOutput, lastDurations,
  showToast, toastConsoleName, toastDuration,
  deploy, clearOutput, dismissToast,
} = useDeploy(() => props.nodes)

const activeMenu  = ref<string | null>(null)
const hoveredNode = ref<string | null>(null)

const presentNodes = computed(() => Object.keys(props.nodes).filter(id => LAYOUT[id]))

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
  if (id === 'gateway') return false
  const n = props.nodes[id]
  // Only up nodes are expandable, and only when they have at least one button.
  return !!n && n.status === 'up' && (n.deploy || n.folder || !!n.code)
}

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

async function openWorkspace(id: string) {
  await fetch(`${API_BASE}/workspace/${id}`, { method: 'POST' })
}

function closeMenu() {
  if (panMoved) { panMoved = false; return }   // a pan-drag, not a real click
  if (activeMenu.value) clearOutput(activeMenu.value)
  activeMenu.value = null
}
function toggleMenu(id: string) {
  if (!isClickable(id)) return
  activeMenu.value === id ? closeMenu() : (activeMenu.value = id)
}

// ── Terminal card positioning ────────────────────────────────────────────────
const wrapEl    = ref<HTMLDivElement | null>(null)
const svgEl     = ref<SVGSVGElement | null>(null)
const cardStyle = ref<Record<string, string>>({ display: 'none' })
const CARD_W    = 460
const TUCK      = 28

const consoleId = computed(() => {
  const id = activeMenu.value
  return id && deployOutput.value[id] ? id : null
})

function updateCardPos() {
  const id   = activeMenu.value
  const svg  = svgEl.value
  const wrap = wrapEl.value
  if (!id || !svg || !wrap || !deployOutput.value[id] || !LAYOUT[id]) return

  const ctm = svg.getScreenCTM()
  if (!ctm) return
  const pt = svg.createSVGPoint()
  pt.x = LAYOUT[id].x
  pt.y = LAYOUT[id].y
  const sp = pt.matrixTransform(ctm)
  const wr = wrap.getBoundingClientRect()

  const nodeX   = sp.x - wr.left
  const nodeY   = sp.y - wr.top
  const bubblePx = BUBBLE_OPEN * ctm.a
  const half     = CARD_W / 2

  const left       = Math.max(half + 8, Math.min(wr.width - half - 8, nodeX))
  const belowTop   = nodeY + bubblePx - TUCK
  const aboveBot   = nodeY - bubblePx + TUCK
  const spaceBelow = wr.height - belowTop - 12
  const spaceAbove = aboveBot - 12

  const style: Record<string, string> = { left: `${left}px`, width: `${CARD_W}px`, transform: 'translateX(-50%)' }
  if (spaceBelow >= 180 || spaceBelow >= spaceAbove) {
    style.top       = `${belowTop}px`
    style.maxHeight = `${Math.max(150, spaceBelow)}px`
  } else {
    style.bottom    = `${wr.height - aboveBot}px`
    style.maxHeight = `${Math.max(150, spaceAbove)}px`
  }
  cardStyle.value = style
}

watch([activeMenu, deployOutput], () => nextTick(updateCardPos), { deep: true })
onMounted(()   => window.addEventListener('resize', updateCardPos))
onUnmounted(() => window.removeEventListener('resize', updateCardPos))
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
          :opacity="e.unconfigured ? 0.08 : e.cloud ? 0.5 : e.up ? 0.8 : 0.2"
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
        v-show="id !== activeMenu"
        :transform="`translate(${LAYOUT[id].x}, ${LAYOUT[id].y})`"
        :class="['node', isClickable(id) ? 'node--clickable' : '']"
        @mouseenter="isClickable(id) && (hoveredNode = id)"
        @mouseleave="hoveredNode === id && (hoveredNode = null)"
      >
        <NodeBubble
          :id="id"
          :node="nodes[id]"
          :icon="ICONS[id]"
          :is-active="false"
          :is-hovered="hoveredNode === id"
          :is-deploying="deploying === id"
          :is-unconfigured="isUnconfigured(id)"
          @toggle="toggleMenu(id)"
          @deploy="deploy(id)"
          @open-workspace="openWorkspace(id)"
          @open-smb="openSmb(id)"
        />
      </g>
    </svg>

    <!-- z-2: deploy terminal -->
    <DeployTerminal
      v-if="consoleId"
      :console-id="consoleId"
      :output="deployOutput[consoleId]!"
      :last-ms="lastDurations[consoleId] ?? null"
      :card-style="cardStyle"
      @close="clearOutput(consoleId)"
    />

    <!-- z-3: active (expanded) node — floats above terminal -->
    <svg
      v-if="activeMenu && LAYOUT[activeMenu]"
      viewBox="0 0 1000 820"
      :style="zoomStyle"
      xmlns="http://www.w3.org/2000/svg"
      class="diagram diagram--active"
      preserveAspectRatio="xMidYMid meet"
    >
      <g
        :transform="`translate(${LAYOUT[activeMenu].x}, ${LAYOUT[activeMenu].y})`"
        class="node node--clickable"
        @click.stop="toggleMenu(activeMenu)"
      >
        <NodeBubble
          :id="activeMenu"
          :node="nodes[activeMenu]"
          :icon="ICONS[activeMenu]"
          :is-active="true"
          :is-hovered="false"
          :is-deploying="deploying === activeMenu"
          :is-unconfigured="isUnconfigured(activeMenu)"
          @toggle="toggleMenu(activeMenu)"
          @deploy="deploy(activeMenu)"
          @open-workspace="openWorkspace(activeMenu)"
          @open-smb="openSmb(activeMenu)"
        />
      </g>
    </svg>

    <AchievementToast
      :show="showToast"
      :console-name="toastConsoleName"
      :duration="toastDuration"
      @dismiss="dismissToast"
    />

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
  background: rgba(238, 240, 243, 0.92);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid var(--line);
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s, opacity 0.15s;
}
.zoom-btn:hover:not(:disabled) { background: rgba(26, 34, 51, 0.06); }
.zoom-btn:disabled { opacity: 0.38; cursor: default; }
.zoom-btn:focus         { outline: none; }
.zoom-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.diagram--bg     { z-index: 1; }
.diagram--active { z-index: 3; }
.diagram .node   { pointer-events: auto; }
.node            { cursor: default; }
.node--clickable { cursor: pointer; }
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
</style>
