<script setup lang="ts">
// Claude source screen. LEFT = ControlFeed (Guide Dog coaching channel).
// RIGHT = ControlCapture (live frame + session/game controls) + manual keyboard.
// Portrait-first: Pluto shares the monitor with Claude Code for the video.
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import type { NodeMap } from '../../composables/useNodes'
import type { FeedLine } from './ControlFeed.vue'
import ControlFeed from './ControlFeed.vue'
import ControlCapture from './ControlCapture.vue'
import ControlLayout from './ControlLayout.vue'

const props = defineProps<{
  active:     boolean
  nodes?:     NodeMap
  mapSource:  string
  target:     string
  mapping:    string
  targetDev?: string
}>()
const emit = defineEmits<{ 'drive-error': [string] }>()

const rumble = ref(false)
let _rumbleTimer = 0
function onRumble() {
  rumble.value = true
  if (_rumbleTimer) clearTimeout(_rumbleTimer)
  _rumbleTimer = window.setTimeout(() => { rumble.value = false }, 400)
}

const API = `http://${window.location.hostname}:7700`
const captureRef = ref<InstanceType<typeof ControlCapture> | null>(null)

// ── Guide Dog log ───────────────────────────────────────────────────────
interface LogLine { ts: number; state: string; role?: string }
const rawLines = ref<LogLine[]>([])

const claudeColor = computed(() => props.nodes?.['claude']?.color ?? 'var(--accent)')
const roleColors  = computed(() => ({
  claude:   claudeColor.value,
  system:   'var(--text-muted)',
  operator: 'var(--text-muted)',
}))

const feedLines = computed<FeedLine[]>(() => rawLines.value.map(l => ({ role: l.role, state: l.state })))

async function refreshLog() {
  try {
    const j = await (await fetch(`${API}/control/log`)).json()
    rawLines.value = Array.isArray(j.lines) ? j.lines : []
  } catch { /* leave last known */ }
  captureRef.value?.refreshLog()   // keep rumble detection in sync
}

async function onSend(v: string) {
  await captureRef.value?.postLog(v, 'operator')
  await refreshLog()
}
async function onQuick(v: string) {
  await captureRef.value?.postLog(v, 'operator')
  await refreshLog()
}

// ── polling (2 s) ───────────────────────────────────────────────────────
let poll = 0
function startPoll() { if (!poll) poll = window.setInterval(refreshLog, 2000) }
function stopPoll()  { if (poll) { clearInterval(poll); poll = 0 } }

function activate() { refreshLog(); startPoll() }
onMounted(() => { if (props.active) activate() })
onBeforeUnmount(stopPoll)
watch(() => props.active, (on) => { if (on) activate(); else stopPoll() })
</script>

<template>
  <ControlLayout :active="active" :map-source="mapSource" :target="target" :mapping="mapping" :target-dev="targetDev || ''" :max-cells="['ne']" @drive-error="emit('drive-error', $event)">
    <!-- NW: Guide Dog chat (spans full-height left, SW empty) -->
    <template #nw>
      <ControlFeed
        title="Guide Dog"
        :lines="feedLines"
        :role-colors="roleColors"
        empty-text="Guide Dog appears here. Type to guide Claude as it plays."
        placeholder="Guide Dog…"
        @send="onSend"
        @quick="onQuick" />
    </template>

    <!-- NE: live video input -->
    <template #ne>
      <ControlCapture ref="captureRef"
        :active="active" :show-game-actions="true"
        :map-source="mapSource" :target="target" :mapping="mapping" :target-dev="targetDev"
        @drive-error="emit('drive-error', $event)"
        @rumble="onRumble" />
    </template>
  </ControlLayout>
</template>
