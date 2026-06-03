<script setup lang="ts">
import { useNodes } from './composables/useNodes'
import NetworkDiagram from './components/NetworkDiagram.vue'

const { nodes, loading, error } = useNodes()
</script>

<template>
  <div class="shell">
    <header class="header">
      <span class="header-title">CPC PLUTO</span>
      <span class="header-status">
        <span>{{ loading ? 'SCANNING' : error ? 'OFFLINE' : 'LIVE' }}</span>
        <svg width="10" height="10" viewBox="0 0 14 14" style="vertical-align: middle; margin-left: 6px;">
          <circle cx="7" cy="7" r="5" :fill="loading ? '#999999' : error ? '#cc1111' : '#00aa44'"/>
          <circle cx="5" cy="5" r="2.5" fill="white" opacity="0.5"/>
        </svg>
      </span>
    </header>

    <main class="main">
      <div v-if="loading" class="state-msg">SCANNING NETWORK...</div>
      <NetworkDiagram v-else :nodes="nodes" />
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
}

.header-title {
  font-family: var(--font-mono);
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.15em;
  color: var(--color-primary);
}

.header-status {
  display: flex;
  align-items: center;
  font-family: var(--font-mono);
  font-size: 13px;
  letter-spacing: 0.1em;
  color: var(--color-primary);
}

.main {
  flex: 1;
  overflow: hidden;
  position: relative;
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
}
</style>
