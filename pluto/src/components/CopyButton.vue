<script setup lang="ts">
// Reusable copy-to-clipboard button. IDs (chip ids, session ids, ...) are a common
// thing to copy, so this is the one affordance for all of them. @click.stop so it
// never triggers a row/card selection it sits inside.
import { ref } from 'vue'

const props = defineProps<{ text: string; title?: string }>()
const copied = ref(false)
let t = 0
function copy() {
  navigator.clipboard?.writeText(props.text).then(() => {
    copied.value = true
    if (t) clearTimeout(t)
    t = window.setTimeout(() => { copied.value = false }, 1200)
  }).catch(() => { /* clipboard unavailable */ })
}
</script>

<template>
  <button class="copy-btn" :title="title || ('Copy\n' + text)" @click.stop="copy">
    <svg v-if="!copied" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
    <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>
  </button>
</template>

<style scoped>
.copy-btn { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; padding: 0; color: var(--text-faint); background: transparent; border: none; border-radius: 5px; cursor: pointer; flex: 0 0 auto; }
.copy-btn:hover { color: var(--accent); background: var(--accent-soft); }
</style>
