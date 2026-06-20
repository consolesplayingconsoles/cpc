<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useNodes } from './composables/useNodes'
import { useConnections } from './composables/useConnections'
import { useMessages } from './composables/useMessages'
import NetworkDiagram from './components/NetworkDiagram.vue'
import GroupChat from './components/GroupChat.vue'
import Robutek from './components/Robutek.vue'
import plutoLabMark from './assets/avatars/pluto-lab.svg'
import plutoC2Mark from './assets/avatars/pluto-c2.svg'

const route = useRoute()
const router = useRouter()

// Light/dark theme — toggled in the header, persisted, applied to <html> so the
// token overrides in style.css take effect. Default light; dark films cleanly
// next to a console instead of a panel that blows out white.
const theme = ref<'light' | 'dark'>(
  (localStorage.getItem('cpc-theme') as 'light' | 'dark') || 'light'
)
function applyTheme(t: 'light' | 'dark') {
  document.documentElement.setAttribute('data-theme', t)
}
applyTheme(theme.value)
function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  localStorage.setItem('cpc-theme', theme.value)
  applyTheme(theme.value)
}

// The visible panel is driven by the current route name. The router table maps
// '/' → network, '/chat' → chat, '/dreame' → the Dreame/Robutek view.
const activeTab = computed<'network' | 'chat' | 'robutek'>(() => {
  if (route.name === 'chat') return 'chat'
  if (route.name === 'dreame') return 'robutek'
  return 'network'
})

// open-tab key (and the switcher buttons) → path
function goToTab(tab: 'network' | 'chat' | 'robutek' | 'dreame') {
  const path = tab === 'chat' ? '/chat' : (tab === 'robutek' || tab === 'dreame') ? '/dreame' : '/'
  if (route.path !== path) router.push(path)
}

const { nodes, loading, error } = useNodes()
const { connections } = useConnections()
const { messages } = useMessages()

const dreameName = computed(() => nodes.value['dreame']?.name ?? 'dreame')

// The Dreame tab only makes sense when the vacuum node is configured (a real .env;
// an unconfigured placeholder reads status 'unconfigured'). Hide the tab otherwise.
// (The vacuum's modules will fold into the UI properly later; this tab is fine for now.)
const dreameConfigured = computed(() =>
  !!nodes.value['dreame'] && nodes.value['dreame'].status !== 'unconfigured'
)

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

// Never strand the user on a hidden Dreame tab — covers both a /dreame deep
// link and the roster loading async after mount. Redirect back to Network.
watch(dreameConfigured, (ok) => {
  if (!ok && activeTab.value === 'robutek') router.replace('/')
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
        <label class="toggle-label">
          <input type="checkbox" v-model="showOffline" class="toggle-checkbox" />
          <span v-if="activeTab !== 'robutek'">Show unconfigured nodes</span>
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
      <!-- Floating tab switcher — top-level Pluto surfaces only. A per-node module
           drill-in (Dreame) hides it and carries its own Back affordance instead,
           so we never sit in a tab bar with nothing selected. -->
      <div v-if="activeTab !== 'robutek'" class="tab-switcher">
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
          Chat
          <span v-if="unreadCount > 0" class="tab-badge">{{ unreadCount }}</span>
        </button>
      </div>

      <div v-show="activeTab === 'network'" class="network-view">
        <div v-if="loading" class="state-msg">Scanning network…</div>
        <NetworkDiagram v-show="!loading" :nodes="displayNodes" :connections="connections" @open-tab="goToTab($event as 'network' | 'chat' | 'robutek' | 'dreame')" />
      </div>

      <GroupChat
        v-show="activeTab === 'chat'"
        :nodes="nodes"
        :show-offline="showOffline"
      />

      <Robutek v-show="activeTab === 'robutek'" :name="dreameName" :active="activeTab === 'robutek'" :nodes="nodes" @back="goToTab('network')" />
    </main>

    <footer class="footer">
      consolesplayingconsoles
    </footer>
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
  overflow: hidden;
  position: relative;
}

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
