<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { NodeMap } from '../composables/useNodes'
import { ICONS } from '../composables/useIcons'
import { useMessages } from '../composables/useMessages'
import { readableBrand } from '../composables/useTheme'
import { formatMsg } from '../lib/chatFormat'
import ChatComposer from './ChatComposer.vue'

// The mini chat: a small floating dock on every tab (think Gmail's chat), grown out of the
// old Recent Activity tail. Minimized it's just a bar with an unread count; open it shows
// the latest messages and the shared composer (@mention -> verb -> target). Expand opens
// the full chat as an overlay. Replaces the Command tab.
const props = defineProps<{ nodes: NodeMap; unread: number }>()
const emit = defineEmits<{ expand: []; seen: [] }>()

const { messages } = useMessages()

// Open/minimized is a per-viewer convenience (cpc.<domain>.<leaf> key convention).
const KEY = 'cpc.chat.dockOpen'
const open = ref((() => { try { return localStorage.getItem(KEY) !== '0' } catch { return true } })())
function setOpen(v: boolean) {
  open.value = v
  try { localStorage.setItem(KEY, v ? '1' : '0') } catch { /* ignore */ }
  if (v) { emit('seen'); scrollDown(); composer.value?.focus() }
}

const recent = computed(() => messages.value.slice(-40))
const listEl = ref<HTMLElement | null>(null)
const composer = ref<InstanceType<typeof ChatComposer> | null>(null)
function scrollDown() { nextTick(() => { if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight }) }

// New message: scroll + mark seen while open; a soft ping either way so a reply to a
// fire-and-forget action (Sync, Deploy) isn't missed down here.
const pinged = ref(false)
let pingTimer: ReturnType<typeof setTimeout> | undefined
watch(() => messages.value[messages.value.length - 1]?.id, (id, prev) => {
  if (id === undefined) return
  if (open.value) { scrollDown(); emit('seen') }
  if (prev === undefined || id <= prev) return
  pinged.value = true
  clearTimeout(pingTimer)
  pingTimer = setTimeout(() => { pinged.value = false }, 1400)
}, { immediate: true })

function name(id: string) { return id === 'pluto' ? 'Pluto C2' : (props.nodes[id]?.name ?? id) }
function color(id: string) { return readableBrand(props.nodes[id]?.color ?? '#888884') }
function time(ts: string) { return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false }) }
// Consecutive messages from one sender show the name once.
const showHead = (i: number) => i === 0 || recent.value[i - 1].sender !== recent.value[i].sender
</script>

<template>
  <div class="mc" :class="{ 'mc--open': open, 'mc--ping': pinged }" @click.stop>
    <header class="mc__head" @click="setOpen(!open)">
      <span class="mc__title">Chat</span>
      <span v-if="!open && unread > 0" class="mc__badge">{{ unread }}</span>
      <span v-if="!open && recent.length" class="mc__peek">
        <strong>{{ name(recent[recent.length - 1].sender) }}:</strong> {{ recent[recent.length - 1].text }}
      </span>
      <span class="mc__btns">
        <button class="mc__btn" title="Open full chat" @click.stop="emit('expand')">
          <svg width="13" height="13" viewBox="0 0 16 16" aria-hidden="true"><path d="M9.5 2.5h4v4M13.5 2.5l-5 5M6.5 13.5h-4v-4M2.5 13.5l5-5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
        <button class="mc__btn" :title="open ? 'Minimize' : 'Open'" @click.stop="setOpen(!open)">
          <svg width="13" height="13" viewBox="0 0 16 16" aria-hidden="true" :style="{ transform: open ? 'none' : 'rotate(180deg)' }"><path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
      </span>
    </header>

    <template v-if="open">
      <ul ref="listEl" class="mc__list">
        <li v-for="(m, i) in recent" :key="m.id" class="mc__msg" :class="{ 'mc__msg--head': showHead(i) }">
          <img v-if="showHead(i) && ICONS[m.sender]" :src="ICONS[m.sender]" class="mc__av" alt="" />
          <span v-else-if="showHead(i)" class="mc__av mc__av--none">{{ name(m.sender).slice(0, 1) }}</span>
          <div class="mc__body">
            <div v-if="showHead(i)" class="mc__meta">
              <span class="mc__name" :style="{ color: color(m.sender) }">{{ name(m.sender) }}</span>
              <span class="mc__time">{{ time(m.ts) }}</span>
            </div>
            <p class="mc__text"><template v-for="(seg, si) in formatMsg(m.text)" :key="si"><strong v-if="seg.mention" class="mc__mention">{{ seg.text }}</strong><a v-else-if="seg.url" :href="seg.text" target="_blank" rel="noopener noreferrer">{{ seg.text }}</a><span v-else>{{ seg.text }}</span></template></p>
          </div>
        </li>
        <li v-if="!recent.length" class="mc__empty">No messages yet</li>
      </ul>
      <ChatComposer ref="composer" :nodes="nodes" compact @sent="scrollDown" />
    </template>
  </div>
</template>

<style scoped>
/* Bottom-left dock on every tab. Quiet glass like the zoom controls: docked flush
   when collapsed, floating when open. */
.mc {
  position: absolute; left: 16px; bottom: 16px; z-index: 5;
  width: min(380px, calc(100vw - 32px));
  display: flex; flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  box-shadow: 0 10px 30px rgba(26, 34, 51, 0.16);
  font-family: var(--font-sans);
  overflow: hidden;
}
.mc--open { height: min(460px, calc(100% - 32px)); }
/* Collapsed it is a docked bar, not a floating card: flush into the bottom-left
   corner, no gap and no shadow, so it stops reading as something hovering over
   the quad underneath it (the SW quad is bottom-left too). Open, it lifts back
   off the edge and floats as before. */
.mc:not(.mc--open) {
  left: 0; bottom: 0;
  border-left: 0; border-bottom: 0;
  border-radius: 0 var(--r-lg) 0 0;
  box-shadow: none;
}
.mc--ping { animation: mc-ping 1.4s ease-out; }
@keyframes mc-ping {
  0%   { border-color: var(--accent); box-shadow: 0 10px 30px rgba(26, 34, 51, 0.16), 0 0 0 3px var(--accent-soft); }
  100% { border-color: var(--line);   box-shadow: 0 10px 30px rgba(26, 34, 51, 0.16), 0 0 0 0 transparent; }
}
@media (prefers-reduced-motion: reduce) { .mc--ping { animation: none; } }

.mc__head { display: flex; align-items: center; gap: 8px; padding: 8px 8px 8px 12px; cursor: pointer; background: var(--surface-2); border-bottom: 1px solid var(--line); min-width: 0; }
.mc:not(.mc--open) .mc__head { border-bottom: 0; }
.mc__title { font-size: 13px; font-weight: 600; color: var(--text); flex: none; }
.mc__badge { flex: none; min-width: 18px; padding: 0 5px; border-radius: 999px; background: var(--accent); color: var(--accent-ink); font-size: 11px; font-weight: 700; line-height: 18px; text-align: center; }
.mc__peek { flex: 1 1 auto; min-width: 0; font-size: 12px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mc__peek strong { color: var(--text); font-weight: 600; }
.mc__btns { display: flex; gap: 2px; margin-left: auto; flex: none; }
.mc__btn { display: flex; align-items: center; justify-content: center; width: 24px; height: 24px; padding: 0; color: var(--text-muted); background: transparent; border: 0; border-radius: 6px; cursor: pointer; }
.mc__btn:hover { color: var(--accent); background: var(--surface-3); }

.mc__list { flex: 1; min-height: 0; overflow-y: auto; margin: 0; padding: 8px 12px; list-style: none; display: flex; flex-direction: column; gap: 2px; }
.mc__msg { display: flex; gap: 8px; padding-left: 30px; }
.mc__msg--head { padding-left: 0; margin-top: 8px; }
.mc__msg--head:first-child { margin-top: 0; }
.mc__av { width: 22px; height: 22px; object-fit: contain; flex: none; margin-top: 1px; }
.mc__av--none { display: flex; align-items: center; justify-content: center; border-radius: 50%; background: var(--surface-3); color: var(--text-muted); font-size: 11px; font-weight: 600; }
.mc__body { min-width: 0; flex: 1; }
.mc__meta { display: flex; align-items: baseline; gap: 6px; }
.mc__name { font-size: 12px; font-weight: 600; }
.mc__time { font-size: 10.5px; color: var(--text-faint); }
.mc__text { margin: 0; font-size: 12.5px; line-height: 1.4; color: var(--text); white-space: pre-wrap; word-break: break-word; }
.mc__mention { color: var(--accent); font-weight: 600; }
.mc__text a { color: var(--accent); text-decoration: underline; word-break: break-all; }
.mc__empty { margin: auto; font-size: 12px; color: var(--text-faint); }
</style>
