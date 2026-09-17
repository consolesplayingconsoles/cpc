<script setup lang="ts">
// Send-to-node buttons: a light bordered box "Send to" followed by one icon button per target
// node (its avatar, else its name). The Media drawer's per-ROM Send, extracted when the Homebrew
// tab became its second user. The caller decides what sending does; `busy` marks the node a
// send is running to. Renders nothing when there are no targets.
//   <SendButtons :targets="sendTargets" :disabled="running" @send="id => send(f, id)" />
import UiIconButton from './ui/UiIconButton.vue'
import { ICONS } from '../composables/useIcons'

defineProps<{
  targets: { id: string; name: string }[]
  disabled?: boolean
  busy?: string | null
}>()
defineEmits<{ (e: 'send', id: string): void }>()
</script>

<template>
  <div v-if="targets.length" class="send-box" :class="{ 'is-disabled': disabled }">
    <span class="send-label">Send to</span>
    <UiIconButton
      v-for="t in targets" :key="t.id"
      variant="ghost" :title="'Send to ' + t.name"
      :disabled="disabled" :active="busy === t.id"
      @click="$emit('send', t.id)"
    >
      <img v-if="ICONS[t.id]" :src="ICONS[t.id]" class="send-ic" alt="" />
      <span v-else>{{ t.name }}</span>
    </UiIconButton>
  </div>
</template>

<style scoped>
.send-box { display: inline-flex; align-items: center; gap: 2px; padding: 2px 4px 2px 10px; border: 1px solid var(--line); border-radius: var(--r); background: var(--surface); }
.send-label { font-size: 12px; font-weight: 600; color: var(--text-muted); margin-right: 4px; white-space: nowrap; }
.send-box.is-disabled .send-label { color: var(--text-faint); }
.send-ic { width: 18px; height: 18px; object-fit: contain; }
</style>
