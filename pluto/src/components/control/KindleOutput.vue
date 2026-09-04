<script setup lang="ts">
// What the Kindle is showing -- by embedding the actual /kindle page, not a
// re-render of it. The first version polled /control/frame/kindle itself and drifted
// immediately: different rotation, different width, so it showed something the device
// never displayed. An iframe has one source of truth and cannot drift.
// Target-owned: only mounted for the kindle target (see ControlLayout, same way the
// roomba camera/telemetry mount for roomba).
import { ref, computed, watch } from 'vue'

const props = defineProps<{ active: boolean }>()
const API = `http://${window.location.hostname}:7700`

// Nonce (re)loads the page on activate; an empty src tears the iframe down so we
// don't hold its MJPEG stream open while the surface is hidden. Mirrors RoombaCamera.
const nonce = ref(0)
const src = computed(() => (props.active ? `${API}/kindle?n=${nonce.value}` : ''))
watch(() => props.active, (on) => { if (on) nonce.value++ }, { immediate: true })

function openPage() { window.open(`${API}/kindle`, '_blank') }
</script>

<template>
  <div class="knd">
    <div class="knd__head">
      <span class="knd__title">Kindle</span>
      <span class="knd__meta mono">/kindle</span>
      <button class="knd__open" title="Open the page the Kindle loads" @click="openPage">Open</button>
    </div>
    <div class="knd__view">
      <iframe v-if="src" :src="src" class="knd__frame" title="Kindle output" />
      <div v-else class="knd__msg mono">Inactive</div>
    </div>
  </div>
</template>

<style scoped>
.knd { display: flex; flex-direction: column; gap: var(--sp-2); height: 100%; padding: var(--sp-4); font-family: var(--font-sans); min-height: 0; }
.knd__head { display: flex; align-items: baseline; gap: 8px; flex: 0 0 auto; }
.knd__title { font-size: 13px; font-weight: 700; color: var(--text); }
.knd__meta { font-size: 11px; color: var(--text-muted); }
.knd__open { margin-left: auto; font-family: var(--font-sans); font-size: 11px; color: var(--text-muted);
  background: var(--surface-3); border: 1px solid var(--line); border-radius: var(--r-sm); padding: 2px 8px; cursor: pointer; }
.knd__open:hover { color: var(--accent); border-color: var(--accent); }
.mono { font-family: var(--font-mono); }
.knd__view { flex: 1 1 auto; min-height: 0; display: flex; align-items: center; justify-content: center;
  background: #fff; border: 1px solid var(--line); border-radius: var(--radius-sm, 8px); overflow: hidden; }
/* The page inside is built for a portrait e-ink panel, so it letterboxes in a wide
   quadrant. That's honest -- it is what the device is showing. */
.knd__frame { width: 100%; height: 100%; border: 0; display: block; background: #fff; }
.knd__msg { font-size: 12px; color: var(--text-muted); }
</style>
