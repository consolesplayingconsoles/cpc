<script setup lang="ts">
import { computed } from 'vue'
import type { NodeData, NodeMap } from '../composables/useNodes'
import { API_BASE } from '../composables/useNodes'
import NodeBubble from './NodeBubble.vue'
import NodeCommand from './NodeCommand.vue'
import chatConfig from '../../config/chat.json'

interface Cmd { verb: string; desc?: string; target?: string; multiline?: boolean; done?: boolean }
const NODE_ACTIONS = (chatConfig.nodeActions ?? {}) as Record<string, Cmd[]>
const HANDLES      = (chatConfig.mentions.handles ?? {}) as Record<string, string>

const props = defineProps<{
  id:        string
  node:      NodeData
  nodes:     NodeMap
  icon?:     string
  deploying: boolean
}>()

const emit = defineEmits<{
  close:         []
  deploy:        []
  'open-smb':    []
  'open-config': []
  'open-tab':    []
}>()

// Offline / unconfigured nodes can't act — deploy + files need the node reachable.
const offline = computed(() => props.node.status === 'down' || props.node.status === 'unconfigured')
const unconfigured = computed(() => props.node.status === 'unconfigured')
// Host vs console: deploying a console ships the Pluto python client to it.
const deployLabel = computed(() => props.id === 'pluto' ? 'Deploy Pluto C2' : 'Deploy Pluto Client')
// The vacuum has its own control surface — its commands live in the Dreame view.
// Both vacuum nodes open it: `dreame` (the L40 on the LAN) and `dreamehome` (its cloud).
const isVacuum = computed(() => props.id === 'dreame' || props.id === 'dreamehome')

// ── The two Pluto instances are first-class nodes ────────────────────────────
// Their drawers read by INTENT, not verb type: a "Pluto" section (the running
// dashboard's web surfaces) + a section named after the instance itself — so the
// two headers spell the node: Pluto + C2, Pluto + Lab. `selfId` is the instance
// we're viewing FROM (Lab under vite, C2 in the deployed dist), so we never offer
// to open the dashboard you're already on, and Lab tooling only shows on the Lab.
const selfId = import.meta.env.DEV ? 'lab' : 'pluto'
const isInstanceNode = computed(() => props.id === 'pluto' || props.id === 'lab')
const isSelfInstance = computed(() => props.id === selfId)
const instanceSuffix = computed(() => props.id === 'pluto' ? 'C2' : 'Lab')
const instanceHost   = computed(() => props.node.ip || window.location.hostname)
const dashUrl   = computed(() =>
  props.id === 'pluto' ? `http://${instanceHost.value}:5173`
  : props.id === 'lab' ? `http://${instanceHost.value}:5174` : '')
const dashLabel  = computed(() => props.id === 'pluto' ? 'Open Pluto C2' : 'Open Pluto Lab')
const retroUrl   = computed(() => `http://${instanceHost.value}:7700/retro`)
// The retro page is served by each instance's own API, so it IS the dev/prod build.
const retroLabel = computed(() => props.id === 'lab' ? 'Open Retro Web (dev)' : 'Open Retro Web (prod)')
function openExternal(url: string) {
  if (url) window.open(url, '_blank', 'noopener')
}

// What fills the instance-named (C2 / Lab) section: the C2 is maintained by Deploy
// (Lab instance only); the Lab is the dev bench, so it gets the config shortcut.
const showDeploy    = computed(() => props.id === 'pluto' && props.node.deploy)
const showLabConfig = computed(() => props.id === 'lab' && isSelfInstance.value)
const instanceHasOps = computed(() => showDeploy.value || showLabConfig.value)

// Non-instance nodes keep the flat layout: their infra actions + chat commands.
const hasInfra = computed(() => props.node.deploy || props.node.folder)

// Node commands (the chat verbs) surface here too — DRY: same chat.json registry,
// same dispatch. Each posts "@handle verb [arg]" to /messages (logged in the chat
// feed AND messages.log). The vacuum is the exception: its commands live in the tab.
const commands = computed(() => isVacuum.value ? [] : (NODE_ACTIONS[props.id] ?? []))
const handle   = computed(() => '@' + (HANDLES[props.id] ?? props.id))
const targets  = computed(() => [
  { label: 'Everyone', value: '@everyone' },
  ...Object.entries(props.nodes)
    .filter(([id, n]) => id !== 'gateway' && id !== 'cloud' && id !== 'pluto' && id !== 'lab' && id !== props.id && !n.cloud)
    .map(([id, n]) => ({ label: n.name, value: '@' + (HANDLES[id] ?? id) })),
])
function postCommand(text: string) {
  fetch(`${API_BASE}/messages`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  }).catch(() => { /* best-effort; the chat feed reflects it on next poll */ })
}
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

    <!-- ── Instance nodes: two sections that spell the node — Pluto + (C2|Lab) ── -->
    <template v-if="isInstanceNode">
      <section class="nd__sec">
        <p class="nd__lbl">Pluto</p>
        <button v-if="!isSelfInstance" class="nd__act" :disabled="offline" @click="openExternal(dashUrl)">
          <svg class="nd__ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/></svg>
          <span>{{ dashLabel }}</span>
          <span class="nd__ext">&#8599;</span>
        </button>
        <button class="nd__act" @click="openExternal(retroUrl)">
          <svg class="nd__ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 9h2M7 13h4"/><circle cx="16" cy="10" r="1.3"/><circle cx="16" cy="14" r="1.3"/></svg>
          <span>{{ retroLabel }}</span>
          <span class="nd__ext">&#8599;</span>
        </button>
      </section>

      <section v-if="instanceHasOps" class="nd__sec">
        <div class="nd__lbl-row">
          <p class="nd__lbl">{{ instanceSuffix }}</p>
          <!-- "Lab" + folder + gear reads as "Lab config dir": the section label IS
               the label, the icon (no text) is the action — open it in your IDE. -->
          <button v-if="showLabConfig" class="nd__cfg" title="Open the Lab config folder in your IDE" @click="emit('open-config')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 7.5A1.5 1.5 0 0 1 4.5 6H8l1.5 1.6h6A1.5 1.5 0 0 1 17 9v2.2"/>
              <path d="M3 7.5V15a1.5 1.5 0 0 0 1.5 1.5H10.5"/>
              <circle cx="17.5" cy="16.5" r="3.2"/>
              <circle cx="17.5" cy="16.5" r="0.95" fill="currentColor" stroke="none"/>
              <path d="M17.5 12.6v1.1M17.5 19.4v1.1M13.6 16.5h1.1M20.3 16.5h1.1M14.8 13.8l.8.8M19.4 18.4l.8.8M20.2 13.8l-.8.8M14.8 19.2l.8-.8"/>
            </svg>
          </button>
        </div>
        <button v-if="showDeploy" class="nd__act" :disabled="deploying || offline" @click="emit('deploy')">
          <svg class="nd__ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l4 4M12 3l-4 4M12 3v12"/><path d="M5 21h14"/></svg>
          <span>{{ deployLabel }}</span>
          <span v-if="deploying" class="nd__act-note">Running…</span>
        </button>
      </section>
    </template>

    <!-- ── Every other node: flat infra actions + chat commands ── -->
    <template v-else>
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
      </section>

      <section v-if="commands.length" class="nd__sec">
        <p class="nd__lbl">Commands</p>
        <NodeCommand
          v-for="c in commands" :key="c.verb"
          :handle="handle" :cmd="c" :targets="targets"
          @run="postCommand"
        />
      </section>
    </template>
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
.nd__ext { margin-left: auto; color: var(--text-faint); font-size: 13px; }
/* the config shortcut rides in the "Lab" section header — label + folder-gear icon
   together read as "Lab config dir". A quiet icon button, no text, no full row. */
.nd__lbl-row { display: flex; align-items: center; gap: 9px; margin-bottom: 10px; }
.nd__lbl-row .nd__lbl { margin: 0; }
.nd__cfg {
  display: inline-flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; padding: 0;
  color: var(--text-muted);
  background: var(--surface); border: 1px solid var(--line); border-radius: 8px; cursor: pointer;
}
.nd__cfg:hover { background: var(--surface-2); border-color: var(--line-strong); color: var(--accent); }
.nd__cfg svg { width: 19px; height: 19px; flex: 0 0 auto; }
</style>
