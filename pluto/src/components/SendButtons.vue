<script setup lang="ts">
// Send-to-node buttons: a labelled button box (UiButtonGroup) with one icon button per target
// node (its avatar, else its name). The Media drawer's per-ROM Send, extracted when the Homebrew
// tab became its second user. The caller decides what sending does; `busy` marks the node a
// send is running to. Renders nothing when there are no targets.
//   <SendButtons :targets="sendTargets" :disabled="running" @send="id => send(f, id)" />
import UiIconButton from './ui/UiIconButton.vue'
import UiButtonGroup from './ui/UiButtonGroup.vue'
import { ICONS } from '../composables/useIcons'

defineProps<{
  targets: { id: string; name: string }[]
  disabled?: boolean
  busy?: string | null
}>()
defineEmits<{ (e: 'send', id: string): void }>()
</script>

<template>
  <UiButtonGroup v-if="targets.length" label="Send to" :disabled="disabled">
    <UiIconButton
      v-for="t in targets" :key="t.id"
      variant="ghost" :title="'Send to ' + t.name"
      :disabled="disabled" :active="busy === t.id"
      @click="$emit('send', t.id)"
    >
      <img v-if="ICONS[t.id]" :src="ICONS[t.id]" class="send-ic" alt="" />
      <span v-else>{{ t.name }}</span>
    </UiIconButton>
  </UiButtonGroup>
</template>

<style scoped>
.send-ic { width: 18px; height: 18px; object-fit: contain; }
</style>
