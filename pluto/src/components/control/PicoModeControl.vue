<script setup lang="ts">
// Target-owned panel for a GP2040-CE Pico: which kind of device it is right now. One firmware,
// many input modes (the gamepad protocols GP2040-CE speaks, plus a mouse). The mode is stored
// on the board and changed over the UART, so this is a setting of the target, not of whatever
// source is driving it. Sending it drops the board off USB for a moment while it reboots
// into the new mode.
import { ref, watch } from 'vue'
import { driveBase } from '../../lib/drive'
import UiSelect from '../ui/UiSelect.vue'

const props = defineProps<{ active: boolean; target: string; targetDev: string }>()
const emit = defineEmits<{ 'drive-error': [msg: string] }>()

// ids are the names the hub maps to the firmware's mode numbers (bridges/hid.py MODE_VALUES)
const MODES = [
  { id: 'xinput', label: 'Gamepad: XInput' },
  { id: 'switch', label: 'Gamepad: Nintendo Switch' },
  { id: 'switchpro', label: 'Gamepad: Switch Pro' },
  { id: 'ps3', label: 'Gamepad: PS3' },
  { id: 'ps4', label: 'Gamepad: PS4' },
  { id: 'ps5', label: 'Gamepad: PS5' },
  { id: 'xbone', label: 'Gamepad: Xbox One' },
  { id: 'xboxog', label: 'Gamepad: Original Xbox' },
  { id: 'generic', label: 'Gamepad: Generic HID' },
  { id: 'psclassic', label: 'Gamepad: PlayStation Classic' },
  { id: 'mdmini', label: 'Gamepad: Mega Drive Mini' },
  { id: 'neogeo', label: 'Gamepad: Neo Geo Mini' },
  { id: 'pcemini', label: 'Gamepad: PC Engine Mini' },
  { id: 'egret', label: 'Gamepad: Egret II' },
  { id: 'astro', label: 'Gamepad: Astro City' },
  { id: 'p5general', label: 'Gamepad: Persona 5' },
  { id: 'keyboard', label: 'Keyboard' },
  { id: 'mouse', label: 'Mouse' },
]

// The board does not report its mode, so this is the last one sent from here (kept per
// device in this browser only as a convenience; it can be stale if changed elsewhere).
const KEY = () => 'cpc.picoMode.' + props.targetDev
const current = ref('')
const busy = ref(false)
const note = ref('')

function load() {
  try { current.value = localStorage.getItem(KEY()) || '' } catch { current.value = '' }
}
watch(() => props.targetDev, load, { immediate: true })

async function setMode(id: string) {
  if (busy.value || !id) return
  busy.value = true
  note.value = ''
  try {
    const r = await fetch(`${driveBase()}/control/drive`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'mode', mode: id, target: props.target, dev: props.targetDev }),
    })
    const j = await r.json().catch(() => null)
    if (j && j.ok === false) throw new Error(j.error || 'mode failed')
    current.value = id
    try { localStorage.setItem(KEY(), id) } catch { /* convenience only */ }
    emit('drive-error', '')
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'failed'
    note.value = msg
    emit('drive-error', msg)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="pm">
    <p class="pm__lbl">Mode</p>
    <UiSelect :model-value="current" :disabled="busy" @update:model-value="setMode">
      <option v-if="!current" value="" disabled>Choose a mode</option>
      <option v-for="m in MODES" :key="m.id" :value="m.id">{{ m.label }}</option>
    </UiSelect>
    <p v-if="note" class="pm__note">{{ note }}</p>
  </div>
</template>

<style scoped>
.pm { padding: 12px; }
.pm__lbl { margin: 0 0 8px; font-size: 11px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-muted); }
.pm__note { margin: 10px 0 0; font-size: 12px; color: var(--text-muted); }
</style>
