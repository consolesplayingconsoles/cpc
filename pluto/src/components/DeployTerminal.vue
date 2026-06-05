<script setup lang="ts">
import { ref, watch } from 'vue'
import type { DeployResult } from '../composables/useDeploy'

const props = defineProps<{
  consoleId: string
  output:    DeployResult
  cardStyle: Record<string, string>
}>()

const emit = defineEmits<{ close: [] }>()

const copied = ref(false)

watch(() => props.output, () => { copied.value = false })

async function copyOutput() {
  try {
    await navigator.clipboard.writeText(props.output.raw)
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch { /* clipboard blocked — ignore */ }
}
</script>

<template>
  <div
    class="term"
    :class="{ 'term--err': !output.ok, 'term--success': output.ok }"
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
        <button class="term__btn term__btn--x" title="close" @click="emit('close')">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
            <path d="M6 6l12 12M18 6L6 18"/>
          </svg>
        </button>
      </span>
    </div>
    <pre class="term__body">{{ output.raw }}</pre>
  </div>
</template>

<style scoped>
.term {
  position: absolute;
  z-index: 2;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #060e06;
  border: 1.5px solid #1a3d22;
  border-radius: 8px;
  box-shadow: 0 8px 30px rgba(0,0,0,0.45), 0 0 22px rgba(10,51,32,0.55);
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
  text-shadow: 0 0 4px rgba(61,235,118,0.4);
  background-image: repeating-linear-gradient(
    to bottom, transparent 0, transparent 2px, rgba(0,0,0,0.16) 3px
  );
}
.term--err .term__title { color: #a8856a; }
.term--err .term__body  { color: #ff6b6b; text-shadow: 0 0 4px rgba(255,80,80,0.35); }
.term--success { animation: borderPulse 0.6s ease-out forwards; }
.term--success .term__body {
  background-image:
    repeating-linear-gradient(to bottom, transparent 0, transparent 2px, rgba(0,0,0,0.16) 3px),
    linear-gradient(rgba(18,16,16,0) 50%, rgba(0,255,0,0.08) 50%),
    linear-gradient(90deg, rgba(255,0,0,0.03), rgba(0,255,0,0.01), rgba(0,0,255,0.03));
  background-size: 100% 3px, 100% 4px, 6px 100%;
}
@keyframes borderPulse {
  0%   { border-color: #3deb76; box-shadow: 0 0 40px rgba(61,235,118,0.7); }
  100% { border-color: #1a3d22; box-shadow: 0 8px 30px rgba(0,0,0,0.45), 0 0 22px rgba(10,51,32,0.55); }
}
</style>
