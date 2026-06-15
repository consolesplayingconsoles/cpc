<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useNodes } from './composables/useNodes'
import { useConnections } from './composables/useConnections'
import { useMessages } from './composables/useMessages'
import NetworkDiagram from './components/NetworkDiagram.vue'
import GroupChat from './components/GroupChat.vue'
import Robutek from './components/Robutek.vue'

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

// True under `vite dev` (the dev starter), compiled to false in the built dist
// shipped to the box — drives the DEV badge and the dev-only CODE button.
const isDev = import.meta.env.DEV

const showOffline    = ref(false)
const activeTab      = ref<'network' | 'chat' | 'robutek'>('network')
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

onMounted(() => {
  const tab = new URLSearchParams(window.location.search).get('tab')
  if (tab === 'chat' || tab === 'network' || tab === 'robutek') activeTab.value = tab
})

watch(activeTab, (tab) => {
  if (tab === 'chat') lastSeenMsgId.value = latestId()
  const url = new URL(window.location.href)
  url.searchParams.set('tab', tab)
  history.replaceState(null, '', url.toString())
})

// Never strand the user on a hidden Dreame tab — covers both a ?tab=robutek deep
// link and the roster loading async after mount. Bounce back to Network.
watch(dreameConfigured, (ok) => {
  if (!ok && activeTab.value === 'robutek') activeTab.value = 'network'
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
        <svg width="64" height="64" viewBox="0 0 24 24" style="vertical-align:middle; margin-right:6px;">
          <!-- tilted orbit / network ring -->
          <ellipse cx="12" cy="12" rx="11" ry="4.1" fill="none"
                   stroke="var(--accent)" stroke-width="1.4" opacity="0.5"
                   transform="rotate(-22 12 12)"/>
          <!-- planet: terracotta Pluto -->
          <circle cx="12" cy="12" r="5.6" fill="var(--accent)"/>
          <circle cx="9.9" cy="9.9" r="1.9" fill="#fff" opacity="0.18"/>
          <!-- network nodes riding the orbit -->
          <circle cx="22.2" cy="7.9" r="1.6" fill="var(--accent)"/>
          <circle cx="1.8" cy="16.1" r="1.6" fill="var(--accent)"/>
        </svg><span>CPC Pluto</span>
        <span v-if="isDev" class="dev-badge" title="Vite dev server — not the deployed build">DEV</span>
      </span>
      <span class="header-controls">
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
      <!-- Floating tab switcher -->
      <div class="tab-switcher">
        <button
          class="tab"
          :class="{ 'tab--active': activeTab === 'network' }"
          @click="activeTab = 'network'"
        >Network</button>
        <button
          class="tab"
          :class="{ 'tab--active': activeTab === 'chat' }"
          @click="activeTab = 'chat'"
        >
          Chat
          <span v-if="unreadCount > 0" class="tab-badge">{{ unreadCount }}</span>
        </button>
        <button
          v-if="dreameConfigured"
          class="tab"
          :class="{ 'tab--active': activeTab === 'robutek' }"
          @click="activeTab = 'robutek'"
        >Dreame</button>
      </div>

      <div v-show="activeTab === 'network'" class="network-view">
        <div v-if="loading" class="state-msg">Scanning network…</div>
        <NetworkDiagram v-show="!loading" :nodes="displayNodes" :connections="connections" @open-tab="activeTab = $event as 'network' | 'chat' | 'robutek'" />
      </div>

      <GroupChat
        v-show="activeTab === 'chat'"
        :nodes="nodes"
        :show-offline="showOffline"
      />

      <Robutek v-show="activeTab === 'robutek'" :name="dreameName" :active="activeTab === 'robutek'" :nodes="nodes" />
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

.dev-badge {
  margin-left: 10px;
  padding: 2px 7px;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.14em;
  color: var(--accent);
  background: var(--accent-soft, rgba(245, 166, 35, 0.14));
  border: 1px solid var(--accent);
  border-radius: 4px;
  text-transform: uppercase;
  /* a quiet mode chip — clearly a state cue, not part of the brand accent usage */
}

.header-controls {
  display: flex;
  align-items: center;
  gap: 20px;
}

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
  background: rgba(238, 240, 243, 0.9);   /* one unified track holds all three */
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
