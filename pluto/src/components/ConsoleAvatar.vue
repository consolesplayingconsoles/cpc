<script setup lang="ts">
import { computed } from 'vue'
import type { NodeStatus } from '../composables/useNodes'

const props = defineProps<{
  id:      string
  icon?:   string
  status:  NodeStatus
  color?:  string | null
  size?:   number
}>()

const sz      = computed(() => props.size ?? 40)
const iconSz  = computed(() => Math.round(sz.value * 0.58))
const dotSz   = computed(() => Math.max(8, Math.round(sz.value * 0.22)))
const dotOff  = computed(() => Math.round(sz.value * 0.06))
const border  = computed(() => props.color ?? 'var(--color-border)')
</script>

<template>
  <div class="avatar" :style="{ width: sz + 'px', height: sz + 'px' }">
    <div
      class="avatar-ring"
      :class="{ 'avatar-ring--dashed': status === 'unconfigured' }"
      :style="{
        width:       sz + 'px',
        height:      sz + 'px',
        borderColor: status === 'unconfigured' ? '#b4b4b0' : border,
        background:  status === 'unconfigured' ? '#fbfbfa' : '#e8e8e6',
      }"
    >
      <img
        v-if="icon"
        :src="icon"
        :alt="id"
        class="avatar-icon"
        :style="{
          width:   iconSz + 'px',
          height:  iconSz + 'px',
          opacity: status === 'up' ? 0.92 : status === 'unconfigured' ? 0.7 : 0.45,
        }"
      />
      <!-- fallback: wifi/gateway symbol -->
      <svg v-else :width="iconSz" :height="iconSz" viewBox="0 0 24 24" fill="none" opacity="0.4">
        <path d="M12 18.5a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3z" fill="#1a1a1a"/>
        <path d="M7 14.5a7 7 0 0 1 10 0" stroke="#1a1a1a" stroke-width="2" stroke-linecap="round"/>
        <path d="M3.5 11A12 12 0 0 1 20.5 11" stroke="#1a1a1a" stroke-width="2" stroke-linecap="round"/>
      </svg>
    </div>

    <!-- status dot — not shown for unconfigured nodes -->
    <span
      v-if="status !== 'unconfigured'"
      class="avatar-dot"
      :style="{
        width:  dotSz + 'px',
        height: dotSz + 'px',
        right:  dotOff + 'px',
        top:    dotOff + 'px',
        background: status === 'up' ? '#00dd55' : '#cc2222',
      }"
    />
  </div>
</template>

<style scoped>
.avatar {
  position: relative;
  flex-shrink: 0;
}

.avatar-ring {
  border-radius: 50%;
  border: 2px solid;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.avatar-ring--dashed {
  border-style: dashed;
}

.avatar-icon {
  object-fit: contain;
  display: block;
}

.avatar-dot {
  position: absolute;
  border-radius: 50%;
  border: 2px solid var(--color-bg, #fff);
  pointer-events: none;
}
</style>
