<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import type { NodeMap, NodeData } from '../composables/useNodes'
import { ICONS } from '../composables/useIcons'
import { useMessages } from '../composables/useMessages'
import ConsoleAvatar from './ConsoleAvatar.vue'

const props = defineProps<{
  nodes:       NodeMap
  showOffline: boolean
}>()

// ── Messages (live API) ──────────────────────────────────────────────────────
const { messages, sendMessage } = useMessages()

// ── Member lists — ordered: online → offline → unconfigured ──────────────────
const allNodes = computed(() => Object.values(props.nodes).filter(n => n.id !== 'gateway'))

const onlineMembers       = computed(() => allNodes.value.filter(n => n.status === 'up'))
const offlineMembers      = computed(() => allNodes.value.filter(n => n.status === 'down'))
const unconfiguredMembers = computed(() =>
  props.showOffline ? allNodes.value.filter(n => n.status === 'unconfigured') : []
)

// ── Message helpers ──────────────────────────────────────────────────────────
function nodeFor(id: string): NodeData | null {
  return props.nodes[id] ?? props.nodes[id === 'pluto' ? 'host' : id] ?? null
}

function iconFor(id: string): string | undefined {
  return ICONS[id] ?? ICONS[nodeFor(id)?.id ?? ''] ?? undefined
}

function displayName(id: string) {
  if (id === 'pluto') return 'pluto'
  return (props.nodes[id]?.name ?? id).toLowerCase()
}

function nameColor(id: string) {
  const node = nodeFor(id)
  if (node?.status === 'unconfigured') return 'var(--color-secondary)'
  return node?.color ?? '#888884'
}

function formatTime(ts: string) {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
}

function formatMsg(text: string): Array<{ mention: boolean; text: string }> {
  return text.split(/(@\w+)/g).map((part, i) => ({ mention: i % 2 === 1, text: part }))
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

// ── Commands ─────────────────────────────────────────────────────────────────
interface CmdDef {
  cmd:        string
  desc:       string
  param?:     { label: string; type: 'console' }
  multiline?: boolean
  done?:      boolean   // implemented? defaults to false = visible but not sendable
}

const COMMANDS: CmdDef[] = [
  { cmd: '/post-to-substack',  desc: 'write & broadcast to substack',    multiline: true },
  { cmd: '/send-saved-games',  desc: 'push saved games to a console',    param: { label: 'console', type: 'console' } },
  { cmd: '/steal-saved-games', desc: 'pull saved games from a console',  param: { label: 'console', type: 'console' } },
]

// @l40 vacuum verbs — offered as autocomplete after "@l40 " when the feeder's
// cousin (the vacuum) is present. Mirrors the safe verb set in the Pluto API.
const VACUUM_VERBS = [
  { verb: 'locate', desc: 'beep so you can find it' },
  { verb: 'clean',  desc: 'start cleaning' },
  { verb: 'dock',   desc: 'return to charge' },
  { verb: 'stop',   desc: 'stop / park in place' },
]

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

const EMOJIS = [':)', ':(', ':|', ':D', ":'(", '>:(', '+1', '-1', '<3', 'X_X', 'O_O', '\\o/', 'gg', 'lol', 'rip', 'ugh', 'zzz', 'ngl', ':P', '...']

function insertEmoji(e: string) {
  draft.value += e
  showEmoji.value = false
  nextTick(() => (inputEl.value ?? textareaEl.value)?.focus())
}

// Parse what's in the draft
const draftParts = computed(() => draft.value.split(' '))

// Resolved command when the first token exactly matches a command name
const resolvedCmd = computed(() =>
  COMMANDS.find(c => c.cmd === draftParts.value[0]) ?? null
)

// True when we're still typing the command name (no space yet)
const showCmdMenu = computed(() =>
  draft.value.startsWith('/') && !draft.value.includes(' ')
)

const filteredCmds = computed(() => {
  const t = draft.value.toLowerCase()
  return COMMANDS.filter(c => c.cmd.startsWith(t))
})

function selectCmd(cmd: string) {
  // Unimplemented commands are readable & navigable, but cannot be added to the
  // prompt — selecting one (click / Tab / Enter) is a deliberate no-op.
  const def = COMMANDS.find(c => c.cmd === cmd)
  if (def && def.done !== true) {
    (inputEl.value ?? textareaEl.value)?.focus()
    return
  }
  draft.value = cmd + ' '
  nextTick(() => (inputEl.value ?? textareaEl.value)?.focus())
}

// Console param autocomplete: active after a console-param command + space
const showConsoleMenu = computed(() =>
  !!resolvedCmd.value?.param && draft.value.includes(' ') && !showCmdMenu.value
)

const consolePartial = computed(() => (draftParts.value[1] ?? '').toLowerCase())

const consoleCandidates = computed(() => {
  if (!showConsoleMenu.value) return []
  const ids = Object.keys(props.nodes).filter(id => id !== 'gateway')
  return consolePartial.value
    ? ids.filter(id => id.toLowerCase().startsWith(consolePartial.value))
    : ids
})

function pickConsole(id: string) {
  draft.value = `${draftParts.value[0]} ${id}`
  nextTick(() => (inputEl.value ?? textareaEl.value)?.focus())
}

// Mention menu: last word starts with @
const showMentionMenu = computed(() => {
  const words = draft.value.split(' ')
  const last  = words[words.length - 1]
  return last.startsWith('@') && last.length >= 1 && !showCmdMenu.value
})

const mentionList = computed(() => {
  const base = ['@here', '@everyone']
  if (props.nodes['claude']) base.push('@claude')
  if (props.nodes['dreame']) base.push('@l40')
  return base
})

const filteredMentions = computed(() => {
  const words = draft.value.split(' ')
  const last  = words[words.length - 1].toLowerCase()
  return mentionList.value.filter(m => m.startsWith(last))
})

function selectMention(m: string) {
  const words = draft.value.split(' ')
  words[words.length - 1] = m
  draft.value = words.join(' ') + ' '
  nextTick(() => (inputEl.value ?? textareaEl.value)?.focus())
}

// Vacuum verb menu: active after "@l40 " when the vacuum node is present.
const showVacuumMenu = computed(() =>
  !!props.nodes['dreame'] &&
  draftParts.value[0]?.toLowerCase() === '@l40' &&
  draft.value.includes(' ') &&
  !showCmdMenu.value
)
const vacuumPartial = computed(() => (draftParts.value[1] ?? '').toLowerCase())
const vacuumCandidates = computed(() =>
  showVacuumMenu.value
    ? VACUUM_VERBS.filter(v => v.verb.startsWith(vacuumPartial.value))
    : [],
)
function pickVacuum(verb: string) {
  draft.value = `@l40 ${verb}`
  nextTick(() => (inputEl.value ?? textareaEl.value)?.focus())
}

// ── Unified autocomplete navigation ──────────────────────────────────────────
// Whichever menu is open exposes a flat list of selectable values plus an apply
// fn, so arrow-key nav and tab/enter-to-complete work the same everywhere. This
// is what stops a half-typed "@cla" from being sent on Enter.
interface Suggest { items: string[]; apply: (v: string) => void }

const highlight = ref(0)

const activeSuggest = computed<Suggest | null>(() => {
  if (showCmdMenu.value && filteredCmds.value.length)
    return { items: filteredCmds.value.map(c => c.cmd), apply: selectCmd }
  if (showConsoleMenu.value && consoleCandidates.value.length)
    return { items: consoleCandidates.value, apply: pickConsole }
  if (showMentionMenu.value && filteredMentions.value.length)
    return { items: filteredMentions.value, apply: selectMention }
  if (showVacuumMenu.value && vacuumCandidates.value.length)
    return { items: vacuumCandidates.value.map(v => v.verb), apply: pickVacuum }
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

// Multiline mode: the resolved command needs multiline input
const isMultiline = computed(() => resolvedCmd.value?.multiline === true)

// A slash-command that isn't built yet — kept visible so it's discoverable, but
// not sendable so it can't be fired by accident.
const blockedCmd = computed(() => {
  const c = COMMANDS.find(c => c.cmd === draftParts.value[0])
  return c && c.done !== true ? c : null
})

// ── Send ─────────────────────────────────────────────────────────────────────
function send() {
  const text = draft.value.trim()
  if (!text || blockedCmd.value) return
  sendMessage('pluto', text)
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
    if (e.key === 'Enter' && !e.shiftKey)  { e.preventDefault(); applyHighlighted(); return }
  }

  // Textarea in multiline mode: Enter sends, Shift+Enter inserts newline
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
}

const plutoNode = computed(() => props.nodes['host'] ?? null)
</script>

<template>
  <div class="chat" @click="showEmoji = false">
    <div class="chat-body">

      <!-- Left sidebar: ordered online → offline → unconfigured -->
      <aside class="sidebar">
        <div v-if="onlineMembers.length > 0">
          <p class="sidebar-section">ONLINE &mdash; {{ onlineMembers.length }}</p>
          <div v-for="n in onlineMembers" :key="n.id" class="member">
            <ConsoleAvatar :id="n.id" :icon="ICONS[n.id]" :status="n.status" :color="n.color" :size="36" />
            <span class="member-name" :style="{ color: n.color ?? 'var(--color-primary)' }">
              {{ displayName(n.id) }}
            </span>
          </div>
        </div>

        <div v-if="offlineMembers.length > 0">
          <p class="sidebar-section sidebar-section--dim">OFFLINE &mdash; {{ offlineMembers.length }}</p>
          <div v-for="n in offlineMembers" :key="n.id" class="member member--offline">
            <ConsoleAvatar :id="n.id" :icon="ICONS[n.id]" :status="n.status" :color="n.color" :size="36" />
            <span class="member-name member-name--dim">
              {{ displayName(n.id) }}
            </span>
          </div>
        </div>

        <div v-if="unconfiguredMembers.length > 0">
          <p class="sidebar-section sidebar-section--dim">NOT PRESENT &mdash; {{ unconfiguredMembers.length }}</p>
          <div v-for="n in unconfiguredMembers" :key="n.id" class="member member--unconfigured">
            <ConsoleAvatar :id="n.id" :icon="ICONS[n.id]" :status="n.status" :color="n.color" :size="36" />
            <span class="member-name member-name--dim">
              {{ displayName(n.id) }}
            </span>
          </div>
        </div>
      </aside>

      <!-- Right: channel + feed + input -->
      <div class="chat-col">
        <div class="channel-header">
          <span class="channel-name"># consoles-chatting-consoles</span>
        </div>

        <div ref="feedEl" class="feed">
          <div v-for="g in messageGroups" :key="g.key" class="msg-group">
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
                <span class="msg-time">{{ formatTime(g.messages[0].ts) }}</span>
              </div>
              <p v-for="m in g.messages" :key="m.id" class="msg-text">
                <template v-for="(seg, si) in formatMsg(m.text)" :key="si">
                  <strong v-if="seg.mention" class="msg-mention">{{ seg.text }}</strong><span v-else>{{ seg.text }}</span>
                </template>
              </p>
            </div>
          </div>

          <div v-if="messageGroups.length === 0" class="feed-empty">
            no messages yet &mdash; say something
          </div>
        </div>

        <!-- Input area -->
        <div class="input-wrap" @click.stop>

          <!-- Command name autocomplete -->
          <div v-if="showCmdMenu && filteredCmds.length > 0" class="autocomplete">
            <div
              v-for="c in filteredCmds"
              :key="c.cmd"
              class="autocomplete-item"
              :class="{ 'autocomplete-item--active': isHl(c.cmd), 'autocomplete-item--soon': c.done !== true }"
              @mouseenter="setHl(c.cmd)"
              @click="selectCmd(c.cmd)"
            >
              <span class="autocomplete-cmd">{{ c.cmd }}</span>
              <span v-if="c.param" class="autocomplete-param">&lt;{{ c.param.label }}&gt;</span>
              <span class="autocomplete-desc">{{ c.desc }}</span>
              <span v-if="c.multiline" class="autocomplete-tag">multiline</span>
              <span v-if="c.done !== true" class="autocomplete-tag autocomplete-tag--soon">soon</span>
            </div>
          </div>

          <!-- Console param autocomplete -->
          <div v-if="showConsoleMenu && consoleCandidates.length > 0" class="autocomplete">
            <div
              v-for="id in consoleCandidates"
              :key="id"
              class="autocomplete-item"
              :class="{ 'autocomplete-item--active': isHl(id) }"
              @mouseenter="setHl(id)"
              @click="pickConsole(id)"
            >
              <ConsoleAvatar
                :id="id"
                :icon="ICONS[id]"
                :status="nodes[id]?.status ?? 'unconfigured'"
                :color="nodes[id]?.color"
                :size="20"
              />
              <span class="autocomplete-cmd">{{ id }}</span>
              <span class="autocomplete-desc">{{ nodes[id]?.ip ?? '' }}</span>
            </div>
          </div>

          <!-- Mention autocomplete -->
          <div v-if="showMentionMenu && filteredMentions.length > 0" class="autocomplete">
            <div
              v-for="m in filteredMentions"
              :key="m"
              class="autocomplete-item"
              :class="{ 'autocomplete-item--active': isHl(m) }"
              @mouseenter="setHl(m)"
              @click="selectMention(m)"
            >
              <span class="autocomplete-cmd">{{ m }}</span>
            </div>
          </div>

          <!-- @l40 vacuum verb autocomplete -->
          <div v-if="showVacuumMenu && vacuumCandidates.length > 0" class="autocomplete">
            <div
              v-for="v in vacuumCandidates"
              :key="v.verb"
              class="autocomplete-item"
              :class="{ 'autocomplete-item--active': isHl(v.verb) }"
              @mouseenter="setHl(v.verb)"
              @click="pickVacuum(v.verb)"
            >
              <span class="autocomplete-cmd">{{ v.verb }}</span>
              <span class="autocomplete-desc">{{ v.desc }}</span>
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
            <ConsoleAvatar
              id="host"
              :icon="ICONS['host']"
              :status="plutoNode?.status ?? 'up'"
              :color="plutoNode?.color"
              :size="36"
            />

            <div class="input-field-wrap">
              <textarea
                v-if="isMultiline"
                ref="textareaEl"
                v-model="draft"
                class="input-field input-field--textarea"
                placeholder="write your post... (shift+enter for new line)"
                maxlength="2000"
                rows="3"
                @keydown="onKeydown"
              />
              <div v-else class="input-overlay-box">
                <div ref="hlEl" class="input-hl" aria-hidden="true">
                  <span class="input-hl-text"><template
                    v-for="(seg, si) in formatMsg(draft)"
                    :key="si"
                  ><strong v-if="seg.mention">{{ seg.text }}</strong><span v-else>{{ seg.text }}</span></template></span>
                </div>
                <input
                  ref="inputEl"
                  v-model="draft"
                  class="input-field input-field--overlay"
                  placeholder="message as pluto... (/ for commands, @ to mention)"
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
              :disabled="!draft.trim() || !!blockedCmd"
              :title="blockedCmd ? 'not built yet' : 'send'"
              @click="send"
            >
              {{ blockedCmd ? 'SOON' : 'SEND' }}
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
  background: var(--color-bg);
  overflow: hidden;
  padding-top: 52px; /* clear floating tab switcher */
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
  border-right: 1px solid var(--color-border);
  background: #f5f5f3;
  overflow-y: auto;
  padding: 14px 0;
}

.sidebar::-webkit-scrollbar       { width: 4px; }
.sidebar::-webkit-scrollbar-thumb { background: var(--color-border); border-radius: 2px; }

.sidebar-section {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.12em;
  color: var(--color-secondary);
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
.member:hover             { background: rgba(0,0,0,0.04); }
.member--offline          { opacity: 0.5; }
.member--unconfigured     { opacity: 0.28; }

.member-name {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  filter: brightness(0.78);
}
.member-name--dim {
  color: var(--color-secondary) !important;
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

.channel-header {
  display: flex;
  align-items: center;
  padding: 10px 20px;
  border-bottom: 1px solid var(--color-border);
  background: #f9f9f8;
  flex-shrink: 0;
}

.channel-name {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.05em;
  color: var(--color-primary);
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
.feed::-webkit-scrollbar-thumb { background: var(--color-border); border-radius: 3px; }

.msg-group {
  display: flex;
  gap: 14px;
  padding: 7px 0;
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
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.04em;
  filter: brightness(0.78);
}

.msg-time {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--color-secondary);
  letter-spacing: 0.06em;
  opacity: 0.65;
}

.msg-text {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--color-primary);
  line-height: 1.6;
  word-break: break-word;
  margin: 0;
  white-space: pre-wrap;
}

.msg-mention {
  font-weight: 700;
  letter-spacing: 0.02em;
}

.feed-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-mono);
  font-size: 12px;
  letter-spacing: 0.1em;
  color: var(--color-secondary);
  opacity: 0.5;
}

/* ── Input area ──────────────────────────────────────────────── */
.input-wrap {
  position: relative;
  flex-shrink: 0;
  border-top: 1px solid var(--color-border);
  background: #f5f5f3;
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
  background: #f0f0ee;   /* recessed — distinct from the white chat bg */
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 8px 12px;
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--color-primary);
  outline: none;
  transition: border-color 0.15s;
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
  caret-color: var(--color-primary);
}
.input-hl {
  position: absolute;
  inset: 0;
  z-index: 0;
  display: flex;
  align-items: center;
  padding: 8px 12px;
  border: 1px solid transparent;   /* match input border box for alignment */
  border-radius: 4px;
  box-sizing: border-box;
  overflow: hidden;
  pointer-events: none;
  background: #f0f0ee;             /* recessed fill behind the transparent input */
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--color-primary);
}
.input-hl-text { white-space: pre; }
.input-hl-text strong { font-weight: 700; color: var(--color-primary); }
.input-field::placeholder { color: var(--color-secondary); opacity: 0.55; }
.input-field:focus        { border-color: var(--color-secondary); }

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
.emoji-toggle:hover       { background: rgba(0,0,0,0.06); }
.emoji-toggle--active     { background: rgba(0,0,0,0.08); border-color: var(--color-border); }

.send-btn {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.1em;
  padding: 8px 16px;
  border: 1.5px solid var(--color-primary);
  border-radius: 3px;
  background: var(--color-primary);
  color: var(--color-bg);
  cursor: pointer;
  transition: opacity 0.15s;
  flex-shrink: 0;
  margin-bottom: 1px;
}
.send-btn:disabled             { opacity: 0.3; cursor: default; }
.send-btn:not(:disabled):hover { opacity: 0.72; }

/* ── Autocomplete / emoji popovers ───────────────────────────── */
.autocomplete {
  position: absolute;
  bottom: calc(100% + 4px);
  left: 16px;
  right: 16px;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
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
.autocomplete-item:hover { background: #f0f0ee; }
.autocomplete-item--active {
  background: #e6e6e2;
  box-shadow: inset 2px 0 0 var(--color-primary);
}
/* not-yet-built command: visible & navigable, but visually muted */
.autocomplete-item--soon { cursor: default; }
.autocomplete-item--soon .autocomplete-cmd,
.autocomplete-item--soon .autocomplete-desc { opacity: 0.5; }
.autocomplete-tag--soon {
  color: #9a6c1a;
  border-color: #d8b06a;
  background: #faf3e2;
}

.autocomplete-cmd {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 700;
  color: var(--color-primary);
  letter-spacing: 0.04em;
}
.autocomplete-param {
  font-family: var(--font-mono);
  font-size: 11px;
  color: #9a6c1a;
  letter-spacing: 0.04em;
}
.autocomplete-desc {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--color-secondary);
  flex: 1;
}
.autocomplete-tag {
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--color-secondary);
  border: 1px solid var(--color-border);
  border-radius: 3px;
  padding: 1px 5px;
}

.emoji-picker {
  position: absolute;
  bottom: calc(100% + 4px);
  right: 16px;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 10px;
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 2px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.1);
  z-index: 10;
}

.emoji-btn {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.03em;
  line-height: 1;
  background: transparent;
  border: none;
  border-radius: 4px;
  padding: 6px 8px;
  cursor: pointer;
  color: var(--color-primary);
  transition: background 0.1s;
}
.emoji-btn:hover { background: #e8e8e6; }

/* ── Responsive ──────────────────────────────────────────────── */
@media (max-width: 620px) {
  .sidebar { display: none; }
}
</style>
