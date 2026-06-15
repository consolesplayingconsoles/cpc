<script setup lang="ts">
import { computed } from 'vue'
import type { NodeData } from '../composables/useNodes'
import type { DeployResult } from '../composables/useDeploy'
import NodeBubble from './NodeBubble.vue'
import DeployTerminal from './DeployTerminal.vue'

const props = defineProps<{
  id:        string
  node:      NodeData
  icon?:     string
  output:    DeployResult | null
  deploying: boolean
  lastMs?:   number | null
}>()

const emit = defineEmits<{
  close:            []
  clear:            []
  deploy:           []
  'open-smb':       []
  'open-workspace': []
  'open-tab':       []
}>()

// Re-home the terminal: same component, flowing in the drawer (relative) rather
// than floating over the diagram (absolute) — so it never drifts on a dense map.
const TERM_STYLE = { position: 'relative', width: '100%', maxHeight: '320px', boxShadow: 'none' }

// Offline / unconfigured nodes can't act — deploy + files need the node reachable.
const offline = computed(() => props.node.status === 'down' || props.node.status === 'unconfigured')
const unconfigured = computed(() => props.node.status === 'unconfigured')
// Host vs console: deploying a console ships the Pluto python client to it.
const deployLabel = computed(() => props.id === 'pluto' ? 'Deploy Pluto' : 'Deploy Pluto Client')
// The vacuum has its own control surface — its commands live in the Dreame tab.
const isVacuum = computed(() => props.id === 'dreame')
const hasInfra = computed(() => props.node.deploy || props.node.folder || !!props.node.code)
</script>

<template>
  <aside class="nd" @click.stop>
    <button class="nd__x" title="Close" aria-label="Close" @click="emit('close')">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>
    </button>

    <!-- Header = the SAME bubble as the diagram (LED, OS badge, name, IP), just bigger. -->
    <header class="nd__head">
      <svg class="nd__bubble" viewBox="-60 -45 120 145" xmlns="http://www.w3.org/2000/svg">
        <NodeBubble :id="id" :node="node" :icon="icon" :is-hovered="false" :is-unconfigured="unconfigured" />
      </svg>
    </header>

    <section v-if="isVacuum || hasInfra" class="nd__sec">
      <p class="nd__lbl">Actions</p>

      <button v-if="isVacuum" class="nd__act" @click="emit('open-tab')">
        <svg class="nd__ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 8h9M19 8h1M4 16h5M15 16h5"/><circle cx="15" cy="8" r="2"/><circle cx="11" cy="16" r="2"/></svg>
        <span>Open Dreame Controls</span>
        <span class="nd__arrow">&rarr;</span>
      </button>

      <button v-if="node.deploy" class="nd__act" :disabled="deploying || offline" @click="emit('deploy')">
        <svg class="nd__ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l4 4M12 3l-4 4M12 3v12"/><path d="M5 21h14"/></svg>
        <span>{{ deployLabel }}</span>
        <span v-if="deploying" class="nd__act-note">Running…</span>
      </button>
      <button v-if="node.folder" class="nd__act" :disabled="offline" @click="emit('open-smb')">
        <svg class="nd__ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
        <span>Files</span>
      </button>
      <button v-if="node.code" class="nd__act" :disabled="offline" @click="emit('open-workspace')">
        <svg class="nd__ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 8l-4 4 4 4M16 8l4 4-4 4"/></svg>
        <span>Code</span>
      </button>
    </section>

    <section v-if="output" class="nd__sec nd__sec--term">
      <p class="nd__lbl">Deploy</p>
      <DeployTerminal
        :console-id="id"
        :output="output"
        :last-ms="lastMs"
        :card-style="TERM_STYLE"
        @close="emit('clear')"
      />
    </section>
  </aside>
</template>

<style scoped>
.nd {
  position: absolute;
  top: 0; right: 0; bottom: 0;
  width: 300px;
  z-index: 4;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border-left: 1px solid var(--line);
  box-shadow: -8px 0 28px rgba(26, 34, 51, 0.07);
  overflow-y: auto;
  padding: 18px 18px 22px;
}
.nd__x {
  position: absolute;
  top: 12px; right: 12px;
  width: 30px; height: 30px;
  display: flex; align-items: center; justify-content: center;
  color: var(--text-muted);
  background: transparent; border: 1px solid var(--line);
  border-radius: 8px; cursor: pointer;
  z-index: 1;
}
.nd__x:hover { background: var(--surface-2); color: var(--text); }
.nd__head { display: flex; justify-content: center; padding: 4px 0 2px; }
.nd__bubble { display: block; width: 168px; height: auto; pointer-events: none; }
.nd__sec { margin-top: 18px; }
.nd__sec--term { display: flex; flex-direction: column; }
.nd__lbl { font-size: 12px; font-weight: 600; letter-spacing: 0.02em; color: var(--text-faint); margin: 0 0 10px; }
.nd__act {
  display: flex; align-items: center; gap: 10px;
  width: 100%; margin-bottom: 8px; padding: 9px 12px;
  font-size: 14px; color: var(--text); text-align: left;
  background: var(--surface); border: 1px solid var(--line); border-radius: 10px; cursor: pointer;
}
.nd__act:hover:not(:disabled) { background: var(--surface-2); border-color: var(--line-strong); }
.nd__act:disabled { opacity: 0.5; cursor: default; }
.nd__ic { width: 18px; height: 18px; color: var(--accent); flex: 0 0 auto; }
.nd__act-note { margin-left: auto; font-size: 12px; color: var(--text-faint); }
.nd__arrow { margin-left: auto; color: var(--text-faint); }
</style>
