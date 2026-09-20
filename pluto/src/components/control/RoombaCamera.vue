<script setup lang="ts">
// Live view of the roomba's onboard camera. Pluto's API proxies the node's RTSP stream as
// MJPEG (the RTSP URL + credentials stay server-side, keyed by the roomba node id), so this is
// just an <img> pointed at that endpoint. Only mounted for the roomba target in the NE slot
// when a source hasn't claimed it (see ControlLayout).
import { ref, computed, watch } from 'vue'

const props = defineProps<{ node: string; active: boolean }>()
const API = `http://${window.location.hostname}:7700`
const failed = ref(false)
// A nonce (re)starts the MJPEG stream on activate / node change; empty src tears it down so we
// don't hold an ffmpeg proxy open when the tab isn't showing.
const nonce = ref(0)
const src = computed(() =>
  (props.active && props.node) ? `${API}/camera/${props.node}/stream?t=${nonce.value}` : '')
watch(() => [props.active, props.node], () => { failed.value = false; nonce.value++ })

</script>

<template>
  <div class="cam">
    <div class="cam__head">
      <span class="cam__title">Camera</span>
      <span v-if="node" class="cam__node mono">{{ node }}</span>
    </div>
    <div class="cam__view">
      <img v-if="src && !failed" :src="src" alt="roomba camera" class="cam__img" @error="failed = true" />
      <div v-else class="cam__msg mono">{{ failed ? 'Camera offline' : 'No camera' }}</div>
    </div>
  </div>
</template>

<style scoped>
.cam { display: flex; flex-direction: column; gap: var(--sp-2); height: 100%; padding: var(--sp-4); font-family: var(--font-sans); min-height: 0; }
.cam__head { display: flex; align-items: baseline; gap: 8px; flex: 0 0 auto; }
.cam__title { font-size: 13px; font-weight: 700; color: var(--text); }
.cam__node { font-size: 11px; color: var(--text-muted); }
.mono { font-family: var(--font-mono); }
.cam__view { flex: 1 1 auto; min-height: 0; display: flex; align-items: center; justify-content: center;
  background: #0b0d12; border: 1px solid var(--line); border-radius: var(--radius-sm, 8px); overflow: hidden; }
.cam__img { max-width: 100%; max-height: 100%; object-fit: contain; display: block; }
.cam__msg { font-size: 12px; color: var(--text-muted); }
</style>
