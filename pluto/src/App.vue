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
  if (!baselined.value) {
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

const displayNodes = computed(() => {
  const src = error.value
    ? Object.fromEntries(Object.entries(nodes.value).map(
        ([k, n]) => [k, n.status === 'unconfigured' ? n : { ...n, status: 'down' as const }]))
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
        <svg width="12" height="12" viewBox="0 0 12 12" style="vertical-align:middle; margin-right:8px;">
          <circle cx="6" cy="6" r="5" fill="#F5A623" opacity="0.2"/>
          <circle cx="6" cy="6" r="3.5" fill="#F5A623"/>
          <circle cx="4.5" cy="4.5" r="1.5" fill="white" opacity="0.45"/>
        </svg><span>CPC PLUTO</span>
      </span>
      <span class="header-controls">
        <label class="toggle-label">
          <input type="checkbox" v-model="showOffline" class="toggle-checkbox" />
          <span>show not present</span>
        </label>
        <span class="header-status">
          <span>{{ loading ? 'SCANNING' : error ? 'OFFLINE' : 'LIVE' }}</span>
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
        >NETWORK</button>
        <button
          class="tab"
          :class="{ 'tab--active': activeTab === 'chat' }"
          @click="activeTab = 'chat'"
        >
          CHAT
          <span v-if="unreadCount > 0" class="tab-badge">{{ unreadCount }}</span>
        </button>
        <button
          class="tab"
          :class="{ 'tab--active': activeTab === 'robutek' }"
          @click="activeTab = 'robutek'"
        >{{ dreameName.toUpperCase() }}</button>
      </div>

      <div v-show="activeTab === 'network'" class="network-view">
        <div v-if="loading" class="state-msg">SCANNING NETWORK...</div>
        <NetworkDiagram v-show="!loading" :nodes="displayNodes" :connections="connections" />
      </div>

      <GroupChat
        v-show="activeTab === 'chat'"
        :nodes="nodes"
        :show-offline="showOffline"
      />

      <Robutek v-show="activeTab === 'robutek'" :name="dreameName" :active="activeTab === 'robutek'" />
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
  padding: 12px 24px;
  background: #ebebea;
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.header-title {
  font-family: var(--font-mono);
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.15em;
  color: #9a6c1a;
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
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.08em;
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
  font-family: var(--font-mono);
  font-size: 13px;
  letter-spacing: 0.1em;
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
  z-index: 20;
  display: flex;
  background: rgba(235, 235, 234, 0.92);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid var(--color-border);
  border-radius: 24px;
  padding: 3px;
  gap: 2px;
  box-shadow: 0 2px 16px rgba(0, 0, 0, 0.1), 0 1px 4px rgba(0, 0, 0, 0.06);
}

.tab {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  padding: 6px 20px;
  border: none;
  border-radius: 20px;
  background: transparent;
  color: var(--color-secondary);
  cursor: pointer;
  transition: background 0.18s, color 0.18s;
  white-space: nowrap;
}

.tab:not(.tab--active):hover {
  background: rgba(26, 26, 26, 0.1);
  color: var(--color-primary);
}

.tab--active:hover {
  background: rgba(26, 26, 26, 0.78);
}

.tab--active {
  background: var(--color-primary);
  color: var(--color-bg);
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
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.2em;
  color: var(--color-secondary);
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}

.footer {
  padding: 10px 24px;
  background: #ebebea;
  border-top: 1px solid var(--color-border);
  font-family: var(--font-mono);
  font-size: 12px;
  letter-spacing: 0.1em;
  color: var(--color-primary);
  opacity: 0.7;
  flex-shrink: 0;
}
</style>
