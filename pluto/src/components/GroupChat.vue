<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import type { NodeMap, NodeData } from '../composables/useNodes'
import { ICONS } from '../composables/useIcons'
import { useMessages } from '../composables/useMessages'
import { readableBrand } from '../composables/useTheme'
import ConsoleAvatar from './ConsoleAvatar.vue'
import ChatComposer from './ChatComposer.vue'
import { formatMsg } from '../lib/chatFormat'

const props = defineProps<{
  nodes:       NodeMap
  showOffline: boolean
}>()

// ── Messages (live API) ──────────────────────────────────────────────────────
const { messages } = useMessages()


// ── Member lists — ordered: online → offline → unconfigured ──────────────────
const allNodes = computed(() => Object.values(props.nodes).filter(n => n.id !== 'gateway'))

const onlineMembers       = computed(() => allNodes.value.filter(n => n.status === 'up'))
const offlineMembers      = computed(() => allNodes.value.filter(n => n.status === 'down'))
const unconfiguredMembers = computed(() =>
  props.showOffline ? allNodes.value.filter(n => n.status === 'unconfigured') : []
)

// ── Message helpers ──────────────────────────────────────────────────────────
function nodeFor(id: string): NodeData | null {
  return props.nodes[id] ?? null
}

function iconFor(id: string): string | undefined {
  return ICONS[id] ?? ICONS[nodeFor(id)?.id ?? ''] ?? undefined
}

function displayName(id: string) {
  if (id === 'pluto') return 'Pluto C2'
  return props.nodes[id]?.name ?? id
}

function nameColor(id: string) {
  const node = nodeFor(id)
  if (node?.status === 'unconfigured') return 'var(--text-muted)'
  return readableBrand(node?.color ?? '#888884')
}

function formatTime(ts: string) {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
}

// Full date + time, for the timestamp's hover tooltip.
function formatFull(ts: string) {
  return new Date(ts).toLocaleString([], {
    weekday: 'short', year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: false,
  })
}

const sameDay = (a: Date, b: Date) =>
  a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()

// Friendly day label for a date divider: Today / Yesterday / "Mon, Jun 9"
// (with the year once it's not the current one).
function formatDay(ts: string) {
  const d = new Date(ts)
  const now = new Date()
  const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1)
  if (sameDay(d, now)) return 'Today'
  if (sameDay(d, yesterday)) return 'Yesterday'
  const opts: Intl.DateTimeFormatOptions = { weekday: 'short', month: 'short', day: 'numeric' }
  if (d.getFullYear() !== now.getFullYear()) opts.year = 'numeric'
  return d.toLocaleDateString([], opts)
}

// The date label to show ABOVE group `gi`, or null if it's the same calendar day
// as the previous group. Now that the feed survives restarts it can span days.
function dayDivider(gi: number): string | null {
  const groups = messageGroups.value
  const cur = groups[gi]?.messages[0]?.ts
  if (!cur) return null
  if (gi === 0) return formatDay(cur)
  const prevMsgs = groups[gi - 1]?.messages
  const prevTs = prevMsgs?.[prevMsgs.length - 1]?.ts
  if (prevTs && sameDay(new Date(prevTs), new Date(cur))) return null
  return formatDay(cur)
}


function isListMsg(text: string): boolean {
  const lines = text.split('\n')
  return lines.length > 1 && lines[0].endsWith(':') && lines[1].startsWith('  ')
}

function listHeader(text: string): string {
  return text.split('\n')[0]
}

function listItems(text: string): { name: string; meta: string }[] {
  return text.split('\n').slice(1).filter(l => l.trim()).map(l => {
    const s = l.trim()
    const i = s.indexOf('(')
    if (i < 0) return { name: s, meta: '' }
    return { name: s.slice(0, i).trimEnd(), meta: s.slice(i) }
  })
}

// Group consecutive messages from the same sender
interface MsgGroup {
  key:      number
  sender:   string
  node:     NodeData | null
  messages: { id: number; text: string; ts: string }[]
}

const messageGroups = computed<MsgGroup[]>(() => {
  const out: MsgGroup[] = []
  for (const m of messages.value) {
    const last = out[out.length - 1]
    if (last && last.sender === m.sender) {
      last.messages.push({ id: m.id, text: m.text, ts: m.ts })
    } else {
      out.push({ key: m.id, sender: m.sender, node: nodeFor(m.sender), messages: [{ id: m.id, text: m.text, ts: m.ts }] })
    }
  }
  return out
})

// ── Feed scroll ──────────────────────────────────────────────────────────────
const feedEl = ref<HTMLDivElement | null>(null)

function scrollToBottom() {
  nextTick(() => { if (feedEl.value) feedEl.value.scrollTop = feedEl.value.scrollHeight })
}
watch(messages, scrollToBottom, { deep: true })

</script>

<template>
  <div class="chat">
    <!-- Channel header + identity now live in the GLOBAL second header (App.vue). -->
    <div class="chat-body">

      <!-- Left sidebar: ordered online → offline → unconfigured -->
      <aside class="sidebar">
        <div v-if="onlineMembers.length > 0">
          <p class="sidebar-section">Online &mdash; {{ onlineMembers.length }}</p>
          <div v-for="n in onlineMembers" :key="n.id" class="member">
            <ConsoleAvatar :id="n.id" :icon="ICONS[n.id]" :status="n.status" :color="n.color" :size="36" />
            <span class="member-name" :style="{ color: readableBrand(n.color ?? 'var(--text)') }">
              {{ displayName(n.id) }}
            </span>
          </div>
        </div>

        <div v-if="offlineMembers.length > 0">
          <p class="sidebar-section sidebar-section--dim">Offline &mdash; {{ offlineMembers.length }}</p>
          <div v-for="n in offlineMembers" :key="n.id" class="member member--offline">
            <ConsoleAvatar :id="n.id" :icon="ICONS[n.id]" :status="n.status" :color="n.color" :size="36" />
            <span class="member-name member-name--dim">
              {{ displayName(n.id) }}
            </span>
          </div>
        </div>

        <div v-if="unconfiguredMembers.length > 0">
          <p class="sidebar-section sidebar-section--dim">Not present &mdash; {{ unconfiguredMembers.length }}</p>
          <div v-for="n in unconfiguredMembers" :key="n.id" class="member member--unconfigured">
            <ConsoleAvatar :id="n.id" :icon="ICONS[n.id]" :status="n.status" :color="n.color" :size="36" />
            <span class="member-name member-name--dim">
              {{ displayName(n.id) }}
            </span>
          </div>
        </div>
      </aside>

      <!-- Right: feed + input -->
      <div class="chat-col">
        <div ref="feedEl" class="feed">
          <template v-for="(g, gi) in messageGroups" :key="g.key">
            <div v-if="dayDivider(gi)" class="day-divider">
              <span class="day-divider-label">{{ dayDivider(gi) }}</span>
            </div>
            <div class="msg-group">
            <ConsoleAvatar
              :id="g.sender"
              :icon="iconFor(g.sender)"
              :status="g.node?.status ?? 'up'"
              :color="g.node?.color"
              :size="38"
              class="msg-avatar"
            />
            <div class="msg-content">
              <div class="msg-meta">
                <span class="msg-name" :style="{ color: nameColor(g.sender) }">
                  {{ displayName(g.sender) }}
                </span>
                <span class="msg-time" :title="formatFull(g.messages[0].ts)">{{ formatTime(g.messages[0].ts) }}</span>
              </div>
              <template v-for="m in g.messages" :key="m.id">
                <div v-if="isListMsg(m.text)" class="msg-list">
                  <span class="msg-list-header">{{ listHeader(m.text) }}</span>
                  <span v-for="(item, i) in listItems(m.text)" :key="i" class="msg-list-item">
                    <span class="msg-list-name">{{ item.name }}</span><span class="msg-list-meta">{{ item.meta }}</span>
                  </span>
                </div>
                <p v-else class="msg-text">
                  <template v-for="(seg, si) in formatMsg(m.text)" :key="si">
                    <strong v-if="seg.mention" class="msg-mention">{{ seg.text }}</strong><a v-else-if="seg.url" :href="seg.text" target="_blank" rel="noopener noreferrer" class="msg-link">{{ seg.text }}</a><span v-else>{{ seg.text }}</span>
                  </template>
                </p>
              </template>
            </div>
            </div>
          </template>

          <div v-if="messageGroups.length === 0" class="feed-empty">
            No messages yet &mdash; say something
          </div>
        </div>

        <ChatComposer :nodes="nodes" @sent="scrollToBottom" />
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── Shell ───────────────────────────────────────────────────── */
.chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--surface);
  color: var(--text);
  font-family: var(--font-sans);
  overflow: hidden;
}

.chat-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* ── Sidebar ─────────────────────────────────────────────────── */
.sidebar {
  width: 196px;
  flex-shrink: 0;
  border-right: 1px solid var(--line);
  background: var(--surface-2);
  overflow-y: auto;
  padding: 14px 0;
}

.sidebar::-webkit-scrollbar       { width: 4px; }
.sidebar::-webkit-scrollbar-thumb { background: var(--line); border-radius: 2px; }

.sidebar-section {
  font-family: var(--font-sans);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.12em;
  color: var(--text-muted);
  padding: 10px 14px 6px;
}
.sidebar-section--dim { opacity: 0.6; margin-top: 4px; }

.member {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 14px;
  border-radius: 4px;
  cursor: default;
  transition: background 0.12s;
}
.member:hover             { background: var(--surface-3); }
.member--offline          { opacity: 0.5; }
.member--unconfigured     { opacity: 0.28; }

.member-name {
  font-family: var(--font-sans);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  filter: brightness(0.78);
}
.member-name--dim {
  color: var(--text-muted) !important;
  filter: none;
}

/* ── Chat column ─────────────────────────────────────────────── */
.chat-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

/* (Channel header + identity moved to the global second header in App.vue.) */

/* ── Feed ────────────────────────────────────────────────────── */
.feed {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  scroll-behavior: smooth;
}

.feed::-webkit-scrollbar       { width: 6px; }
.feed::-webkit-scrollbar-thumb { background: var(--line); border-radius: 3px; }

.msg-group {
  display: flex;
  gap: 14px;
  padding: 7px 0;
}

/* date separator between days — a hairline rule with a centred day label */
.day-divider {
  display: flex;
  align-items: center;
  margin: 14px 0 6px;
}
.day-divider::before,
.day-divider::after {
  content: "";
  flex: 1;
  height: 1px;
  background: var(--line);
}
.day-divider-label {
  padding: 0 12px;
  font-family: var(--font-sans);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--text-muted);
  white-space: nowrap;
}
.msg-avatar  { flex-shrink: 0; margin-top: 2px; }

.msg-content { flex: 1; min-width: 0; }

.msg-meta {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 3px;
}

.msg-name {
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.04em;
  filter: brightness(0.78);
}

.msg-time {
  font-family: var(--font-sans);
  font-size: 10px;
  color: var(--text-muted);
  letter-spacing: 0.06em;
  opacity: 0.65;
}

.msg-text {
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text);
  line-height: 1.6;
  word-break: break-word;
  margin: 0;
  white-space: pre-wrap;
}

.msg-mention {
  font-weight: 700;
  letter-spacing: 0.02em;
}

.msg-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  margin: 0;
}

.msg-list-header {
  font-family: var(--font-sans);
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.07em;
  margin-bottom: 5px;
}

.msg-list-item {
  font-size: 12px;
  line-height: 1.55;
}

.msg-list-name {
  font-family: var(--font-mono);
  color: var(--text);
}

.msg-list-meta {
  font-family: var(--font-sans);
  color: var(--text-muted);
  margin-left: 4px;
}


.feed-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-sans);
  font-size: 12px;
  letter-spacing: 0.1em;
  color: var(--text-muted);
  opacity: 0.5;
}

/* ── Responsive ──────────────────────────────────────────────── */
@media (max-width: 620px) {
  .sidebar { display: none; }
}
</style>
