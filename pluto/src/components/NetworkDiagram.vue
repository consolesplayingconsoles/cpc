<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import type { NodeMap } from '../composables/useNodes'
import { useDeploy } from '../composables/useDeploy'
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
  ps3:     { x: 610, y:  80 },
  gba:     { x:  80, y:  55 },
  ws:      { x: 800, y: 430 },
  host:    { x: 660, y: 460 },
}

const BUBBLE_R    = 32
const BUBBLE_HOV  = 36
const BUBBLE_OPEN = 78

// ── Deploy composable ────────────────────────────────────────────────────────
const {
  deploying, deployOutput,
  showToast, toastConsoleName, toastDuration,
  deploy, openLocal, clearOutput, dismissToast,
} = useDeploy(() => props.nodes)

// ── Menu state ───────────────────────────────────────────────────────────────
const activeMenu  = ref<string | null>(null)
const hoveredNode = ref<string | null>(null)
const hoveredBtn  = ref<string | null>(null)

const presentNodes = computed(() =>
  Object.keys(props.nodes).filter(id => LAYOUT[id])
)

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
function bubbleR(id: string)     { return activeMenu.value === id ? BUBBLE_OPEN : hoveredNode.value === id ? BUBBLE_HOV : BUBBLE_R }
function statusColor(id: string) { return isUp(id) ? 'var(--color-up)' : 'var(--color-down)' }
function tooltipW(label: string) { return label.length * 6.5 + 14 }
function tooltipX(label: string) { return -tooltipW(label) / 2 }

function onEnter(id: string) { if (isClickable(id)) hoveredNode.value = id }
function onLeave(id: string) { if (hoveredNode.value === id) hoveredNode.value = null }

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

  const nodeX    = sp.x - wr.left
  const nodeY    = sp.y - wr.top
  const bubblePx = BUBBLE_OPEN * ctm.a
  const half     = CARD_W / 2

  const left        = Math.max(half + 8, Math.min(wr.width - half - 8, nodeX))
  const belowTop    = nodeY + bubblePx - TUCK
  const aboveBot    = nodeY - bubblePx + TUCK
  const spaceBelow  = wr.height - belowTop - 12
  const spaceAbove  = aboveBot - 12

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
    <svg
      ref="svgEl"
      viewBox="0 0 1000 620"
      xmlns="http://www.w3.org/2000/svg"
      class="diagram"
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
        :transform="`translate(${LAYOUT[id].x}, ${LAYOUT[id].y})`"
        :class="['node', isClickable(id) ? 'node--clickable' : '']"
        @mouseenter="onEnter(id)"
        @mouseleave="onLeave(id)"
      >
        <circle
          :r="bubbleR(id)"
          fill="#e8e8e6"
          :stroke="nodes[id]?.color ?? '#ccccca'"
          stroke-width="2.5"
          class="bubble"
          style="pointer-events:none"
        />

        <g :transform="activeMenu === id ? 'translate(0,-35)' : ''">
          <circle cx="24" cy="-24" r="7" :fill="isUp(id) ? '#00ff55' : '#ff2222'"/>
          <circle cx="24" cy="-24" r="4" fill="white" opacity="0.35"/>
          <circle cx="22" cy="-26" r="2" fill="white" opacity="0.5"/>

          <svg v-if="id === 'gateway'" x="-24" y="-24" width="48" height="48" viewBox="0 0 100 100">
            <path d="M50 28 m-28-8 a30 30 0 0 1 56 0" stroke="#1a1a1a" stroke-width="3" stroke-linecap="round" opacity="0.4" fill="none"/>
            <path d="M50 28 m-18-6 a20 20 0 0 1 36 0" stroke="#1a1a1a" stroke-width="3" stroke-linecap="round" opacity="0.7" fill="none"/>
            <path d="M50 28 m-8-4 a10 10 0 0 1 16 0"  stroke="#1a1a1a" stroke-width="3" stroke-linecap="round" fill="none"/>
            <ellipse cx="50" cy="72" rx="38" ry="10" fill="#1a1a1a" opacity="0.15"/>
            <rect x="12" y="44" width="76" height="28" rx="38" fill="#1a1a1a" opacity="0.9"/>
            <ellipse cx="50" cy="44" rx="38" ry="10" fill="#1a1a1a"/>
            <circle cx="50" cy="44" r="5" fill="#1a1a1a" opacity="0.35"/>
          </svg>

          <image
            v-else-if="ICONS[id]"
            :href="ICONS[id]"
            x="-24" y="-24" width="48" height="48"
            :opacity="isUp(id) ? 0.92 : 0.25"
            @click.stop="toggleMenu(id)"
          />

          <text y="52" text-anchor="middle" class="node-label" :fill="statusColor(id)" @click.stop="toggleMenu(id)">
            {{ nodes[id]?.name ?? id }}
          </text>
          <text y="65" text-anchor="middle" class="node-ip" @click.stop="toggleMenu(id)">{{ nodes[id]?.ip }}</text>

          <g v-if="activeMenu === id" @click.stop>
            <g
              class="action-btn"
              transform="translate(-14, 0)"
              @click.stop="deploy(id)"
              @mouseenter="hoveredBtn = 'deploy-' + id"
              @mouseleave="hoveredBtn = null"
            >
              <circle cx="0" cy="90" r="11" fill="var(--color-up)" :opacity="deploying === id ? 0.4 : 1"/>
              <g v-if="deploying === id" transform="translate(0,90)" style="pointer-events:none">
                <circle r="15" fill="none" stroke="var(--color-up)" stroke-width="1.5" stroke-dasharray="20 26" opacity="0.9">
                  <animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="0.9s" repeatCount="indefinite"/>
                </circle>
              </g>
              <g transform="translate(0,90) scale(0.6)" style="pointer-events:none">
                <g v-if="id !== 'host'">
                  <line x1="0" y1="6" x2="0" y2="-4" stroke="white" stroke-width="2.5" stroke-linecap="round"/>
                  <polyline points="-4,0 0,-5 4,0" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                  <line x1="-5" y1="6" x2="5" y2="6" stroke="white" stroke-width="2.5" stroke-linecap="round"/>
                </g>
                <g v-else>
                  <path d="M-2,-6 Q-5,-6 -5,-3 L-5,0 Q-7,1.5 -5,3 L-5,6 Q-5,9 -2,9" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  <path d="M2,-6 Q5,-6 5,-3 L5,0 Q7,1.5 5,3 L5,6 Q5,9 2,9" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </g>
              </g>
              <g v-if="hoveredBtn === 'deploy-' + id">
                <rect :x="tooltipX(id === 'host' ? 'CODE' : 'DEPLOY')" y="108" :width="tooltipW(id === 'host' ? 'CODE' : 'DEPLOY')" height="14" rx="4" fill="#1a1a1a" opacity="0.85"/>
                <text x="0" y="119" text-anchor="middle" class="tooltip-label">{{ id === 'host' ? 'CODE' : 'DEPLOY' }}</text>
              </g>
            </g>

            <g
              class="action-btn"
              transform="translate(14,0)"
              @click.stop="openLocal(id)"
              @mouseenter="hoveredBtn = 'folder-' + id"
              @mouseleave="hoveredBtn = null"
            >
              <circle cx="0" cy="90" r="11" fill="#888884"/>
              <g transform="translate(0,90) scale(0.75)" style="pointer-events:none">
                <rect x="-7" y="-3" width="14" height="9" rx="1.5" fill="none" stroke="white" stroke-width="2.5"/>
                <path d="M-7,-3 L-4,-6 L0,-6 L3,-3" fill="none" stroke="white" stroke-width="2.5" stroke-linejoin="round"/>
              </g>
              <g v-if="hoveredBtn === 'folder-' + id">
                <rect :x="tooltipX(id === 'host' ? 'DIR' : 'FILES')" y="108" :width="tooltipW(id === 'host' ? 'DIR' : 'FILES')" height="14" rx="4" fill="#1a1a1a" opacity="0.85"/>
                <text x="0" y="119" text-anchor="middle" class="tooltip-label">{{ id === 'host' ? 'DIR' : 'FILES' }}</text>
              </g>
            </g>
          </g>
        </g>
      </g>
    </svg>

    <DeployTerminal
      v-if="consoleId"
      :console-id="consoleId"
      :output="deployOutput[consoleId]!"
      :card-style="cardStyle"
      @close="clearOutput(consoleId)"
    />

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
  z-index: 2;
  pointer-events: none;
}
.diagram .node { pointer-events: auto; }
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
.action-btn { cursor: pointer; }
.tooltip-label {
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.08em;
  fill: white;
  pointer-events: none;
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
