<script setup lang="ts">
import { ref, watch, computed, nextTick, onUnmounted } from 'vue'
import type { DeployResult } from '../composables/useDeploy'

const props = defineProps<{
  consoleId: string
  output:    DeployResult
  lastMs?:   number | null
  cardStyle: Record<string, string>
}>()

const emit = defineEmits<{ close: [] }>()

const bodyEl = ref<HTMLElement | null>(null)
const copied = ref(false)

// ── Live elapsed timer ────────────────────────────────────────────────────────
// Ticks once a second while the deploy is in flight so the slow sync step shows
// visible progress; frozen on finish. Paired with the "~last" reference it turns
// an opaque wait into a predictable one.
const now    = ref(Date.now())
let   timer: ReturnType<typeof setInterval> | null = null

function stopTimer() {
  if (timer) { clearInterval(timer); timer = null }
}

watch(() => props.output.ok, (ok) => {
  if (ok === null) {
    now.value = Date.now()
    if (!timer) timer = setInterval(() => { now.value = Date.now() }, 1000)
  } else {
    now.value = Date.now()   // capture the final tick
    stopTimer()
  }
}, { immediate: true })

onUnmounted(stopTimer)

function fmtDur(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000))
  const m = Math.floor(s / 60)
  return m > 0 ? `${m}:${String(s % 60).padStart(2, '0')}` : `${s}s`
}

const elapsed = computed(() => props.output.startedAt ? fmtDur(now.value - props.output.startedAt) : '0s')
const lastRef = computed(() => (props.lastMs ? fmtDur(props.lastMs) : null))

// Auto-scroll to bottom when output grows
watch(() => props.output.raw, () => {
  nextTick(() => {
    if (bodyEl.value) bodyEl.value.scrollTop = bodyEl.value.scrollHeight
  })
})

watch(() => props.output, () => { copied.value = false })

async function copyOutput() {
  try {
    await navigator.clipboard.writeText(props.output.raw)
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch { /* clipboard blocked */ }
}

const STEP_LABELS: Record<string, string> = {
  starting: 'starting',
  vendor:   'vendoring',
  sync:     'syncing',
  deps:     'linux deps',
  done:     'done',
  failed:   'failed',
}
</script>

<template>
  <div
    class="term"
    :class="{
      'term--running': output.ok === null,
      'term--err':     output.ok === false,
      'term--success': output.ok === true,
    }"
    :style="cardStyle"
    @click.stop
    @wheel.stop
  >
    <div class="term__bar">
      <span class="term__title">
        ▶ deploy ·
        <span class="term__step">{{ STEP_LABELS[output.step] ?? output.step }}</span>
        <span class="term__timer">
          {{ elapsed }}<span v-if="lastRef" class="term__last"> / ~{{ lastRef }}</span>
        </span>
      </span>
      <span class="term__tools">
        <button class="term__btn" :title="copied ? 'copied' : 'copy'" @click="copyOutput">
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
    <pre ref="bodyEl" class="term__body">{{ output.raw }}</pre>
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
  flex: 1 1 auto;
  min-width: 0;
  color: #3a7a52;
  font-size: 12px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  display: flex;
  align-items: center;
  gap: 8px;
}
.term__step {
  color: #3deb76;
  opacity: 0.7;
  font-size: 10px;
}
.term__timer {
  margin-left: auto;
  padding-left: 10px;
  color: #3deb76;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.04em;
  white-space: nowrap;
  text-transform: none;
}
.term__last { color: #3a7a52; }
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
.term--running .term__title { color: #6a8a7a; }
.term--running .term__body::after {
  content: '▋';
  animation: blink 1s step-end infinite;
  color: #3deb76;
}
@keyframes blink { 0%, 100% { opacity: 1 } 50% { opacity: 0 } }
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
