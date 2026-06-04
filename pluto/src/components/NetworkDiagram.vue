<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
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

interface DeployResult { raw: string; ok: boolean }

const activeMenu   = ref<string | null>(null)
const hoveredNode  = ref<string | null>(null)
const hoveredBtn   = ref<string | null>(null)
const deploying    = ref<string | null>(null)
const deployOutput = ref<Record<string, DeployResult | null>>({})

// Achievement Toast Reactive State
const showToast = ref(false)
const toastConsoleName = ref('')
const toastDuration = ref('')

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
        x2: bx - ux * BUBBLE_R, y2: by - ux * BUBBLE_R,
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
  if (activeMenu.value === id) {
    closeMenu()
  } else {
    activeMenu.value = id
  }
}
function closeMenu() {
  if (activeMenu.value) deployOutput.value = { ...deployOutput.value, [activeMenu.value]: null }
  activeMenu.value = null
}

function dismissToast() { showToast.value = false }

// Tooltip helpers
function tooltipW(label: string) { return label.length * 6.5 + 14 }
function tooltipX(label: string) { return -tooltipW(label) / 2 }

const SUCCESS_BANNER = `
================───────────────────────────────────
  ✔ DEPLOYMENT SUCCESSFUL
================───────────────────────────────────`

async function deploy(id: string) {
  if (id === 'host') {
    await fetch(`${API_BASE}/workspace/${id}`, { method: 'POST' })
    return
  }
  deploying.value = id
  deployOutput.value = { ...deployOutput.value, [id]: null }

  const startTime = performance.now()

  try {
    const res  = await fetch(`${API_BASE}/deploy/${id}`, { method: 'POST' })
    const data = await res.json()
    let raw  = String(data.output ?? data.error ?? '').replace(/\n{3,}/g, '\n\n').trim()

    const endTime = performance.now()
    const elapsed = ((endTime - startTime) / 1000).toFixed(2)

    if (data.status === 'ok') {
      raw = `${raw}\n${SUCCESS_BANNER}`

      // Fixed cascade delay: Terminal updates instantly, Toast displays 800ms later
      setTimeout(() => {
        toastConsoleName.value = props.nodes[id]?.name ?? id.toUpperCase()
        toastDuration.value = `${elapsed}s`
        showToast.value = true

        setTimeout(() => { showToast.value = false }, 4000)
      }, 800)
    }

    deployOutput.value = { ...deployOutput.value, [id]: { raw, ok: data.status === 'ok' } }
  } finally {
    deploying.value = null
  }
}

async function openLocal(id: string) {
  await fetch(`${API_BASE}/open/${id}`, { method: 'POST' })
}

/* ── Terminal overlay (real HTML, layered over the SVG) ─────────────── */
const wrapEl = ref<HTMLDivElement | null>(null)
const svgEl  = ref<SVGSVGElement | null>(null)
const copied = ref(false)
const cardStyle = ref<Record<string, string>>({ display: 'none' })

const CARD_W = 460
const TUCK   = 30   // px the bubble overlaps the terminal edge (avatar tuck)

const consoleId = computed(() => {
  const id = activeMenu.value
  return id && deployOutput.value[id] ? id : null
})

function updateCardPos() {
  const id = activeMenu.value
  const svg = svgEl.value
  const wrap = wrapEl.value
  if (!id || !svg || !wrap || !deployOutput.value[id] || !LAYOUT[id]) return

  const ctm = svg.getScreenCTM()
  if (!ctm) return
  const pt = svg.createSVGPoint()
  pt.x = LAYOUT[id].x
  pt.y = LAYOUT[id].y
  const sp = pt.matrixTransform(ctm)
  const wr = wrap.getBoundingClientRect()

  const scale    = ctm.a               // px per user unit (uniform)
  const nodeX    = sp.x - wr.left
  const nodeY    = sp.y - wr.top
  const bubblePx = BUBBLE_OPEN * scale
  const half     = CARD_W / 2

  const left = Math.max(half + 8, Math.min(wr.width - half - 8, nodeX))
  // Tuck the card edge up under the bubble so it peeks out from behind it.
  const belowTop   = nodeY + bubblePx - TUCK
  const aboveBot   = nodeY - bubblePx + TUCK
  const spaceBelow = wr.height - belowTop - 12
  const spaceAbove = aboveBot - 12

  const style: Record<string, string> = {
    left: `${left}px`,
    width: `${CARD_W}px`,
    transform: 'translateX(-50%)',
  }
  if (spaceBelow >= 180 || spaceBelow >= spaceAbove) {
    style.top = `${belowTop}px`
    style.maxHeight = `${Math.max(150, spaceBelow)}px`
  } else {
    style.bottom = `${wr.height - aboveBot}px`
    style.maxHeight = `${Math.max(150, spaceAbove)}px`
  }
  cardStyle.value = style
}

async function copyOutput() {
  const id = consoleId.value
  if (!id) return
  const d = deployOutput.value[id]
  if (!d) return
  try {
    await navigator.clipboard.writeText(d.raw)
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch { /* clipboard blocked — ignore */ }
}

function closeConsole() {
  const id = consoleId.value
  if (id) deployOutput.value = { ...deployOutput.value, [id]: null }
}

watch([activeMenu, deployOutput], () => { copied.value = false; nextTick(updateCardPos) }, { deep: true })
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
              <circle cx="0" cy="90" r="11" fill="var(--color-up)" :opacity="deploying === id ? 0.4 : 1" @click.stop="deploy(id)"/>
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
                <rect
                  :x="tooltipX(id === 'host' ? 'CODE' : 'DEPLOY')"
                  y="108"
                  :width="tooltipW(id === 'host' ? 'CODE' : 'DEPLOY')"
                  height="14" rx="4" fill="#1a1a1a" opacity="0.85"
                />
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
              <circle cx="0" cy="90" r="11" fill="#888884" @click.stop="openLocal(id)"/>
              <g transform="translate(0,90) scale(0.75)" style="pointer-events:none">
                <rect x="-7" y="-3" width="14" height="9" rx="1.5" fill="none" stroke="white" stroke-width="2.5"/>
                <path d="M-7,-3 L-4,-6 L0,-6 L3,-3" fill="none" stroke="white" stroke-width="2.5" stroke-linejoin="round"/>
              </g>
              <g v-if="hoveredBtn === 'folder-' + id">
                <rect
                  :x="tooltipX(id === 'host' ? 'DIR' : 'FILES')"
                  y="108"
                  :width="tooltipW(id === 'host' ? 'DIR' : 'FILES')"
                  height="14" rx="4" fill="#1a1a1a" opacity="0.85"
                />
                <text x="0" y="119" text-anchor="middle" class="tooltip-label">{{ id === 'host' ? 'DIR' : 'FILES' }}</text>
              </g>
            </g>

          </g>

        </g>
      </g>
    </svg>

    <div
      v-if="consoleId"
      class="term"
      :class="{
        'term--err': !deployOutput[consoleId]!.ok,
        'term--success': deployOutput[consoleId]!.ok
      }"
      :style="cardStyle"
      @click.stop
    >
      <div class="term__bar">
        <span class="term__title">▶ deploy · {{ consoleId }}</span>
        <span class="term__tools">
          <button class="term__btn" :title="copied ? 'copied' : 'copy output'" @click="copyOutput">
            <svg v-if="!copied" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="9" y="9" width="11" height="11" rx="2"/>
              <path d="M5 15V5a2 2 0 0 1 2-2h10"/>
            </svg>
            <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">
              <path d="M5 12l4 4 10-11"/>
            </svg>
          </button>
          <button class="term__btn term__btn--x" title="close" @click="closeConsole">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
              <path d="M6 6l12 12M18 6L6 18"/>
            </svg>
          </button>
        </span>
      </div>
      <pre class="term__body">{{ deployOutput[consoleId]!.raw }}</pre>
    </div>

    <Transition name="achievement">
      <div v-if="showToast" class="achievement-toast" @click.stop="dismissToast">
        <div class="achievement-toast__badge">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6" />
            <path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18" />
            <path d="M4 22h16" />
            <path d="M10 14.66V17c0 .55-.45 1-1 1H4v2h16v-2h-5c-.55 0-1-.45-1-1v-2.34" />
            <path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-4 4 4 4 0 0 1-4-4V6a4 4 0 0 1 4-4z" />
          </svg>
        </div>
        <div class="achievement-toast__content">
          <div class="achievement-toast__title">ACHIEVEMENT UNLOCKED</div>
          <div class="achievement-toast__desc">Successfully Deployed to {{ toastConsoleName }}</div>
        </div>
        <div class="achievement-toast__points">{{ toastDuration }}</div>
      </div>
    </Transition>
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

/* ── Edge Animation on Success ───────────────────────────────────────── */
.edge-flowing {
  stroke: #3deb76 !important;
  stroke-width: 2px;
  animation: pipePacketDash 0.8s linear infinite;
}

@keyframes pipePacketDash {
  to {
    stroke-dashoffset: -20;
  }
}

/* ── CRT terminal overlay ───────────────────────────────────────────── */
.term {
  position: absolute;
  z-index: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #060e06;
  border: 1.5px solid #1a3d22;
  border-radius: 8px;
  box-shadow:
    0 8px 30px rgba(0, 0, 0, 0.45),
    0 0 22px rgba(10, 51, 32, 0.55);
  font-family: var(--font-mono);
}
.term__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 7px 8px 7px 12px;
  background: #08160a;
  border-bottom: 1px solid #163420;
  flex: 0 0 auto;
}
.term__title {
  color: #3a7a52;
  font-size: 12px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.term__tools { display: flex; gap: 6px; }
.term__btn {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #3deb76;
  background: transparent;
  border: 1px solid #235e38;
  border-radius: 4px;
  width: 24px;
  height: 22px;
  cursor: pointer;
}
.term__btn:hover { background: #0e2414; border-color: #3deb76; }
.term__btn--x { color: #9fcfb0; }
.term__btn--x:hover { color: #ff8a8a; border-color: #7a3030; background: #200d0d; }
.term__body {
  position: relative;
  margin: 0;
  padding: 10px 14px;
  overflow-y: auto;
  overflow-x: hidden;
  flex: 1 1 auto;
  color: #3deb76;
  font-size: 14px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
  text-shadow: 0 0 4px rgba(61, 235, 118, 0.4);
  background-image: repeating-linear-gradient(
    to bottom, transparent 0, transparent 2px, rgba(0, 0, 0, 0.16) 3px
  );
}

.term--err .term__title { color: #a8856a; }
.term--err .term__body {
  color: #ff6b6b;
  text-shadow: 0 0 4px rgba(255, 80, 80, 0.35);
}

/* Success Highlight Scanline Effect */
.term--success {
  animation: borderPulse 0.6s ease-out forwards;
}

.term--success .term__body::after {
  content: " ";
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 255, 0, 0.15) 50%), linear-gradient(90deg, rgba(255, 0, 0, 0.06), rgba(0, 255, 0, 0.02), rgba(0, 0, 255, 0.06));
  background-size: 100% 4px, 6px 100%;
  z-index: 10;
  background-color: rgba(61, 235, 118, 0.03);
  pointer-events: none;
  animation: scanReveal 0.4s ease-out forwards;
}

@keyframes borderPulse {
  0% { border-color: #3deb76; box-shadow: 0 0 40px rgba(61, 235, 118, 0.7); }
  100% { border-color: #1a3d22; box-shadow: 0 8px 30px rgba(0, 0, 0, 0.45), 0 0 22px rgba(10, 51, 32, 0.55); }
}

@keyframes scanReveal {
  0% { clip-path: inset(0 0 100% 0); }
  100% { clip-path: inset(0 0 0 0); }
}

/* ── Achievement Unlocked Toast ────────────────────────────────────── */
.achievement-toast {
  position: absolute;
  top: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;

  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 350px;
  padding: 10px 18px;
  background: #090d0a;
  border: 2px solid #3deb76;
  border-radius: 30px;
  box-shadow:
    0 12px 36px rgba(0, 0, 0, 0.65),
    0 0 25px rgba(61, 235, 118, 0.3);
  cursor: pointer;
  user-select: none;
}

.achievement-toast__badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: #122919;
  border-radius: 50%;
  color: #3deb76;
  filter: drop-shadow(0 0 4px rgba(61, 235, 118, 0.6));
}

.achievement-toast__content {
  display: flex;
  flex-direction: column;
  flex-grow: 1;
}

.achievement-toast__title {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.12em;
  color: #9fcfb0;
}

.achievement-toast__desc {
  font-family: sans-serif;
  font-size: 13px;
  font-weight: 500;
  color: #ffffff;
  margin-top: 1px;
}

.achievement-toast__points {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 700;
  color: #3deb76;
  padding-left: 10px;
  border-left: 1px solid #1c472a;
  white-space: nowrap;
}

/* Vue Dynamic Transitions */
.achievement-enter-active {
  animation: achievement-in 0.45s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}
.achievement-leave-active {
  animation: achievement-in 0.28s ease-in reverse;
}

@keyframes achievement-in {
  0% {
    top: -65px;
    opacity: 0;
    transform: translateX(-50%) scale(0.88);
  }
  75% {
    transform: translateX(-50%) scale(1.02);
  }
  100% {
    top: 24px;
    opacity: 1;
    transform: translateX(-50%) scale(1);
  }
}
</style>
