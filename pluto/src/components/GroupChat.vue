<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import type { NodeMap, NodeData } from '../composables/useNodes'
import { ICONS } from '../composables/useIcons'
import { useMessages } from '../composables/useMessages'
import { useIdentity } from '../composables/useIdentity'
import ConsoleAvatar from './ConsoleAvatar.vue'
import chatConfig from '../../config/chat.json'

const props = defineProps<{
  nodes:       NodeMap
  showOffline: boolean
}>()

// ── Messages (live API) ──────────────────────────────────────────────────────
const { messages, sendMessage } = useMessages()

// ── Identity: who you are — shared with the global header (which shows/edits it),
// so the chat sends as exactly what the header displays. See useIdentity. ──
const { meNode, guestName, isGuest, identity } = useIdentity()
const identityLabel = computed(() => meNode.value ? displayName(meNode.value) : guestName.value)

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
  return node?.color ?? '#888884'
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

type MsgSeg = { mention?: boolean; url?: boolean; text: string }

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

function formatMsg(text: string): MsgSeg[] {
  return text.split(/(https?:\/\/[^\s<>"]+|@\w+)/g).map((part, i) => {
    if (i % 2 === 1) {
      if (/^https?:\/\//.test(part)) return { url: true, text: part }
      return { mention: true, text: part }
    }
    return { text: part }
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

// ── Mentions & node actions ──────────────────────────────────────────────────
// One model: every node is taggable (@handle). Tagging reveals the node's actions
// as an explicit verb substep (consequential actions are never auto-fired); a node
// with no actions is a plain mention, and claude is conversational. From the shared
// chat.json (api.py reads the same file, so client + server agree).
interface ActionDef {
  verb:       string
  desc:       string
  target?:    string    // 'console' -> a second tag (a console, or @everyone)
  multiline?: boolean
}
const NODE_ACTIONS: Record<string, ActionDef[]> = chatConfig.nodeActions ?? {}
const HANDLES: Record<string, string> = chatConfig.mentions.handles ?? {}

// gateway/cloud are virtual infra, not chat participants.
const taggableIds = computed(() =>
  Object.keys(props.nodes).filter(id => id !== 'gateway' && id !== 'cloud')
)
// @handle for a node (default = its key; chat.json overrides, e.g. dreame -> l40).
function handleFor(id: string): string { return HANDLES[id] ?? id }
const nodeByHandle = computed<Record<string, string>>(() => {
  const m: Record<string, string> = {}
  for (const id of taggableIds.value) m['@' + handleFor(id)] = id
  return m
})

// ── Input state ──────────────────────────────────────────────────────────────
const draft       = ref('')
const inputEl     = ref<HTMLInputElement | null>(null)
const textareaEl  = ref<HTMLTextAreaElement | null>(null)
const hlEl        = ref<HTMLDivElement | null>(null)
const showEmoji   = ref(false)

// Keep the bold-mention highlight layer scrolled in lockstep with the input as
// the caret moves past the visible edge (monospace makes the metrics line up).
function syncScroll() {
  if (hlEl.value && inputEl.value) hlEl.value.scrollLeft = inputEl.value.scrollLeft
}

const EMOJIS = chatConfig.emojis

function insertEmoji(e: string) {
  draft.value += e
  showEmoji.value = false
  nextTick(() => (inputEl.value ?? textareaEl.value)?.focus())
}

// Parse the draft into tokens: [ @handle, verb, target, ... ]
const draftParts = computed(() => draft.value.split(' '))

// The tagged node: token 0 is a completed @handle that resolves to a node.
const taggedNode = computed(() =>
  nodeByHandle.value[(draftParts.value[0] ?? '').toLowerCase()] ?? null
)
const taggedActions = computed<ActionDef[]>(() =>
  taggedNode.value ? (NODE_ACTIONS[taggedNode.value] ?? []) : []
)
// The resolved action: token 1 matches one of the tagged node's verbs.
const resolvedAction = computed<ActionDef | null>(() =>
  taggedActions.value.find(a => a.verb === draftParts.value[1]) ?? null
)

// (1) Mention menu — typing the @handle at token 0. Every node is taggable.
const showMentionMenu = computed(() =>
  draftParts.value.length === 1 && draft.value.startsWith('@')
)
const mentionList = computed(() => [
  ...chatConfig.mentions.base,
  ...taggableIds.value.map(id => '@' + handleFor(id)),
])
const filteredMentions = computed(() => {
  const t = (draftParts.value[0] ?? '').toLowerCase()
  return mentionList.value.filter(m => m.toLowerCase().startsWith(t))
})
function selectMention(m: string) {
  // Trailing space so a node-with-actions immediately reveals its verb substep.
  draft.value = m + ' '
  nextTick(() => (inputEl.value ?? textareaEl.value)?.focus())
}

// (2) Action menu — the tagged node's verbs, after "@handle ".
const showActionMenu = computed(() =>
  !!taggedNode.value && taggedActions.value.length > 0 &&
  draftParts.value.length === 2 && !showMentionMenu.value
)
const actionCandidates = computed(() => {
  if (!showActionMenu.value) return []
  const t = (draftParts.value[1] ?? '').toLowerCase()
  return taggedActions.value.filter(a => a.verb.startsWith(t))
})
function pickAction(verb: string) {
  draft.value = `${draftParts.value[0]} ${verb} `
  nextTick(() => (inputEl.value ?? textareaEl.value)?.focus())
}

// (3) Target menu — a console (or @everyone) for an action that takes one.
const showTargetMenu = computed(() =>
  resolvedAction.value?.target === 'console' && draftParts.value.length >= 3
)
const targetOptions = computed(() => [
  '@everyone',
  ...taggableIds.value
    // local consoles only: not cloud connectors (the `cloud` flag holds even when
    // an unconfigured connector reads status 'unconfigured'), and not the host.
    .filter(id => !props.nodes[id]?.cloud && id !== 'pluto')
    .map(id => '@' + handleFor(id)),
])
const targetCandidates = computed(() => {
  if (!showTargetMenu.value) return []
  const t = (draftParts.value[2] ?? '').toLowerCase()
  return t ? targetOptions.value.filter(o => o.toLowerCase().startsWith(t)) : targetOptions.value
})
function pickTarget(tok: string) {
  draft.value = `${draftParts.value[0]} ${draftParts.value[1]} ${tok}`
  nextTick(() => (inputEl.value ?? textareaEl.value)?.focus())
}

// ── Unified autocomplete navigation ──────────────────────────────────────────
// Whichever menu is open exposes a flat list of selectable values plus an apply
// fn, so arrow-key nav and tab/enter-to-complete work the same everywhere. This
// is what stops a half-typed "@cla" from being sent on Enter.
interface Suggest { items: string[]; apply: (v: string) => void }

const highlight = ref(0)

const activeSuggest = computed<Suggest | null>(() => {
  if (showMentionMenu.value && filteredMentions.value.length)
    return { items: filteredMentions.value, apply: selectMention }
  if (showActionMenu.value && actionCandidates.value.length)
    return { items: actionCandidates.value.map(a => a.verb), apply: pickAction }
  if (showTargetMenu.value && targetCandidates.value.length)
    return { items: targetCandidates.value, apply: pickTarget }
  return null
})

// Reset to the top whenever the suggestion list itself changes (new filter).
watch(() => activeSuggest.value?.items.join('') ?? '', () => { highlight.value = 0 })

function clampedHl() {
  const s = activeSuggest.value
  if (!s) return -1
  return Math.min(Math.max(highlight.value, 0), s.items.length - 1)
}
function isHl(val: string) {
  const s = activeSuggest.value
  return !!s && s.items[clampedHl()] === val
}
function setHl(val: string) {
  const s = activeSuggest.value
  if (s) highlight.value = Math.max(0, s.items.indexOf(val))
}
function applyHighlighted(): boolean {
  const s = activeSuggest.value
  if (!s) return false
  s.apply(s.items[clampedHl()])
  return true
}

// Multiline when the resolved action asks for it (e.g. substack post).
const isMultiline = computed(() => resolvedAction.value?.multiline === true)

// ── Send ─────────────────────────────────────────────────────────────────────
function send() {
  const text = draft.value.trim()
  if (!text) return
  sendMessage(identity.value, text)
  draft.value = ''
  showEmoji.value = false
  scrollToBottom()
}



function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') { showEmoji.value = false; return }

  // When an autocomplete menu is open, arrows navigate and Tab/Enter complete
  // the highlighted item instead of sending — so "@cla" + Enter resolves to
  // "@claude " rather than firing a half-typed mention.
  const s = activeSuggest.value
  if (s) {
    const n = s.items.length
    if (e.key === 'ArrowDown') { e.preventDefault(); highlight.value = (clampedHl() + 1) % n; return }
    if (e.key === 'ArrowUp')   { e.preventDefault(); highlight.value = (clampedHl() - 1 + n) % n; return }
    if (e.key === 'Tab')                   { e.preventDefault(); applyHighlighted(); return }
    if (e.key === 'Enter' && !e.shiftKey)  {
      e.preventDefault()
      // If the draft is already the completed value (e.g. "@l40 status"), applying
      // is a no-op — that means the user is done, so send instead of re-completing.
      const before = draft.value
      applyHighlighted()
      if (draft.value === before) send()
      return
    }
  }

  // Textarea in multiline mode: Enter sends, Shift+Enter inserts newline
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
}
</script>

<template>
  <div class="chat" @click="showEmoji = false">
    <!-- Channel header + identity now live in the GLOBAL second header (App.vue). -->
    <div class="chat-body">

      <!-- Left sidebar: ordered online → offline → unconfigured -->
      <aside class="sidebar">
        <div v-if="onlineMembers.length > 0">
          <p class="sidebar-section">Online &mdash; {{ onlineMembers.length }}</p>
          <div v-for="n in onlineMembers" :key="n.id" class="member">
            <ConsoleAvatar :id="n.id" :icon="ICONS[n.id]" :status="n.status" :color="n.color" :size="36" />
            <span class="member-name" :style="{ color: n.color ?? 'var(--text)' }">
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

        <!-- Input area -->
        <div class="input-wrap" @click.stop>

          <!-- (1) Mention autocomplete: tag any node (+ @here/@everyone) -->
          <div v-if="showMentionMenu && filteredMentions.length > 0" class="autocomplete">
            <div
              v-for="m in filteredMentions"
              :key="m"
              class="autocomplete-item"
              :class="{ 'autocomplete-item--active': isHl(m) }"
              @mouseenter="setHl(m)"
              @click="selectMention(m)"
            >
              <ConsoleAvatar
                v-if="nodeByHandle[m.toLowerCase()]"
                :id="nodeByHandle[m.toLowerCase()]"
                :icon="ICONS[nodeByHandle[m.toLowerCase()]]"
                :status="nodes[nodeByHandle[m.toLowerCase()]]?.status ?? 'unconfigured'"
                :color="nodes[nodeByHandle[m.toLowerCase()]]?.color"
                :size="20"
              />
              <span class="autocomplete-cmd">{{ m }}</span>
            </div>
          </div>

          <!-- (2) Action substep: the tagged node's verbs -->
          <div v-if="showActionMenu && actionCandidates.length > 0" class="autocomplete">
            <div
              v-for="a in actionCandidates"
              :key="a.verb"
              class="autocomplete-item"
              :class="{ 'autocomplete-item--active': isHl(a.verb) }"
              @mouseenter="setHl(a.verb)"
              @click="pickAction(a.verb)"
            >
              <span class="autocomplete-cmd">{{ a.verb }}</span>
              <span v-if="a.target" class="autocomplete-param">&lt;{{ a.target }}&gt;</span>
              <span class="autocomplete-desc">{{ a.desc }}</span>
              <span v-if="a.multiline" class="autocomplete-tag">multiline</span>
            </div>
          </div>

          <!-- (3) Target substep: a console (or @everyone) for actions that take one -->
          <div v-if="showTargetMenu && targetCandidates.length > 0" class="autocomplete">
            <div
              v-for="t in targetCandidates"
              :key="t"
              class="autocomplete-item"
              :class="{ 'autocomplete-item--active': isHl(t) }"
              @mouseenter="setHl(t)"
              @click="pickTarget(t)"
            >
              <ConsoleAvatar
                v-if="t !== '@everyone' && nodeByHandle[t.toLowerCase()]"
                :id="nodeByHandle[t.toLowerCase()]"
                :icon="ICONS[nodeByHandle[t.toLowerCase()]]"
                :status="nodes[nodeByHandle[t.toLowerCase()]]?.status ?? 'unconfigured'"
                :color="nodes[nodeByHandle[t.toLowerCase()]]?.color"
                :size="20"
              />
              <span class="autocomplete-cmd">{{ t }}</span>
            </div>
          </div>

          <!-- Emoji picker -->
          <div v-if="showEmoji" class="emoji-picker">
            <button
              v-for="e in EMOJIS"
              :key="e"
              class="emoji-btn"
              @click.stop="insertEmoji(e)"
            >{{ e }}</button>
          </div>

          <div class="input-bar">
            <div v-if="isGuest" class="guest-avatar" :title="'Posting as ' + guestName">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="var(--accent)" shape-rendering="crispEdges">
                <rect x="5"  y="4"  width="2"  height="2"/><rect x="17" y="4"  width="2"  height="2"/>
                <rect x="7"  y="6"  width="2"  height="2"/><rect x="15" y="6"  width="2"  height="2"/>
                <rect x="5"  y="8"  width="14" height="2"/>
                <rect x="3"  y="10" width="4"  height="2"/><rect x="9"  y="10" width="6" height="2"/><rect x="17" y="10" width="4" height="2"/>
                <rect x="1"  y="12" width="22" height="2"/>
                <rect x="1"  y="14" width="2"  height="2"/><rect x="5"  y="14" width="14" height="2"/><rect x="21" y="14" width="2" height="2"/>
                <rect x="1"  y="16" width="2"  height="2"/><rect x="5"  y="16" width="2" height="2"/><rect x="17" y="16" width="2" height="2"/><rect x="21" y="16" width="2" height="2"/>
                <rect x="7"  y="18" width="4"  height="2"/><rect x="13" y="18" width="4" height="2"/>
              </svg>
            </div>
            <ConsoleAvatar
              v-else
              :id="meNode!"
              :icon="iconFor(meNode!)"
              :status="nodeFor(meNode!)?.status ?? 'up'"
              :color="nodeFor(meNode!)?.color"
              :size="36"
            />

            <div class="input-field-wrap">
              <textarea
                v-if="isMultiline"
                ref="textareaEl"
                v-model="draft"
                class="input-field input-field--textarea"
                placeholder="Write your post…  (shift+enter for new line)"
                maxlength="2000"
                rows="3"
                @keydown="onKeydown"
              />
              <div v-else class="input-overlay-box">
                <div ref="hlEl" class="input-hl" aria-hidden="true">
                  <span class="input-hl-text"><template
                    v-for="(seg, si) in formatMsg(draft)"
                    :key="si"
                  ><strong v-if="seg.mention">{{ seg.text }}</strong><a v-else-if="seg.url" :href="seg.text" target="_blank" rel="noopener noreferrer" class="msg-link">{{ seg.text }}</a><span v-else>{{ seg.text }}</span></template></span>
                </div>
                <input
                  ref="inputEl"
                  v-model="draft"
                  class="input-field input-field--overlay"
                  :placeholder="'Message as ' + identityLabel + '…  (@ to tag a node)'"
                  maxlength="500"
                  @keydown="onKeydown"
                  @input="syncScroll"
                  @scroll="syncScroll"
                />
              </div>
            </div>

            <button
              class="emoji-toggle"
              :class="{ 'emoji-toggle--active': showEmoji }"
              title="Emoji"
              @click.stop="showEmoji = !showEmoji"
            >&#x1F3AE;</button>

            <button
              class="send-btn"
              :disabled="!draft.trim()"
              title="send"
              @click="send"
            >
              Send
            </button>
          </div>
        </div>
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

/* Guest sender avatar — a monogram, no console icon to borrow */
.guest-avatar {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border-radius: 50%;
  border: 2px solid var(--accent);
  background: var(--accent-soft);
  color: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-sans);
  font-size: 15px;
  font-weight: 700;
}

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

.msg-link {
  color: var(--accent);
  text-decoration: underline;
  text-underline-offset: 2px;
  word-break: break-all;
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

/* ── Input area ──────────────────────────────────────────────── */
.input-wrap {
  position: relative;
  flex-shrink: 0;
  border-top: 1px solid var(--line);
  background: var(--surface-2);
}

.input-bar {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 10px 16px 12px;
}

.input-field-wrap { flex: 1; min-width: 0; }

.input-field {
  width: 100%;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-sm);
  padding: 9px 12px;
  /* monospace stays: the @mention highlight overlay aligns char-for-char,
     and bold mentions only stay aligned in a fixed-width font */
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text);
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
  display: block;
}
.input-field--textarea {
  resize: vertical;
  min-height: 60px;
  max-height: 200px;
  line-height: 1.5;
}

/* ── Mention highlight overlay (single-line input) ─────────────── */
.input-overlay-box { position: relative; }

/* The input sits on top with transparent text; the highlight layer behind
   renders the same characters, bolding @mentions. Monospace keeps them aligned. */
.input-field--overlay {
  position: relative;
  z-index: 1;
  background: transparent;
  color: transparent;
  caret-color: var(--text);
}
.input-hl {
  position: absolute;
  inset: 0;
  z-index: 0;
  display: flex;
  align-items: center;
  padding: 9px 12px;
  border: 1px solid transparent;   /* match input border box for alignment */
  border-radius: var(--r-sm);
  box-sizing: border-box;
  overflow: hidden;
  pointer-events: none;
  background: var(--surface-2);             /* recessed fill behind the transparent input */
  font-family: var(--font-mono);            /* must match .input-field for char alignment */
  font-size: 13px;
  color: var(--text);
}
.input-hl-text { white-space: pre; }
.input-hl-text strong { font-weight: 700; color: var(--accent); }
.input-field::placeholder { color: var(--text-faint); }
.input-field:focus        { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }

.emoji-toggle {
  font-size: 18px;
  line-height: 1;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  padding: 6px;
  cursor: pointer;
  transition: background 0.14s, border-color 0.14s;
  flex-shrink: 0;
  margin-bottom: 1px;
}
.emoji-toggle:hover       { background: var(--surface-3); }
.emoji-toggle--active     { background: var(--surface-3); border-color: var(--line); }

.send-btn {
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.01em;
  padding: 9px 18px;
  border: 0;
  border-radius: var(--r-sm);
  background: var(--accent);
  color: var(--accent-ink);
  cursor: pointer;
  transition: background 0.15s;
  flex-shrink: 0;
  margin-bottom: 1px;
}
.send-btn:disabled             { opacity: 0.4; cursor: default; }
.send-btn:not(:disabled):hover { background: var(--accent-hover); }

/* ── Autocomplete / emoji popovers ───────────────────────────── */
.autocomplete {
  position: absolute;
  bottom: calc(100% + 4px);
  left: 16px;
  right: 16px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 6px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.1);
  overflow: hidden;
  z-index: 10;
}

.autocomplete-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 14px;
  cursor: pointer;
  transition: background 0.1s;
}
.autocomplete-item:hover { background: var(--surface-2); }
.autocomplete-item--active {
  background: var(--accent-soft);
  box-shadow: inset 2px 0 0 var(--accent);
}
.autocomplete-cmd {
  font-family: var(--font-sans);
  font-size: 12px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: 0.04em;
}
.autocomplete-param {
  font-family: var(--font-sans);
  font-size: 11px;
  color: #9a6c1a;
  letter-spacing: 0.04em;
}
/* the amber param hint is dark-on-light; lift it on dark so it stays legible */
:root[data-theme="dark"] .autocomplete-param { color: var(--warn); }
.autocomplete-desc {
  font-family: var(--font-sans);
  font-size: 11px;
  color: var(--text-muted);
  flex: 1;
}
.autocomplete-tag {
  font-family: var(--font-sans);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  border: 1px solid var(--line);
  border-radius: 3px;
  padding: 1px 5px;
}

.emoji-picker {
  position: absolute;
  bottom: calc(100% + 4px);
  right: 16px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px;
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 2px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.1);
  z-index: 10;
}

.emoji-btn {
  font-family: var(--font-sans);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.03em;
  line-height: 1;
  background: transparent;
  border: none;
  border-radius: 4px;
  padding: 6px 8px;
  cursor: pointer;
  color: var(--text);
  transition: background 0.1s;
}
.emoji-btn:hover { background: var(--surface-3); }

/* ── Responsive ──────────────────────────────────────────────── */
@media (max-width: 620px) {
  .sidebar { display: none; }
}
</style>
