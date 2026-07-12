<script setup lang="ts">
// Reusable feed panel: scrollable log of named/coloured lines + optional coaching
// input row. Used by ClaudeControl (Guide Dog channel) and GoogleLensControl
// (Vision scan results). The caller owns the data; the component owns the scroll
// and the layout.
import { ref, watch, nextTick } from 'vue'
import UiButton from '../ui/UiButton.vue'

export interface FeedLine {
  role?:  string
  state:  string
}

const props = defineProps<{
  title:          string
  lines:          FeedLine[]
  emptyText?:     string
  roleColors?:    Record<string, string>  // role -> css color
  myName?:        string                  // label for the 'operator' role (default 'You')
  showInput?:     boolean                 // show text input + send + thumbs (default true)
  placeholder?:   string
}>()

const emit = defineEmits<{
  send:  [string]
  quick: [string]
}>()

const feedEl = ref<HTMLElement | null>(null)
const cmd    = ref('')

function lineName(l: FeedLine) {
  const r = l.role ?? ''
  if (r === 'operator') return props.myName ?? 'You'
  return r
}
function lineColor(l: FeedLine) {
  const r = l.role ?? ''
  return props.roleColors?.[r] ?? 'var(--text-muted)'
}

function sendCmd() {
  const v = cmd.value.trim()
  if (!v) return
  cmd.value = ''
  emit('send', v)
}

// Auto-scroll to bottom when lines change.
watch(() => props.lines, async () => {
  await nextTick()
  if (feedEl.value) feedEl.value.scrollTop = feedEl.value.scrollHeight
}, { deep: true })
</script>

<template>
  <div class="cf">
    <div class="cf-head">
      <span class="cf-title">{{ title }}</span>
      <slot name="header-actions" />
    </div>

    <div ref="feedEl" class="cf-feed">
      <p v-for="(line, i) in lines" :key="i" class="cf-line">
        <span v-if="lineName(line)" class="cf-name" :style="{ color: lineColor(line) }">{{ lineName(line) }}</span><span v-if="lineName(line)">: </span>{{ line.state }}
      </p>
      <div v-if="lines.length === 0" class="cf-empty">
        {{ emptyText ?? 'Nothing here yet.' }}
      </div>
    </div>

    <div v-if="showInput !== false" class="cf-input-wrap">
      <button class="cf-thumb" @click="emit('quick', 'yes')" title="Yes">👍</button>
      <button class="cf-thumb" @click="emit('quick', 'no')"  title="No">👎</button>
      <input class="cf-input" v-model="cmd"
             :placeholder="placeholder ?? 'Type a message…'"
             @keydown.enter="sendCmd" />
      <UiButton variant="primary" class="cf-send" :disabled="!cmd.trim()" @click="sendCmd">Send</UiButton>
    </div>

    <slot name="footer" />
  </div>
</template>

<style scoped>
.cf {
  display: flex; flex-direction: column;
  height: 100%; min-height: 0; background: var(--surface);
  font-family: var(--font-sans);
}
.cf-head {
  display: flex; align-items: center; justify-content: space-between; flex: 0 0 auto;
  padding: var(--sp-3) var(--sp-4); border-bottom: 1px solid var(--line);
}
.cf-title { font-size: 13px; font-weight: 600; color: var(--text); }

.cf-feed {
  flex: 1 1 0; min-height: 0; overflow-y: auto;
  padding: 14px 16px 10px; display: flex; flex-direction: column; gap: 3px;
  scroll-behavior: smooth; background: var(--surface);
}
.cf-empty { margin: auto; color: var(--text-muted); font-size: 13px; text-align: center; line-height: 1.6; max-width: 80%; }
.cf-line  { font-size: 13px; line-height: 1.6; color: var(--text); margin: 0; white-space: pre-wrap; }
.cf-name  { font-weight: 700; }

.cf-input-wrap {
  display: flex; align-items: center; gap: var(--sp-2); flex: 0 0 auto;
  padding: var(--sp-3) var(--sp-4); border-top: 1px solid var(--line);
  background: var(--surface);
}
.cf-input {
  flex: 1 1 auto; min-width: 0; font-family: var(--font-sans); font-size: 13px;
  color: var(--text); padding: 8px 12px; border: 1px solid var(--line-strong);
  border-radius: var(--r-sm); background: var(--surface-2);
}
.cf-input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.cf-input::placeholder { color: var(--text-faint); }
/* layout only — the terracotta look now comes from UiButton */
.cf-send { flex: 0 0 auto; }
.cf-thumb {
  flex: 0 0 auto; font-size: 18px; line-height: 1; padding: 6px 8px;
  border: 1px solid var(--line-strong); border-radius: var(--r-sm);
  background: var(--surface-3); cursor: pointer; transition: background 0.1s;
}
.cf-thumb:hover { background: var(--line-strong); }
</style>
