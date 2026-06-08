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

const LAYOUT: Record<string, { x: number; y: number }> = {
  gateway:  { x: 500, y: 280 },
  wii:      { x: 230, y: 180 },
  dc:       { x: 430, y:  90 },
  ps3:      { x: 720, y: 130 },
  gba:      { x:  70, y: 125 },
  ws:       { x:  70, y: 335 },
  host:     { x: 350, y: 470 },
  batocera: { x: 820, y: 350 },
  dreame:   { x: 660, y: 460 },
  birdbuddy:{ x: 500, y: 565 },
}


const {
  deploying, deployOutput, lastDurations,
  showToast, toastConsoleName, toastDuration,
  deploy, openLocal, clearOutput, dismissToast,
} = useDeploy(() => props.nodes)

const activeMenu  = ref<string | null>(null)
const hoveredNode = ref<string | null>(null)

const presentNodes = computed(() => Object.keys(props.nodes).filter(id => LAYOUT[id]))

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
        flowing: !!flowing,
      }
    })
)

function isUnconfigured(id: string) { return props.nodes[id]?.status === 'unconfigured' }
function isClickable(id: string) {
  if (id === 'gateway') return false
  const n = props.nodes[id]
  // Only up nodes are expandable, and only when they have at least one button.
  return !!n && n.status === 'up' && (n.deploy || n.folder)
}

async function openSmb(id: string) {
  await fetch(`${API_BASE}/smb/${id}`, { method: 'POST' })
}

function closeMenu() {
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
  <div ref="wrapEl" class="diagram-wrap" @click="closeMenu">

    <!-- z-1: edges + all idle nodes -->
    <svg
      ref="svgEl"
      viewBox="0 0 1000 620"
      xmlns="http://www.w3.org/2000/svg"
      class="diagram diagram--bg"
      preserveAspectRatio="xMidYMid meet"
    >
      <g>
        <line
          v-for="e in visibleEdges" :key="e.key"
          :x1="e.x1" :y1="e.y1" :x2="e.x2" :y2="e.y2"
          :stroke="e.up ? 'var(--color-up)' : 'var(--color-down)'"
          stroke-width="1.5"
          :stroke-dasharray="e.flowing ? '4 4' : '6 4'"
          :class="{ 'edge-flowing': e.flowing }"
          :opacity="e.unconfigured ? 0.08 : e.up ? 0.8 : 0.2"
        />
        <g
          v-for="e in visibleEdges" :key="'lbl-' + e.key"
          :transform="`translate(${e.mx}, ${e.my})`"
          :opacity="e.up ? 1 : 0.4"
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
          @open-local="openLocal(id)"
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
      viewBox="0 0 1000 620"
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
          @open-local="openLocal(activeMenu)"
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
  </div>
</template>

<style scoped>
.diagram-wrap { position: relative; width: 100%; height: 100%; }
.diagram {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  display: block;
  pointer-events: none;
}
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
