<script setup lang="ts">
// DreamPicoPort source: up to 4 Dreamcast controller ports, each surfaced by the browser
// as a separate HID Gamepad. INSPECTOR-FIRST: different peripherals (a wheel racer vs a
// regular pad) report DIFFERENT button/axis layouts, so this renders the RAW indices/values
// live rather than assuming a mapping -- the same "observe real numbers before wiring
// behavior" approach used for the Roomba telemetry. A real drive mapping (config/mappings/
// dreampicoport/<target>.json, btn-index -> verb) gets authored once the layout is confirmed
// here, then a drive-capable child renders in its place (mirrors ControlKeyboard).
import { ref, computed, watch } from 'vue'
import { useGamepads } from '../../composables/useGamepads'
import { useGamepadDrive } from '../../composables/useGamepadDrive'
import ControlLayout from './ControlLayout.vue'

const props = defineProps<{
  sub: string             // gamepad index as a string ('0'..'3'), '' = show all in the inspector
  active: boolean
  target: string
  mapping: string
  targetDev?: string
  roombaIp?: string
}>()
const emit = defineEmits<{ 'drive-error': [string] }>()

const { pads } = useGamepads()

const shown = computed(() => {
  if (props.sub === '') return pads.value
  const idx = Number(props.sub)
  return pads.value.filter(p => p.index === idx)
})

// Drive from the FIRST connected pad for now (matches today's real usage: one controller
// reliably visible at a time). A per-port "drive from here" selector is the natural next
// step once more than one pad needs to be told apart while driving.
const canDrive = computed(() => !!props.target && props.target !== 'none')
useGamepadDrive({
  active: () => props.active,
  canDrive: () => canDrive.value,
  padIndex: () => pads.value[0]?.index ?? null,
  source: () => 'dreampicoport',
  target: () => props.target,
  mapping: () => props.mapping,
  targetDev: () => props.targetDev || '',
  onError: (msg) => emit('drive-error', msg),
})

// Per-port TYPE tag, kept INSIDE this component (not the URL/routing) as the operator asked --
// each DreamPicoPort port can have a different peripheral plugged in (a wheel racer vs a
// regular pad), and they report different axis/button layouts. This is display-only for now
// (labels which peripheral a port is) and will feed the eventual mapping selection once a
// drive mapping is authored per type. Keyed + persisted by the port's raw HID id string (not
// the index, since the index can shift across reconnects) via localStorage.
const TYPES = ['pad', 'wheel'] as const
type PadType = typeof TYPES[number]
const TYPE_KEY = 'cpc.dreampicoport.types'
const typeMap = ref<Record<string, PadType>>(JSON.parse(localStorage.getItem(TYPE_KEY) || '{}'))
watch(typeMap, (v) => localStorage.setItem(TYPE_KEY, JSON.stringify(v)), { deep: true })
function typeOf(id: string): PadType { return typeMap.value[id] || 'unknown' }
function setType(id: string, t: PadType) { typeMap.value = { ...typeMap.value, [id]: t } }

function axisPct(v: number) { return Math.round((v + 1) / 2 * 100) }   // -1..1 -> 0..100%
</script>

<template>
  <ControlLayout :active="active" map-source="dreampicoport" :target="target" :mapping="mapping" :target-dev="targetDev || ''" :roomba-ip="roombaIp"
    @drive-error="$emit('drive-error', $event)">
    <template #nw>
      <div class="dpp">
        <div v-if="!pads.length" class="dpp__empty mono">
          No gamepads detected. Plug DreamPicoPort into this Mac (each port shows up as its own
          controller). Chrome/Firefox only expose gamepads to a document that has FOCUS: click
          once anywhere on this page, then press a button on the controller.
        </div>

        <div v-for="p in shown" :key="p.index" class="dpp__pad">
          <div class="dpp__head">
            <span class="dpp__port">Port {{ p.index + 1 }}</span>
            <span class="dpp__id mono">{{ p.id }}</span>
            <span class="dpp__types">
              <button v-for="t in TYPES" :key="t" class="dpp__type" :class="{ on: typeOf(p.id) === t }"
                      @click="setType(p.id, t)">{{ t }}</button>
            </span>
          </div>

          <div class="dpp__section">
            <span class="dpp__lbl">Buttons ({{ p.buttons.length }})</span>
            <div class="dpp__btns">
              <div v-for="(b, i) in p.buttons" :key="i" class="dpp__btn" :class="{ on: b.pressed }">
                <span class="dpp__btn-i mono">{{ i }}</span>
                <span v-if="b.value > 0 && b.value < 1" class="dpp__btn-v mono">{{ b.value.toFixed(2) }}</span>
              </div>
            </div>
          </div>

          <div class="dpp__section">
            <span class="dpp__lbl">Axes ({{ p.axes.length }})</span>
            <div class="dpp__axes">
              <div v-for="(a, i) in p.axes" :key="i" class="dpp__axis">
                <span class="dpp__axis-i mono">{{ i }}</span>
                <span class="dpp__axis-bar"><span class="dpp__axis-fill" :style="{ width: axisPct(a) + '%' }" /></span>
                <span class="dpp__axis-v mono">{{ a.toFixed(2) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </ControlLayout>
</template>

<style scoped>
.dpp { display: flex; flex-direction: column; gap: var(--sp-4); height: 100%; padding: var(--sp-4); overflow: auto; font-family: var(--font-sans); }
.mono { font-family: var(--font-mono); }
.dpp__empty { color: var(--text-muted); font-size: 12px; line-height: 1.5; }

.dpp__pad { display: flex; flex-direction: column; gap: 10px; padding: var(--sp-3); border: 1px solid var(--line); border-radius: 8px; background: var(--surface); }
.dpp__head { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.dpp__port { font-size: 13px; font-weight: 700; color: var(--text); }
.dpp__id { font-size: 10px; color: var(--text-muted); word-break: break-all; }
.dpp__types { display: inline-flex; gap: 4px; margin-left: auto; }
.dpp__type { font-size: 10px; text-transform: uppercase; letter-spacing: 0.03em; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--line); background: var(--surface-3); color: var(--text-muted); cursor: pointer; }
.dpp__type.on { background: var(--accent-soft); color: var(--accent-hover); border-color: var(--accent); font-weight: 700; }

.dpp__section { display: flex; flex-direction: column; gap: 6px; }
.dpp__lbl { font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); }

.dpp__btns { display: flex; flex-wrap: wrap; gap: 4px; }
.dpp__btn { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1px; width: 30px; height: 26px; border-radius: 6px; background: var(--surface-3); border: 1px solid var(--line); }
.dpp__btn.on { background: var(--accent-soft); border-color: var(--accent); }
.dpp__btn-i { font-size: 10px; color: var(--text-muted); }
.dpp__btn.on .dpp__btn-i { color: var(--accent-hover); font-weight: 700; }
.dpp__btn-v { font-size: 8px; color: var(--text-faint); }

.dpp__axes { display: flex; flex-direction: column; gap: 4px; }
.dpp__axis { display: grid; grid-template-columns: 16px 1fr 40px; align-items: center; gap: 8px; }
.dpp__axis-i { font-size: 10px; color: var(--text-muted); }
.dpp__axis-bar { height: 6px; border-radius: 999px; background: var(--surface-3); overflow: hidden; }
.dpp__axis-fill { display: block; height: 100%; background: var(--accent); }
.dpp__axis-v { font-size: 10px; color: var(--text-muted); text-align: right; }
</style>
