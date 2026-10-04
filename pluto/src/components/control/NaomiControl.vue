<script setup lang="ts">
// Target-owned panel for the NAOMI: the cabinet events a player's pad cannot send.
//
// Coin, Test and Service are NOT panel buttons. A coin goes into a slot, and test and
// service sit inside the coin door, so they belong to the cabinet rather than to whatever
// source happens to be driving the game. That is why they live here and not in a source
// mapping -- they stay available whichever source is selected.
//
// Each is a MOMENTARY switch on real hardware (the filter board exposes test and service
// as PSW1 and PSW2), so we send the existing drive protocol's hold down then up rather
// than inventing an event verb: a brief closure is exactly what the hardware does, and
// OpenJVS counts a coin on the press edge.
import { ref } from 'vue'
import { driveBase } from '../../lib/drive'
import UiButton from '../ui/UiButton.vue'

const props = defineProps<{ active: boolean; target: string; source: string; mapping: string }>()
const emit = defineEmits<{ 'drive-error': [msg: string] }>()

const busy = ref('')
const note = ref('')

// How long the switch stays closed. Long enough that a poll cannot miss it (the board
// reads the IO board every frame), short enough to read as a press rather than a hold.
const CLOSURE_MS = 90

async function send(btn: string, down: boolean) {
  const r = await fetch(`${driveBase()}/control/drive`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'hold', down, btn, target: props.target, source: props.source, mapping: props.mapping }),
  })
  const j = await r.json().catch(() => null)
  if (j && j.ok === false) throw new Error(j.error || `${btn.toLowerCase()} failed`)
}

async function pulse(btn: string, label: string) {
  if (busy.value) return
  busy.value = btn
  note.value = ''
  try {
    await send(btn, true)
    await new Promise(r => setTimeout(r, CLOSURE_MS))
    await send(btn, false)
    note.value = label + ' sent'
    emit('drive-error', '')
  } catch (e) {
    // Release anyway: a switch left closed because the second call never happened would
    // read as a jammed coin mech or a held test button.
    try { await send(btn, false) } catch { /* already failed; nothing to recover */ }
    const msg = e instanceof Error ? e.message : 'failed'
    note.value = msg
    emit('drive-error', msg)
  } finally {
    busy.value = ''
  }
}
</script>

<template>
  <div class="nc">
    <p class="nc__lbl">Cabinet</p>
    <!-- Service then Test, matching the filter board silkscreen, which reads PSW2 PSW1
         left to right (PSW1 = Test, PSW2 = Service). The coin has no place on that board
         at all -- it arrives over JVS -- so it leads, as the one a player would use. -->
    <div class="nc__row">
      <!-- The coin is the slot, not a labelled button: the glyph IS the affordance.
           Title and aria-label carry the words for a screen reader and on hover. -->
      <UiButton variant="primary" class="nc__coin" title="Insert Coin" aria-label="Insert Coin"
        :disabled="!active || busy === 'COIN'" @click="pulse('COIN', 'Coin')">🪙</UiButton>
      <UiButton :disabled="!active || busy === 'SERVICE'" @click="pulse('SERVICE', 'Service')">Service</UiButton>
      <UiButton :disabled="!active || busy === 'TEST'" @click="pulse('TEST', 'Test')">Test</UiButton>
    </div>
    <p v-if="note" class="nc__note">{{ note }}</p>
  </div>
</template>

<style scoped>
.nc { padding: 12px; }
.nc__lbl { margin: 0 0 8px; font-size: 11px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-muted); }
.nc__row { display: flex; flex-wrap: wrap; gap: 8px; }
.nc__coin { font-size: 17px; line-height: 1; padding-left: 14px; padding-right: 14px; }
.nc__note { margin: 10px 0 0; font-size: 12px; color: var(--text-muted); }
</style>
