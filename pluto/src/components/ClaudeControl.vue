<script setup lang="ts">
// Claude source screen. LEFT = ControlFeed (Guide Dog coaching channel).
// RIGHT = ControlCapture (live frame + session/game controls) + manual keyboard.
// Portrait-first: Pluto shares the monitor with Claude Code for the video.
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import type { NodeMap } from '../composables/useNodes'
import type { FeedLine } from './ControlFeed.vue'
import ControlFeed from './ControlFeed.vue'
import ControlCapture from './ControlCapture.vue'
import ControlKeyboard from './ControlKeyboard.vue'

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
  <div class="cc" :class="{ 'cc--rumble': rumble }">
    <div class="cc-body">

      <ControlFeed class="cc-panel"
        title="Guide Dog"
        :lines="feedLines"
        :role-colors="roleColors"
        empty-text="Guide Dog appears here. Type to guide Claude as it plays."
        placeholder="Guide Dog…"
        @send="onSend"
        @quick="onQuick" />

      <div class="cc-right">
        <ControlCapture ref="captureRef"
          :active="active" :show-game-actions="true"
          :map-source="mapSource" :target="target" :mapping="mapping" :target-dev="targetDev"
          @drive-error="emit('drive-error', $event)"
          @rumble="onRumble" />
        <section class="cc-pad">
          <ControlKeyboard :active="active" :map-source="mapSource" :target="target" :mapping="mapping"
                           :target-dev="targetDev" heading="Manual Assistance"
                           @drive-error="emit('drive-error', $event)" />
        </section>
      </div>

    </div>
  </div>
</template>

<style scoped>
.cc { display: flex; flex-direction: column; height: 100%; min-height: 0; overflow: hidden; background: var(--surface-2); position: relative; }
.cc--rumble::after { content: ''; position: absolute; inset: 0; background: rgba(220,40,40,0.40); pointer-events: none; z-index: 20; animation: cc-rumble 0.4s ease-out forwards; }
@keyframes cc-rumble { 0% { opacity: 1; } 100% { opacity: 0; } }
.cc-body  { display: flex; flex: 1 1 0; min-height: 0; overflow: hidden; }
.cc-panel { flex: 0 0 50%; min-width: 0; border-right: 1px solid var(--line); }
.cc-right { display: flex; flex-direction: column; flex: 0 0 50%; min-width: 0; min-height: 0; background: var(--surface-2); }
.cc-pad   { flex: 1 1 0; min-height: 0; min-width: 0; background: var(--surface); border-top: 1px solid var(--line); }
</style>
