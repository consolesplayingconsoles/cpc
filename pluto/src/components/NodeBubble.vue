<script setup lang="ts">
import { computed, ref } from 'vue'
import type { NodeData } from '../composables/useNodes'
import { BUBBLE_R, BUBBLE_HOV, BUBBLE_OPEN } from '../composables/bubbleConstants'

const props = defineProps<{
  id:             string
  node:           NodeData
  icon?:          string
  isActive:       boolean
  isHovered:      boolean
  isDeploying:    boolean
  isUnconfigured: boolean
}>()

const emit = defineEmits<{
  toggle:       []
  deploy:       []
  'open-local': []
  'open-smb':   []
}>()

const isLocalhost  = computed(() =>
  props.id === 'host' || props.node.ip === '127.0.0.1' || props.node.ip === 'localhost'
)
const showFolderBtn = computed(() => isLocalhost.value || !!props.node.smb)
function handleFolder() {
  if (isLocalhost.value) emit('open-local')
  else emit('open-smb')
}

const hoveredBtn = ref<'deploy' | 'folder' | null>(null)

const bubbleR     = computed(() => props.isActive ? BUBBLE_OPEN : props.isHovered ? BUBBLE_HOV : BUBBLE_R)
const statusColor = computed(() => {
  if (props.node.status === 'up') return 'var(--color-up)'
  if (props.isUnconfigured)       return 'var(--color-secondary)'
  return 'var(--color-down)'
})
const borderColor  = computed(() => props.node.color ?? '#ccccca')

// Disabled (unconfigured) nodes keep their console icon in full colour so the
// device stays recognisable — the "off" state is signalled by a dashed, muted
// ring and a hollow fill rather than by greying the icon into the background.
const isUp         = computed(() => props.node.status === 'up')
const bubbleFill   = computed(() => props.isUnconfigured ? '#fbfbfa' : '#e8e8e6')
const bubbleStroke = computed(() => props.isUnconfigured ? '#b4b4b0' : borderColor.value)
const bubbleDash   = computed(() => props.isUnconfigured ? '5 5' : undefined)
const iconOpacity  = computed(() => {
  if (isUp.value)            return 0.92
  if (props.isUnconfigured)  return 0.7
  return 0.5 // configured but down
})

// Centre the action buttons as a group so the layout stays symmetric whether
// one (deploy only) or two (deploy + folder) buttons are visible.
const BTN_SPACING = 28
const btnCount    = computed(() => showFolderBtn.value ? 2 : 1)
const btnX        = (i: number) => (i - (btnCount.value - 1) / 2) * BTN_SPACING

const nameLines = computed(() => {
  const words = props.node.name.split(' ')
  if (words.length <= 1) return [props.node.name]
  const mid = Math.ceil(words.length / 2)
  return [words.slice(0, mid).join(' '), words.slice(mid).join(' ')]
})

const labelStartY = computed(() => nameLines.value.length > 1 ? 48 : 52)
const ipY         = computed(() => nameLines.value.length > 1 ? 78 : 65)

function tooltipW(label: string) { return label.length * 6.5 + 14 }
function tooltipX(label: string) { return -tooltipW(label) / 2 }
</script>

<template>
  <circle
    :r="bubbleR"
    :fill="bubbleFill"
    :stroke="bubbleStroke"
    :stroke-dasharray="bubbleDash"
    stroke-width="2.5"
    class="bubble"
    style="pointer-events:none"
  />

  <g :transform="isActive ? 'translate(0,-35)' : ''">
    <g v-if="!isUnconfigured">
      <circle cx="24" cy="-24" r="7" :fill="node.status === 'up' ? '#00ff55' : '#ff2222'" class="status-dot"/>
      <circle cx="24" cy="-24" r="4" fill="white" opacity="0.35"/>
      <circle cx="22" cy="-26" r="2" fill="white" opacity="0.5"/>
    </g>

    <svg v-if="!icon" x="-24" y="-24" width="48" height="48" viewBox="0 0 100 100">
      <path d="M50 28 m-28-8 a30 30 0 0 1 56 0" stroke="#1a1a1a" stroke-width="3" stroke-linecap="round" opacity="0.4" fill="none"/>
      <path d="M50 28 m-18-6 a20 20 0 0 1 36 0" stroke="#1a1a1a" stroke-width="3" stroke-linecap="round" opacity="0.7" fill="none"/>
      <path d="M50 28 m-8-4 a10 10 0 0 1 16 0"  stroke="#1a1a1a" stroke-width="3" stroke-linecap="round" fill="none"/>
      <ellipse cx="50" cy="72" rx="38" ry="10" fill="#1a1a1a" opacity="0.15"/>
      <rect x="12" y="44" width="76" height="28" rx="38" fill="#1a1a1a" opacity="0.9"/>
      <ellipse cx="50" cy="44" rx="38" ry="10" fill="#1a1a1a"/>
      <circle cx="50" cy="44" r="5" fill="#1a1a1a" opacity="0.35"/>
    </svg>

    <image
      v-else
      :href="icon"
      x="-20" y="-20" width="40" height="40"
      :opacity="iconOpacity"
      @click.stop="emit('toggle')"
    />

    <text text-anchor="middle" class="node-label" :fill="statusColor" @click.stop="emit('toggle')">
      <tspan v-for="(line, i) in nameLines" :key="i" x="0" :dy="i === 0 ? labelStartY : 14">{{ line }}</tspan>
    </text>

    <text :y="ipY" text-anchor="middle" class="node-ip" @click.stop="emit('toggle')">{{ node.ip }}</text>

    <g v-if="isActive" @click.stop :transform="nameLines.length > 1 ? 'translate(0,5)' : ''">
      <g
        class="action-btn"
        :transform="`translate(${btnX(0)}, 0)`"
        @click.stop="emit('deploy')"
        @mouseenter="hoveredBtn = 'deploy'"
        @mouseleave="hoveredBtn = null"
      >
        <circle cx="0" cy="90" r="11" fill="var(--color-up)" :opacity="isDeploying ? 0.4 : 1"/>
        <g v-if="isDeploying" transform="translate(0,90)" style="pointer-events:none">
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
        <g v-if="hoveredBtn === 'deploy'">
          <rect :x="tooltipX(id === 'host' ? 'CODE' : 'DEPLOY')" y="108" :width="tooltipW(id === 'host' ? 'CODE' : 'DEPLOY')" height="14" rx="4" fill="#1a1a1a" opacity="0.85"/>
          <text x="0" y="119" text-anchor="middle" class="tooltip-label">{{ id === 'host' ? 'CODE' : 'DEPLOY' }}</text>
        </g>
      </g>

      <g
        v-if="showFolderBtn"
        class="action-btn"
        :transform="`translate(${btnX(1)}, 0)`"
        @click.stop="handleFolder"
        @mouseenter="hoveredBtn = 'folder'"
        @mouseleave="hoveredBtn = null"
      >
        <circle cx="0" cy="90" r="11" fill="#888884"/>
        <g transform="translate(0,90) scale(0.75)" style="pointer-events:none">
          <rect x="-7" y="-3" width="14" height="9" rx="1.5" fill="none" stroke="white" stroke-width="2.5"/>
          <path d="M-7,-3 L-4,-6 L0,-6 L3,-3" fill="none" stroke="white" stroke-width="2.5" stroke-linejoin="round"/>
        </g>
        <g v-if="hoveredBtn === 'folder'">
          <rect :x="tooltipX(id === 'host' ? 'DIR' : 'FILES')" y="108" :width="tooltipW(id === 'host' ? 'DIR' : 'FILES')" height="14" rx="4" fill="#1a1a1a" opacity="0.85"/>
          <text x="0" y="119" text-anchor="middle" class="tooltip-label">{{ id === 'host' ? 'DIR' : 'FILES' }}</text>
        </g>
      </g>
    </g>
  </g>
</template>

<style scoped>
.bubble { transition: r 0.2s ease; }
.status-dot { transition: fill 0.8s ease; }
.node-label {
  font-family: var(--font-mono);
  font-size: 11px;
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
</style>
