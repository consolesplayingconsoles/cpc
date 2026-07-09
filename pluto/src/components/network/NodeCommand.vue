<script setup lang="ts">
import { ref, computed } from 'vue'
import UiButton from './ui/UiButton.vue'
import UiActionRow from './ui/UiActionRow.vue'
import UiSelect from './ui/UiSelect.vue'

// A node command is just a chat message: "@handle verb [arg]". The shapes are
// finite, so one component renders the right input and emits the assembled line;
// the parent posts it to /messages (logged in the chat feed AND messages.log).
// Every verb is always sendable — an unbuilt one gets a gracious "not implemented
// yet" from the server. The backend is the contract; the UI never pre-judges.
interface Cmd { verb: string; desc?: string; target?: string; multiline?: boolean; url?: string; script?: string; credit?: string }

const props = defineProps<{
  handle:   string                              // e.g. "@dropbox"
  cmd:      Cmd
  targets?: { label: string; value: string }[]  // for the node-dropdown shape
}>()
const emit = defineEmits<{ run: [text: string] }>()

const kind  = computed(() => props.cmd.multiline ? 'text' : props.cmd.target ? 'node' : 'button')
const label = computed(() => props.cmd.verb.charAt(0).toUpperCase() + props.cmd.verb.slice(1))
const base  = computed(() => `${props.handle} ${props.cmd.verb}`)

const text   = ref('')
const target = ref(props.targets?.[0]?.value ?? '@everyone')
const sent   = ref(false)

function fire(arg?: string) {
  emit('run', arg ? `${base.value} ${arg}` : base.value)
  text.value = ''
  sent.value = true
  setTimeout(() => { sent.value = false }, 1600)
}
</script>

<template>
  <!-- command -->
  <UiActionRow v-if="kind === 'button'" @click="fire()">
    <span class="cmd__label">{{ label }}</span>
    <span v-if="cmd.desc" class="cmd__desc">{{ cmd.desc }}</span>
    <span v-if="sent" class="cmd__sent">sent &check;</span>
  </UiActionRow>

  <!-- command + text -->
  <div v-else-if="kind === 'text'" class="cmd cmd--form">
    <div class="cmd__head">
      <span class="cmd__label">{{ label }}</span>
      <span v-if="sent" class="cmd__sent">sent &check;</span>
    </div>
    <textarea v-model="text" class="cmd__text" :placeholder="cmd.desc || 'Write…'" rows="3"></textarea>
    <UiButton variant="primary" class="cmd__send" :disabled="!text.trim()" @click="fire(text.trim())">Send</UiButton>
  </div>

  <!-- command + node -->
  <div v-else class="cmd cmd--form">
    <div class="cmd__head">
      <span class="cmd__label">{{ label }}</span>
      <span v-if="cmd.desc" class="cmd__desc">{{ cmd.desc }}</span>
      <span v-if="sent" class="cmd__sent">sent &check;</span>
    </div>
    <div class="cmd__row">
      <UiSelect v-model="target" class="cmd__select">
        <option v-for="t in targets" :key="t.value" :value="t.value">{{ t.label }}</option>
      </UiSelect>
      <UiButton variant="primary" class="cmd__send" @click="fire(target)">Send</UiButton>
    </div>
  </div>
</template>

<style scoped>
.cmd { width: 100%; margin-bottom: 8px; }
/* the command-button row frame is now UiActionRow */
.cmd--form {
  padding: 10px 12px;
  background: var(--surface-2); border: 1px solid var(--line); border-radius: 10px;
}
.cmd__head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.cmd__label { font-size: 14px; font-weight: 600; color: var(--text); }
.cmd__desc { font-size: 12px; color: var(--text-faint); }
.cmd__sent { margin-left: auto; font-size: 11px; color: var(--color-up); }
.cmd__text {
  width: 100%; resize: vertical; box-sizing: border-box;
  font: inherit; font-size: 13px; color: var(--text);
  background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 7px 9px;
}
.cmd__row { display: flex; gap: 8px; align-items: center; }
/* layout only — the field look comes from UiSelect */
.cmd__select { flex: 1; }
/* layout only — the terracotta look + hover + disabled now come from UiButton */
.cmd__send { margin-top: 8px; }
.cmd__row .cmd__send { margin-top: 0; }
</style>
