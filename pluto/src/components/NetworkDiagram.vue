<script setup lang="ts">
import { computed, ref } from 'vue'
import type { NodeMap } from '../composables/useNodes'
import { API_BASE } from '../composables/useNodes'

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
  ps3:     { x: 610, y:  80 },
  gba:     { x: 780, y: 130 },
  ws:      { x: 800, y: 430 },
  host:    { x: 660, y: 460 },
}

const BUBBLE_R    = 32
const BUBBLE_HOV  = 36
const BUBBLE_OPEN = 78

const EDGES = [
  ['host', 'gateway'],
  ['gateway', 'wii'], ['gateway', 'dc'],
  ['gateway', 'ps3'], ['gateway', 'gba'], ['gateway', 'ws'],
]

const activeMenu  = ref<string | null>(null)
const hoveredNode = ref<string | null>(null)
const deploying   = ref<string | null>(null)

const presentNodes = computed(() =>
  Object.keys(props.nodes).filter(id => LAYOUT[id])
)

const visibleEdges = computed(() =>
  EDGES
    .filter(([a, b]) => props.nodes[a] && props.nodes[b])
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
)

function isUp(id: string)       { return props.nodes[id]?.status === 'up' }
function isClickable(id: string){ return isUp(id) && id !== 'gateway' }

function bubbleR(id: string): number {
  if (activeMenu.value === id) return BUBBLE_OPEN
  if (hoveredNode.value === id) return BUBBLE_HOV
  return BUBBLE_R
}

function statusColor(id: string): string {
  return isUp(id) ? 'var(--color-up)' : 'var(--color-down)'
}

function onEnter(id: string) {
  if (isClickable(id)) hoveredNode.value = id
}
function onLeave(id: string) {
  if (hoveredNode.value === id) hoveredNode.value = null
}
function toggleMenu(id: string) {
  if (!isClickable(id)) return
  activeMenu.value = activeMenu.value === id ? null : id
}
function closeMenu() { activeMenu.value = null }

async function deploy(id: string) {
  deploying.value = id
  await fetch(`${API_BASE}/deploy/${id}`, { method: 'POST' })
  deploying.value = null
  activeMenu.value = null
}
</script>

<template>
  <svg
    viewBox="0 0 1000 600"
    xmlns="http://www.w3.org/2000/svg"
    class="diagram"
    preserveAspectRatio="xMidYMid meet"
    @click.self="closeMenu"
  >
    <!-- Edges -->
    <g>
      <line
        v-for="e in visibleEdges" :key="e.key"
        :x1="e.x1" :y1="e.y1" :x2="e.x2" :y2="e.y2"
        :stroke="e.up ? 'var(--color-up)' : 'var(--color-down)'"
        stroke-width="1.5" stroke-dasharray="6 4" opacity="0.4"
      />
    </g>

    <!-- Nodes -->
    <g
      v-for="id in presentNodes" :key="id"
      :transform="`translate(${LAYOUT[id].x}, ${LAYOUT[id].y})`"
      :class="['node', isClickable(id) ? 'node--clickable' : '']"
      @mouseenter="onEnter(id)"
      @mouseleave="onLeave(id)"
      @click="toggleMenu(id)"
    >
      <!-- Bubble grows behind everything -->
      <circle :r="bubbleR(id)" fill="#e8e8e6" class="bubble"/>

      <!-- Content group — shifts up when open to center in expanded bubble -->
      <g :transform="activeMenu === id ? 'translate(0,-35)' : ''">

      <!-- LED — follows content so it stays at icon top-right -->
      <circle cx="24" cy="-24" r="7" :fill="isUp(id) ? '#00ff55' : '#ff2222'"/>
      <circle cx="24" cy="-24" r="4" fill="white" opacity="0.35"/>
      <circle cx="22" cy="-26" r="2" fill="white" opacity="0.5"/>

        <!-- Gateway inline SVG -->
        <svg v-if="id === 'gateway'" x="-24" y="-24" width="48" height="48" viewBox="0 0 100 100">
          <path d="M50 28 m-28-8 a30 30 0 0 1 56 0" stroke="#1a1a1a" stroke-width="3" stroke-linecap="round" opacity="0.4" fill="none"/>
          <path d="M50 28 m-18-6 a20 20 0 0 1 36 0" stroke="#1a1a1a" stroke-width="3" stroke-linecap="round" opacity="0.7" fill="none"/>
          <path d="M50 28 m-8-4 a10 10 0 0 1 16 0"  stroke="#1a1a1a" stroke-width="3" stroke-linecap="round" fill="none"/>
          <ellipse cx="50" cy="72" rx="38" ry="10" fill="#1a1a1a" opacity="0.15"/>
          <rect x="12" y="44" width="76" height="28" rx="38" fill="#1a1a1a" opacity="0.9"/>
          <ellipse cx="50" cy="44" rx="38" ry="10" fill="#1a1a1a"/>
          <circle cx="50" cy="44" r="5" fill="#1a1a1a" opacity="0.35"/>
        </svg>

        <!-- Console icon -->
        <image
          v-else-if="ICONS[id]"
          :href="ICONS[id]"
          x="-24" y="-24" width="48" height="48"
          :opacity="isUp(id) ? 0.92 : 0.25"
        />

        <!-- Label -->
        <text y="52" text-anchor="middle" class="node-label" :fill="statusColor(id)">
          {{ nodes[id]?.name ?? id }}
        </text>

        <!-- IP -->
        <text y="65" text-anchor="middle" class="node-ip">{{ nodes[id]?.ip }}</text>

        <!-- Deploy button — appears below IP when open -->
        <g
          v-if="activeMenu === id"
          class="deploy-btn"
          @click.stop="deploy(id)"
        >
          <rect x="-28" y="74" width="56" height="20" rx="10" fill="var(--color-up)"/>
          <text x="0" y="89" text-anchor="middle" class="deploy-label">
            {{ deploying === id ? '...' : 'DEPLOY' }}
          </text>
        </g>

      </g>
    </g>
  </svg>
</template>

<style scoped>
.diagram { width: 100%; height: 100%; display: block; }
.node { cursor: default; }
.node--clickable { cursor: pointer; }
.bubble { transition: r 0.2s ease; }
.node-label {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}
.node-ip {
  font-family: var(--font-mono);
  font-size: 11px;
  fill: var(--color-secondary);
  opacity: 0.8;
}
.deploy-btn { cursor: pointer; }
.deploy-label {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.12em;
  fill: white;
  pointer-events: none;
}
</style>
