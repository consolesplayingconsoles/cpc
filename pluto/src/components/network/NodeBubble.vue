<script setup lang="ts">
import { computed } from 'vue'
import type { NodeData } from '../composables/useNodes'
import { BUBBLE_R, BUBBLE_HOV } from '../composables/bubbleConstants'
import tuxImg from '../assets/tux.png'

// The whole bubble is one button: click to open its drawer (emits 'toggle'); it
// just grows on hover. Actions live in the drawer now, not on the bubble.
const props = defineProps<{
  id:             string
  node:           NodeData
  icon?:          string
  isHovered:      boolean
  isUnconfigured: boolean
}>()

const emit = defineEmits<{ toggle: [] }>()

const bubbleR     = computed(() => props.isHovered ? BUBBLE_HOV : BUBBLE_R)
const statusColor = computed(() => {
  if (props.node.status === 'up')    return 'var(--color-up)'
  if (props.node.status === 'cloud') return props.node.color ?? 'var(--color-secondary)'
  if (props.isUnconfigured)          return 'var(--color-secondary)'
  return 'var(--color-down)'
})
const borderColor  = computed(() => props.node.color ?? '#ccccca')
const isLinux      = computed(() => props.node.os === 'linux')
const isMac        = computed(() => props.node.os === 'macos')

// Disabled (unconfigured) nodes keep their console icon in full colour so the
// device stays recognisable — the "off" state is signalled by a dashed, muted
// ring and a hollow fill rather than by greying the icon into the background.
const isUp         = computed(() => props.node.status === 'up')
const bubbleFill   = computed(() => props.isUnconfigured ? '#fbfbfa' : '#e8e8e6')
const bubbleStroke = computed(() => props.isUnconfigured ? '#b4b4b0' : borderColor.value)
const bubbleDash   = computed(() => props.isUnconfigured ? '5 5' : undefined)
const iconOpacity  = computed(() => {
  if (isUp.value || props.node.status === 'cloud') return 0.92
  if (props.isUnconfigured)  return 0.7
  return 0.5 // configured but down
})

const nameLines = computed(() => {
  const words = props.node.name.split(' ')
  if (words.length <= 1) return [props.node.name]
  const mid = Math.ceil(words.length / 2)
  return [words.slice(0, mid).join(' '), words.slice(mid).join(' ')]
})

const labelStartY = computed(() => nameLines.value.length > 1 ? 48 : 52)
const ipY         = computed(() => nameLines.value.length > 1 ? 78 : 65)
</script>

<template>
  <circle
    :r="bubbleR"
    :fill="bubbleFill"
    :stroke="bubbleStroke"
    :stroke-dasharray="bubbleDash"
    stroke-width="2.5"
    class="bubble"
    style="cursor:pointer"
    @click.stop="emit('toggle')"
  />

  <g>
    <!-- cloud buddies are linked, not pinged — no status LED at all -->
    <g v-if="!isUnconfigured && node.status !== 'cloud'">
      <circle cx="24" cy="-24" r="7" :fill="node.status === 'up' ? '#00ff55' : '#ff2222'" class="status-dot"/>
      <circle cx="24" cy="-24" r="4" fill="white" opacity="0.35"/>
      <circle cx="22" cy="-26" r="2" fill="white" opacity="0.5"/>
    </g>

    <!-- OS badge, top-left. Tux for Linux (real Larry Ewing penguin, see NOTICES);
         the command glyph for macOS — a public-domain symbol, not Apple's logo. -->
    <image
      v-if="isLinux && !isUnconfigured"
      :href="tuxImg"
      x="-31" y="-33" width="16" height="19"
      style="pointer-events:none"
    />
    <text
      v-else-if="isMac && !isUnconfigured"
      x="-24" y="-15" text-anchor="middle"
      class="os-badge-mac"
      style="pointer-events:none"
    >&#x2318;</text>

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
}
.node-ip {
  font-family: var(--font-mono);
  font-size: 11px;
  fill: var(--color-secondary);
  opacity: 0.8;
}
.os-badge-mac {
  font-size: 24px;
  font-weight: 600;
  fill: #3a3a3a;
}
/* the OS hint is a dark glyph on light; on dark it'd vanish, so lift it to a
   readable grey there (light mode unchanged). */
:root[data-theme="dark"] .os-badge-mac { fill: var(--color-secondary); }
</style>
