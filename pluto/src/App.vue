<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useNodes } from './composables/useNodes'
import { useConnections } from './composables/useConnections'
import { useMessages } from './composables/useMessages'
import { useIdentity } from './composables/useIdentity'
import NetworkDiagram from './components/NetworkDiagram.vue'
import GroupChat from './components/GroupChat.vue'
import Control from './components/Control.vue'
import TranslationTable from './components/TranslationTable.vue'
import AchievementToast from './components/AchievementToast.vue'
import { useDeploy } from './composables/useDeploy'
import plutoLabMark from './assets/avatars/pluto-lab.svg'
import plutoC2Mark from './assets/avatars/pluto-c2.svg'

const route = useRoute()
const router = useRouter()

// Light/dark theme — toggled in the header, persisted, applied to <html> so the
// token overrides in style.css take effect. Default light; dark films cleanly
// next to a console instead of a panel that blows out white.
// localStorage keys follow one convention across the app: cpc.<domain>.<leaf>
// (see the storage-keys note in .claude memory). Old un-namespaced key read once
// as a fallback so the saved preference survives the rename.
const THEME_KEY = 'cpc.ui.theme'
const theme = ref<'light' | 'dark'>(
  (localStorage.getItem(THEME_KEY) || localStorage.getItem('cpc-theme') || 'light') as 'light' | 'dark'
)
function applyTheme(t: 'light' | 'dark') {
  document.documentElement.setAttribute('data-theme', t)
}
applyTheme(theme.value)
function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  localStorage.setItem(THEME_KEY, theme.value)
  applyTheme(theme.value)
}

// The visible panel is driven by the current route name. The router table maps
// '/' → network, '/chat' → chat, '/control/...' → the Control surface.
// The Command surface is the chat component (it's the node command bus); route is
// 'command' but the internal panel key stays 'chat'.
const activeTab = computed<'network' | 'chat' | 'control' | 'translation'>(() => {
  if (route.name === 'command') return 'chat'
  if (route.name === 'control') return 'control'
  if (route.name === 'translation') return 'translation'
  return 'network'
})

// open-tab key (and the switcher buttons) → path. The Control tab lands on the bare
// surface (it auto-selects the first available source); the node drawer's
// 'robutek'/'dreame' jump straight to the dreame source.
function goToTab(tab: 'network' | 'chat' | 'control' | 'translation' | 'robutek' | 'dreame') {
  const path = tab === 'chat' ? '/command'
    : tab === 'control' ? '/control'
    : tab === 'translation' ? '/translation'
    : (tab === 'robutek' || tab === 'dreame') ? '/control/dreame'
    : '/'
  if (route.path !== path) router.push(path)
}

const { nodes, loading, error } = useNodes()
const { connections } = useConnections()
const { messages } = useMessages()
const { showToast, toastConsoleName, toastDuration } = useDeploy()

// ── Global second header: a per-tab channel hashtag + your identity. Both headers
// live HERE in the parent so the top is uniform across tabs (no per-page stacking).
// The hashtag is the only per-tab-changing string and is declared in each route's
// meta (see main.ts), so adding a surface carries its own hashtag with it. ──
const pageHashtag = computed(() => (route.meta.hashtag as string | undefined) ?? '')

// Identity (who you are) is shared with the chat via useIdentity; the header shows it
// and lets a guest rename. A recognized node is locked to its display name.
const { meNode, guestName, isGuest, setGuestName } = useIdentity()
const editingName = ref(false)
const nameDraft   = ref('')
const nameInputEl = ref<HTMLInputElement | null>(null)
function displayName(id: string) { return id === 'pluto' ? 'Pluto C2' : (nodes.value[id]?.name ?? id) }
const identityLabel = computed(() => meNode.value ? displayName(meNode.value) : guestName.value)
function startEditName() {
  nameDraft.value = guestName.value
  editingName.value = true
  nextTick(() => { nameInputEl.value?.focus(); nameInputEl.value?.select() })
}
function saveName() { setGuestName(nameDraft.value); editingName.value = false }

// True under `vite dev` (the workspace starter), compiled to false in the built
// dist shipped to the box. Distinguishes the two instance identities: the Lab
// (workspace — builds/deploys/opens code) vs the C2 (the live command + comms node).
const isDev = import.meta.env.DEV

// The header logo IS the instance identity — the Lab wears the beaker mark, the
// live C2 the signal mark.
const headerMark = computed(() => isDev ? plutoLabMark : plutoC2Mark)

// One header button: jump to the SIBLING instance, opened in a NEW TAB so a target
// that isn't running never disturbs the current app ("be prepared"). From the Lab
// -> the C2's deployed SPA (:5173); from the C2 -> the Lab's vite server (:5174),
// shown only when LAB_IP is configured (so the Lab node exists in the roster).
const siblingLink = computed<{ label: string; url: string } | null>(() => {
  if (isDev) {
    const ip = nodes.value['pluto']?.ip
    return ip ? { label: 'C2', url: `http://${ip}:5173` } : null
  }
  const ip = nodes.value['lab']?.ip
  return ip ? { label: 'Lab', url: `http://${ip}:5174` } : null
})
function openExternal(url: string) {
  if (url) window.open(url, '_blank', 'noopener')
}

const showOffline    = ref(false)
const lastSeenMsgId  = ref(0)
const baselined      = ref(false)

function latestId() {
  return messages.value[messages.value.length - 1]?.id ?? 0
}

const unreadCount = computed(() => {
  if (activeTab.value === 'chat') return 0
  return messages.value.filter(m => m.id > lastSeenMsgId.value).length
})

// Mark everything seen whenever the chat tab is active — including messages that
// arrive while reading — so leaving for the network tab never resurfaces them as
// unread. Also baseline once on first load so pre-existing history isn't "unread".
watch(messages, () => {
  // Baseline only once the feed actually has content. The immediate run fires
  // while messages is still empty; baselining there pins lastSeen at 0 and then
  // counts all loaded history as "unread" — the phantom-badge bug.
  if (!baselined.value && messages.value.length > 0) {
    lastSeenMsgId.value = latestId()
    baselined.value = true
  }
  if (activeTab.value === 'chat') lastSeenMsgId.value = latestId()
}, { deep: true, immediate: true })

// Mark chat read whenever the chat route becomes active (including on direct load).
watch(activeTab, (tab) => {
  if (tab === 'chat') lastSeenMsgId.value = latestId()
}, { immediate: true })

const displayNodes = computed(() => {
  const src = error.value
    ? Object.fromEntries(Object.entries(nodes.value).map(
        ([k, n]) => [k, (n.status === 'unconfigured' || n.status === 'cloud') ? n : { ...n, status: 'down' as const }]))
    : nodes.value
  if (showOffline.value) return src
  return Object.fromEntries(
    Object.entries(src).filter(([, n]) => n.status !== 'unconfigured')
  )
})
</script>

<template>
  <div class="shell">
    <header class="header">
      <span class="header-title">
        <img :src="headerMark" width="42" height="42" alt="" class="header-mark" /><span>CPC Pluto <span class="header-instance">{{ isDev ? 'Lab' : 'C2' }}</span></span>
      </span>
      <span class="header-controls">
        <button
          class="head-link theme-toggle"
          :title="theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'"
          @click="toggleTheme"
        >
          <svg v-if="theme === 'dark'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4"/></svg>
          <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
        </button>
        <button
          v-if="siblingLink"
          class="head-link"
          :title="`Open the ${siblingLink.label} dashboard in a new tab`"
          @click="openExternal(siblingLink.url)"
        >{{ siblingLink.label }}<svg width="11" height="11" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3h7v7M13 3l-8 8" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
        <!-- Show-unconfigured reveals unconfigured entities on every surface: map
             nodes, chat members, and Control's unconfigured source options. -->
        <label class="toggle-label">
          <input type="checkbox" v-model="showOffline" class="toggle-checkbox" />
          <span>Show unconfigured nodes</span>
        </label>
        <span class="header-status">
          <span>{{ loading ? 'Scanning' : error ? 'Offline' : 'Live' }}</span>
          <svg width="10" height="10" viewBox="0 0 14 14" style="vertical-align: middle; margin-left: 6px;">
            <circle cx="7" cy="7" r="5" :fill="loading ? '#999999' : error ? '#cc1111' : '#00aa44'"/>
            <circle cx="5" cy="5" r="2.5" fill="white" opacity="0.5"/>
          </svg>
        </span>
      </span>
    </header>

    <main class="main">
      <!-- Global second header — uniform across tabs. Per-tab hashtag (left), your
           identity (right); the floating tab switcher rides over its clear centre. -->
      <div class="subheader">
        <span class="channel-name">{{ pageHashtag }}</span>
        <div class="identity">
          <span class="identity-eyebrow">You're</span>
          <input
            v-if="isGuest && editingName"
            ref="nameInputEl"
            v-model="nameDraft"
            class="identity-input"
            maxlength="24"
            @keydown.enter="saveName"
            @keydown.escape="editingName = false"
            @blur="saveName"
          />
          <button
            v-else-if="isGuest"
            class="identity-name"
            title="Edit your display name"
            @click="startEditName"
          >
            {{ guestName }}
            <svg class="identity-pencil" width="11" height="11" viewBox="0 0 24 24" fill="none">
              <path d="M14.06 6.19l3.75 3.75M4 20.5h3.75L18.31 9.94a1.5 1.5 0 0 0 0-2.12l-1.63-1.63a1.5 1.5 0 0 0-2.12 0L4 16.75v3.75z"
                    stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
            </svg>
          </button>
          <span v-else class="identity-name identity-name--locked">{{ identityLabel }}</span>
        </div>
      </div>

      <!-- Floating tab switcher — the three top-level Pluto surfaces, always present. -->
      <div class="tab-switcher">
        <button
          class="tab"
          :class="{ 'tab--active': activeTab === 'network' }"
          @click="goToTab('network')"
        >Network</button>
        <button
          class="tab"
          :class="{ 'tab--active': activeTab === 'chat' }"
          @click="goToTab('chat')"
        >
          Command
          <span v-if="unreadCount > 0" class="tab-badge">{{ unreadCount }}</span>
        </button>
        <button
          class="tab"
          :class="{ 'tab--active': activeTab === 'control' }"
          @click="goToTab('control')"
        >Control</button>
        <button
          class="tab"
          :class="{ 'tab--active': activeTab === 'translation' }"
          @click="goToTab('translation')"
        >Translation</button>
      </div>

      <div class="panels">
        <div v-show="activeTab === 'network'" class="network-view">
          <div v-if="loading" class="state-msg">Scanning network…</div>
          <NetworkDiagram v-show="!loading" :nodes="displayNodes" :connections="connections" @open-tab="goToTab($event as 'network' | 'chat' | 'robutek' | 'dreame')" />
        </div>

        <GroupChat
          v-show="activeTab === 'chat'"
          :nodes="nodes"
          :show-offline="showOffline"
        />

        <Control v-show="activeTab === 'control'" :active="activeTab === 'control'" :nodes="nodes" :show-offline="showOffline" />

        <TranslationTable v-show="activeTab === 'translation'" />
      </div>
    </main>

    <footer class="footer">
      consolesplayingconsoles
    </footer>

    <AchievementToast
      :show="showToast"
      :console-name="toastConsoleName"
      :duration="toastDuration"
    />
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--color-bg);
  color: var(--color-primary);
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0px 28px;
  background: var(--surface);
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}

.header-title {
  font-family: var(--font-sans);
  font-size: 19px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--accent);
  display: flex;
  align-items: center;
}

/* The instance (Lab / C2) is part of the title, not a chip — a lighter-weight,
   muted qualifier after the terracotta brand so the two read as one identity. */
.header-instance {
  font-weight: 500;
  color: var(--text-muted);
}

.header-controls {
  display: flex;
  align-items: center;
  gap: 20px;
}

.header-mark {
  display: inline-block;
  vertical-align: middle;
  margin-right: 7px;
}

.head-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  padding: 4px 9px;
  color: var(--text-muted);
  background: transparent;
  border: 1px solid var(--line);
  border-radius: 6px;
  cursor: pointer;
  transition: color 0.15s, background 0.15s, border-color 0.15s;
}
.head-link svg { opacity: 0.8; }
.head-link:hover:not(:disabled) {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-soft, rgba(245, 166, 35, 0.12));
}
.head-link:disabled { opacity: 0.45; cursor: default; }
.head-link:focus { outline: none; }
.head-link:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }

.toggle-label {
  display: flex;
  align-items: center;
  gap: 7px;
  font-family: var(--font-sans);
  font-size: 12px;
  letter-spacing: 0.01em;
  color: var(--color-secondary);
  cursor: pointer;
  user-select: none;
}

.toggle-checkbox {
  appearance: none;
  width: 12px;
  height: 12px;
  border: 1.5px solid var(--color-secondary);
  border-radius: 2px;
  background: transparent;
  cursor: pointer;
  position: relative;
  flex-shrink: 0;
}

.toggle-checkbox:checked {
  background: var(--color-secondary);
}

.toggle-checkbox:checked::after {
  content: '';
  position: absolute;
  left: 2px;
  top: -1px;
  width: 5px;
  height: 8px;
  border: 1.5px solid #ebebea;
  border-top: none;
  border-left: none;
  transform: rotate(45deg);
}

.header-status {
  display: flex;
  align-items: center;
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--color-primary);
}

/* ── Main ────────────────────────────────────────────────────── */
.main {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  position: relative;
  display: flex;
  flex-direction: column;
}

/* Global second header — same height/colour for every tab; the floating tabs ride
   over its clear centre (hashtag left, identity right). */
.subheader {
  flex: 0 0 auto;
  height: 58px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  background: var(--surface);
  border-bottom: 1px solid var(--line);
}
.channel-name {
  font-family: var(--font-sans);
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--text);
}
.identity { display: flex; align-items: center; gap: 8px; }
.identity-eyebrow { font-family: var(--font-sans); font-size: 12px; color: var(--text-muted); }
.identity-name {
  display: inline-flex; align-items: center; gap: 6px;
  font-family: var(--font-sans); font-size: 13px; font-weight: 600;
  color: var(--accent); background: var(--accent-soft);
  border: 1px solid transparent; border-radius: var(--r-sm);
  padding: 4px 10px; cursor: pointer; transition: border-color 0.15s;
}
.identity-name:hover            { border-color: var(--accent); }
.identity-pencil                { opacity: 0.55; }
.identity-name--locked          { cursor: default; }
.identity-name--locked:hover    { border-color: transparent; }
.identity-input {
  font-family: var(--font-sans); font-size: 13px; font-weight: 600;
  color: var(--text); width: 132px; padding: 4px 10px;
  border: 1px solid var(--accent); border-radius: var(--r-sm);
  outline: none; box-shadow: 0 0 0 3px var(--accent-soft);
}

/* The tab panels fill the rest below the second header. */
.panels { flex: 1; min-height: 0; position: relative; }

.network-view {
  width: 100%;
  height: 100%;
  position: relative;
}

/* ── Floating tab switcher ───────────────────────────────────── */
.tab-switcher {
  position: absolute;
  top: 14px;
  left: 50%;
  transform: translateX(-50%);
  /* Layering vs the network diagram (all in the same root stacking context):
     diagram bg/idle nodes (1) < tabs (2) = deploy terminal (2, later in DOM, so
     it paints above the tabs) < active bubble (3). The terminal's 1/2/3 ladder
     is fixed by the bubble overlay, so we drop the tabs to slot under it rather
     than bumping the terminal. */
  z-index: 2;
  display: flex;
  background: var(--tab-track);   /* one unified track holds all three */
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid var(--line);
  border-radius: 22px;
  padding: 3px;
  gap: 2px;
  box-shadow: inset 0 1px 1px rgba(26, 34, 51, 0.04);
}

.tab {
  font-family: var(--font-sans);
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
  padding: 6px 18px;
  border: none;
  border-radius: 18px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: background 0.18s, color 0.18s;
  white-space: nowrap;
}

/* keyboard focus is on-brand; a mouse click never paints the default blue ring */
.tab:focus         { outline: none; }
.tab:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

.tab:not(.tab--active):hover {
  background: rgba(26, 34, 51, 0.05);
  color: var(--text);
}

.tab--active,
.tab--active:hover {
  background: var(--accent);
  color: var(--accent-ink);
  box-shadow: 0 1px 3px rgba(176, 94, 67, 0.45);
}

.tab-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  margin-left: 6px;
  border-radius: 8px;
  background: #cc3a1a;
  color: #fff;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0;
  line-height: 1;
  vertical-align: middle;
}

.state-msg {
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.05em;
  color: var(--color-secondary);
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}

.footer {
  padding: 10px 24px;
  background: var(--surface);
  border-top: 1px solid var(--line);
  font-family: var(--font-mono);
  font-size: 12px;
  letter-spacing: 0.1em;
  color: var(--color-primary);
  opacity: 0.7;
  flex-shrink: 0;
}
</style>
