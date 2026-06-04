<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import type { NodeMap } from '../composables/useNodes'
import { useDeploy } from '../composables/useDeploy'
import NodeBubble from './NodeBubble.vue'
import DeployTerminal from './DeployTerminal.vue'
import AchievementToast from './AchievementToast.vue'

import imgWii  from '../assets/consoles/wii.png'
import imgDc   from '../assets/consoles/dc.png'
import imgPs3  from '../assets/consoles/ps3.png'
import imgGba  from '../assets/consoles/gba.png'
import imgWs   from '../assets/consoles/ws.png'
import imgHost from '../assets/consoles/host.png'

const props = defineProps<{ nodes: NodeMap }>()

const ICONS: Record<string, string> = {
  wii: imgWii, dc: imgDc, ps3: imgPs3,
  gba: imgGba, ws: imgWs, host: imgHost,
}

const LAYOUT: Record<string, { x: number; y: number }> = {
  gateway: { x: 500, y: 280 },
  wii:     { x: 220, y: 130 },
  dc:      { x: 390, y:  80 },
  ps3:     { x: 700, y: 130 },
  gba:     { x:  80, y: 230 },
  ws:      { x: 800, y: 430 },
  host:    { x: 660, y: 460 },
}

const BUBBLE_R    = 32
const BUBBLE_OPEN = 78

const {
  deploying, deployOutput,
  showToast, toastConsoleName, toastDuration,
  deploy, openLocal, clearOutput, dismissToast,
} = useDeploy(() => props.nodes)

const activeMenu  = ref<string | null>(null)
const hoveredNode = ref<string | null>(null)

const presentNodes = computed(() => Object.keys(props.nodes).filter(id => LAYOUT[id]))

const visibleEdges = computed(() => {
  const pairs: Array<[string, string]> = []
  for (const [id, node] of Object.entries(props.nodes)) {
    if (id === 'gateway') continue
    pairs.push([node.parent ?? 'gateway', id])
  }
  return pairs
    .filter(([a, b]) => props.nodes[a] && props.nodes[b] && LAYOUT[a] && LAYOUT[b])
    .map(([a, b]) => {
      const ax = LAYOUT[a].x, ay = LAYOUT[a].y
      const bx = LAYOUT[b].x, by = LAYOUT[b].y
      const dx = bx - ax, dy = by - ay
      const len = Math.sqrt(dx * dx + dy * dy)
      const ux = dx / len, uy = dy / len
      return {
        key: `${a}-${b}`,
        x1: ax + ux * BUBBLE_R, y1: ay + uy * BUBBLE_R,
        x2: bx - ux * BUBBLE_R, y2: by - uy * BUBBLE_R,
        up: props.nodes[a]?.status === 'up' && props.nodes[b]?.status === 'up',
      }
    })
})

function isUp(id: string)        { return props.nodes[id]?.status === 'up' }
function isClickable(id: string) { return isUp(id) && id !== 'gateway' }

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
const TUCK      = 30

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
          :stroke-dasharray="activeMenu && e.key.includes(activeMenu) && deployOutput[activeMenu]?.ok ? '4 4' : '6 4'"
          :class="{ 'edge-flowing': activeMenu && e.key.includes(activeMenu) && deployOutput[activeMenu]?.ok }"
          :opacity="e.up ? 0.8 : 0.2"
        />
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
          @toggle="toggleMenu(id)"
          @deploy="deploy(id)"
          @open-local="openLocal(id)"
        />
      </g>
    </svg>

    <!-- z-2: deploy terminal -->
    <DeployTerminal
      v-if="consoleId"
      :console-id="consoleId"
      :output="deployOutput[consoleId]!"
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
          @toggle="toggleMenu(activeMenu)"
          @deploy="deploy(activeMenu)"
          @open-local="openLocal(activeMenu)"
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
.edge-flowing {
  stroke: #3deb76 !important;
  stroke-width: 2px;
  animation: pipePacketDash 0.8s linear infinite;
}
@keyframes pipePacketDash {
  to { stroke-dashoffset: -20; }
}
</style>
