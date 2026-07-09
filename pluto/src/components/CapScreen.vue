<script setup lang="ts">
// Shared capture/sensor surface: an aspect-locked screen (slotted `content`) plus the
// standard GO / WAIT / STOP input-button bar. The bar is the reusable pattern -- CapScreen
// owns the markup + styling and only EMITS `go` / `wait` / `stop`; each parent (ControlCapture
// for HDMI, KinectControl for the Kinect) wires those to its own start/pause/stop logic.
// `controls` opts the bar in; `running` gates STOP; `busy` disables GO/WAIT while a request
// is in flight. Extra source-specific buttons go through the `actions` slot.
defineProps<{
  live: boolean
  device: string
  timestamp?: string
  controls?: boolean
  running?: boolean
  busy?: boolean
}>()

const emit = defineEmits<{ go: []; wait: []; stop: [] }>()

defineSlots<{
  content(props: {}): any
  actions(props: {}): any
}>()
</script>

<template>
  <div class="cap-screen">
    <div class="cap-screen-body">
      <div class="cap-screen-inner">
        <slot name="content" />
        <div v-if="live" class="cap-screen-tag">
          <span class="cap-rec live" /> LIVE<span v-if="timestamp"> · {{ timestamp }}</span>
        </div>
      </div>
    </div>

    <!-- shared input buttons: GO / WAIT / STOP, emitted up to the parent -->
    <div v-if="controls" class="cap-controls">
      <button class="cap-btn cap-btn--go"   :disabled="busy"     @click="emit('go')"   title="Go — start">▶</button>
      <button class="cap-btn cap-btn--wait" :disabled="busy"     @click="emit('wait')" title="Wait — pause">⏸</button>
      <button class="cap-btn cap-btn--stop" :disabled="!running" @click="emit('stop')" title="Stop">⏹</button>
      <slot name="actions" />
    </div>
  </div>
</template>

<style scoped>
.cap-screen {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}

/* The screen fills the space ABOVE the controls and shrinks to fit (min-height:0), so the
   controls are always in view. The image inside letterboxes (object-fit) to keep aspect. */
.cap-screen-body {
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
  padding: var(--sp-3);
  display: flex;
}

.cap-screen-inner {
  position: relative;
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
  width: 100%;
  background: #0b0d10;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  overflow: hidden;
}

.cap-screen-tag {
  position: absolute;
  top: 6px;
  left: 6px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: #fff;
  background: rgba(0, 0, 0, 0.6);
  padding: 2px 7px;
  border-radius: 999px;
}

.cap-rec {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-faint);
  flex-shrink: 0;
  display: inline-block;
}

.cap-rec.live {
  background: var(--bad);
  animation: cap-pulse 1.4s ease-in-out infinite;
}

@keyframes cap-pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.3;
  }
}

/* shared input-button bar */
.cap-controls {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: var(--sp-1);
  padding: var(--sp-2) var(--sp-3);
  border-top: 1px solid var(--line);
  background: var(--surface);
}

.cap-btn {
  flex: 1 1 0;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 38px;
  font-size: 17px;
  line-height: 1;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: background 0.1s, opacity 0.1s;
}

.cap-btn:disabled {
  opacity: 0.35;
  cursor: default;
}

.cap-btn:active:not(:disabled) {
  transform: scale(0.94);
}

.cap-btn--go {
  background: var(--surface-3);
  color: var(--ok);
  border-color: var(--ok);
}

.cap-btn--go:hover:not(:disabled) {
  background: var(--ok);
  color: #fff;
}

.cap-btn--wait {
  background: var(--surface-3);
  color: var(--text-muted);
  border-color: var(--line-strong);
}

.cap-btn--wait:hover:not(:disabled) {
  background: var(--line-strong);
}

.cap-btn--stop {
  background: var(--surface-3);
  color: var(--bad);
  border-color: var(--bad);
}

.cap-btn--stop:hover:not(:disabled) {
  background: var(--bad);
  color: #fff;
}
</style>
