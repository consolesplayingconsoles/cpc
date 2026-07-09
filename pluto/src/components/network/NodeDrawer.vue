<script setup lang="ts">
import { computed, ref } from 'vue'
import type { NodeData, NodeMap } from '../composables/useNodes'
import { API_BASE } from '../composables/useNodes'
import NodeBubble from './NodeBubble.vue'
import NodeCommand from './NodeCommand.vue'
import CopyButton from './CopyButton.vue'
import UiClose from './ui/UiClose.vue'
import UiActionRow from './ui/UiActionRow.vue'
import UiIconButton from './ui/UiIconButton.vue'
import chatConfig from '../../config/chat.json'

interface Cmd  { verb: string; desc?: string; target?: string; multiline?: boolean; url?: string; script?: string; credit?: string }
const NODE_ACTIONS = (chatConfig.nodeActions ?? {}) as Record<string, Cmd[]>
const HANDLES      = (chatConfig.mentions.handles ?? {}) as Record<string, string>

const props = defineProps<{
  id:        string
  node:      NodeData
  nodes:     NodeMap
  icon?:     string
  deploying: boolean
  lastMs?:   number | null   // duration of this node's last successful deploy
  lastAt?:   number | null   // when (epoch ms) it last deployed
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
// A node's payloads come from config/payloads.json (client, hub, ...), so the button
// stays generic -- "Deploy Pluto Node" -- rather than naming a payload. (The host
// keeps its instance label.)
const deployLabel = computed(() => props.id === 'pluto' ? 'Deploy Pluto C2' : 'Deploy Pluto Node')
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
// The retro page is served by each instance's own API, so it IS the local/stable build.
const retroLabel = computed(() => props.id === 'lab' ? 'Open Retro Web (local)' : 'Open Retro Web (stable)')
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

// The Wii is two machines in one: a Linux node (Wii-Linux: SSH deploy + SMB files) AND
// a native console (Homebrew/Nintendont: .dol flash + game library). Deploy/Files mean
// different things in each, so its drawer shows BOTH as separate sections rather than
// pretending they're one. The native side isn't built yet -- the buttons are real, and
// the API answers 'not implemented' (honest capability, not a hidden one).
const isWii = computed(() => props.id === 'wii')
const nativeNote = ref('')
function nativeAction(action: string) {
  nativeNote.value = ''
  fetch(`${API_BASE}/native/${props.id}/${action}`, { method: 'POST' })
    .then(r => r.json())
    .then(j => { nativeNote.value = j?.error || (j?.ok ? '' : 'failed') })
    .catch(() => { nativeNote.value = 'API unreachable' })
}

// Last-deploy line — general to any deployable node (pi, pluto, the python clients).
// The pi's covers its Picos too (their flashing is a step of the pi deploy).
const hasDeployInfo = computed(() => !!props.lastAt || !!props.lastMs)
function fmtAgo(at: number | null | undefined): string {
  if (!at) return ''
  const s = Math.max(0, Math.round((Date.now() - at) / 1000))
  if (s < 60) return 'just now'
  const m = Math.round(s / 60); if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60); if (h < 24) return `${h}h ago`
  return `${Math.round(h / 24)}d ago`
}
function fmtDur(ms: number | null | undefined): string {
  return ms ? `${Math.round(ms / 1000)}s` : ''
}

// Pico fleet (the Pi): each board declared in the node's .env, so you can see at a
// glance what every locally-deployed board is for and how it's managed/connected.
const picos = computed(() => props.node.picos ?? [])
// Colour HINT only, from the declared value -- never the source of the text. Anything
// unrecognized (incl. blank) styles neutral, so changing the .env value can't break it.
function deployClass(d: string) {
  const v = (d || '').toLowerCase()
  return v === 'pluto' ? 'is-pluto' : v === 'pi' ? 'is-pi' : 'is-unknown'
}

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
  const cmd = commands.value.find(c => c.verb === 'open-link' && text.includes('open-link'))
  if (cmd?.url) window.open(cmd.url, '_blank', 'noopener')
  fetch(`${API_BASE}/messages`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  }).catch(() => { /* best-effort; the chat feed reflects it on next poll */ })
}
</script>

<template>
  <aside class="nd" @click.stop @wheel.stop>
    <UiClose class="nd__x" title="Close" aria-label="Close" @click="emit('close')" />

    <!-- Header = the SAME bubble as the diagram (LED, OS badge, name, IP), just bigger. -->
    <header class="nd__head">
      <svg class="nd__bubble" viewBox="-60 -45 120 145" xmlns="http://www.w3.org/2000/svg">
        <NodeBubble :id="id" :node="node" :icon="icon" :is-hovered="false" :is-unconfigured="unconfigured" />
      </svg>
    </header>

    <p v-if="hasDeployInfo" class="nd__deploy-meta">
      Last deploy{{ lastAt ? ' ' + fmtAgo(lastAt) : '' }}{{ lastMs ? ' · ~' + fmtDur(lastMs) : '' }}
    </p>

    <!-- ── Instance nodes: two sections that spell the node — Pluto + (C2|Lab) ── -->
    <template v-if="isInstanceNode">
      <section class="nd__sec">
        <p class="nd__lbl">Pluto</p>
        <UiActionRow v-if="!isSelfInstance" :disabled="offline" @click="openExternal(dashUrl)">
          <svg class="nd__ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/></svg>
          <span>{{ dashLabel }}</span>
          <span class="nd__ext">&#8599;</span>
        </UiActionRow>
        <UiActionRow @click="openExternal(retroUrl)">
          <svg class="nd__ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 9h2M7 13h4"/><circle cx="16" cy="10" r="1.3"/><circle cx="16" cy="14" r="1.3"/></svg>
          <span>{{ retroLabel }}</span>
          <span class="nd__ext">&#8599;</span>
        </UiActionRow>
      </section>

      <section v-if="instanceHasOps" class="nd__sec">
        <div class="nd__lbl-row">
          <p class="nd__lbl">{{ instanceSuffix }}</p>
          <!-- "Lab" + folder + gear reads as "Lab config dir": the section label IS
               the label, the icon (no text) is the action — open it in your IDE. -->
          <UiIconButton v-if="showLabConfig" variant="bordered" class="nd__cfg" title="Open the Lab config folder in your disk" @click="emit('open-config')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 6A1.5 1.5 0 0 1 4.5 4.5H7.5L9 6h3.5A1.5 1.5 0 0 1 14 7.5V9"/>
              <path d="M3 6v8A1.5 1.5 0 0 0 4.5 15.5H8"/>
              <circle cx="15.5" cy="15.5" r="4.6"/>
              <circle cx="15.5" cy="15.5" r="1.4" fill="currentColor" stroke="none"/>
              <path d="M15.5 9.3v1.6M15.5 20.1v1.6M21.7 15.5h-1.6M10.9 15.5H9.3M19.9 11.1l-1.1 1.1M12.2 18.8l-1.1 1.1M19.9 19.9l-1.1-1.1M12.2 12.2l-1.1-1.1"/>
            </svg>
          </UiIconButton>
        </div>
        <UiActionRow v-if="showDeploy" :disabled="deploying || offline" @click="emit('deploy')">
          <svg class="nd__ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l4 4M12 3l-4 4M12 3v12"/><path d="M5 21h14"/></svg>
          <span>{{ deployLabel }}</span>
          <span v-if="deploying" class="nd__act-note">Running…</span>
        </UiActionRow>
      </section>
    </template>

    <!-- ── Every other node: flat infra actions + chat commands ── -->
    <template v-else>
      <!-- The Wii is dual-natured: a Linux node (SSH deploy + SMB files) AND a native
           console (homebrew flash + game library). Two sections so Deploy/Files read
           honestly per mode; the native side isn't built, so the API says so. -->
      <template v-if="isWii">
        <section class="nd__sec">
          <p class="nd__lbl">Linux</p>
          <UiActionRow v-if="node.deploy" :disabled="deploying || offline" @click="emit('deploy')">
            <svg class="nd__ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l4 4M12 3l-4 4M12 3v12"/><path d="M5 21h14"/></svg>
            <span>{{ deployLabel }}</span>
            <span v-if="deploying" class="nd__act-note">Running…</span>
          </UiActionRow>
          <UiActionRow v-if="node.folder" :disabled="offline" @click="emit('open-smb')">
            <svg class="nd__ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
            <span>Files</span>
          </UiActionRow>
          <p v-if="!node.deploy && !node.folder" class="nd__hint">No SSH or SMB configured.</p>
        </section>

        <section class="nd__sec">
          <p class="nd__lbl">System</p>
          <UiActionRow :disabled="offline" @click="nativeAction('flash')">
            <svg class="nd__ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2L4 14h7l-1 8 9-12h-7z"/></svg>
            <span>Flash Homebrew</span>
          </UiActionRow>
          <UiActionRow :disabled="offline" @click="nativeAction('games')">
            <svg class="nd__ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2.4"/></svg>
            <span>Game Library</span>
          </UiActionRow>
          <p v-if="nativeNote" class="nd__hint">{{ nativeNote }}</p>
        </section>
      </template>

      <section v-else-if="isVacuum || hasInfra" class="nd__sec">
        <p class="nd__lbl">Actions</p>

        <UiActionRow v-if="isVacuum" @click="emit('open-tab')">
          <svg class="nd__ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 8h9M19 8h1M4 16h5M15 16h5"/><circle cx="15" cy="8" r="2"/><circle cx="11" cy="16" r="2"/></svg>
          <span>Open Dreame Controls</span>
          <span class="nd__arrow">&rarr;</span>
        </UiActionRow>

        <UiActionRow v-if="node.deploy" :disabled="deploying || offline" @click="emit('deploy')">
          <svg class="nd__ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l4 4M12 3l-4 4M12 3v12"/><path d="M5 21h14"/></svg>
          <span>{{ deployLabel }}</span>
          <span v-if="deploying" class="nd__act-note">Running…</span>
        </UiActionRow>
        <UiActionRow v-if="node.folder" :disabled="offline" @click="emit('open-smb')">
          <svg class="nd__ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
          <span>Files</span>
        </UiActionRow>
      </section>

      <section v-if="picos.length" class="nd__sec">
        <p class="nd__lbl">Picos</p>
        <div v-for="p in picos" :key="p.chipid" class="nd__pico">
          <!-- Title = alias (human name) when set, with the chip id shown after it in
               parens (still nice to see the real id); just the chip id when no alias.
               The copy button ALWAYS copies the chip id, whatever shows. -->
          <div class="nd__pico-id">
            <span class="nd__pico-id-text" :class="{ 'is-alias': p.alias }">{{ p.alias || p.chipid }}</span>
            <span v-if="p.alias" class="nd__pico-id-sub">({{ p.chipid }})</span>
            <CopyButton :text="p.chipid" :title="'copy chip id\n' + p.chipid" />
          </div>
          <div class="nd__pico-main">
            <span class="nd__pico-role">{{ p.role || 'unassigned' }}</span>
            <span v-if="p.iface" class="nd__pico-badge is-iface" title="HID mode the board presents to the console (generic / ps3 / switch …)">{{ p.iface }}</span>
            <span class="nd__pico-badge" :class="deployClass(p.deploy)"
                  :title="p.deploy === 'pluto' ? 'Flashed by the Pluto deploy pipeline (firmware/' + p.role + '/ exists)'
                        : p.deploy === 'pi' ? 'Deployed locally on the Pi — Pluto does not flash it'
                        : 'Deploy ownership not determinable here'">
              {{ p.deploy || 'deploy?' }}
            </span>
            <span class="nd__pico-badge is-conn">{{ p.conn || 'conn?' }}</span>
            <span v-if="(p.conn || '').toLowerCase() === 'uart'" class="nd__pico-uart">{{ p.dev || 'no dev' }}<template v-if="p.baud">@{{ p.baud }}</template></span>
          </div>
        </div>
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
/* position only — the close look comes from UiClose */
.nd__x { position: absolute; top: 12px; right: 12px; z-index: 1; }
.nd__head { display: flex; justify-content: center; padding: 4px 0 2px; }
.nd__bubble { display: block; width: 168px; height: auto; pointer-events: none; }
.nd__deploy-meta { margin: 0; text-align: center; font-family: var(--font-mono); font-size: 11px; color: var(--text-faint); }
.nd__sec { margin-top: 18px; }
.nd__lbl { font-size: 12px; font-weight: 600; letter-spacing: 0.02em; color: var(--text-faint); margin: 0 0 10px; }
.nd__hint { margin: 2px 0 0; font-size: 12px; color: var(--text-faint); }
/* the action-row frame is now UiActionRow; these are the row CONTENTS */
.nd__ic { width: 18px; height: 18px; color: var(--accent); flex: 0 0 auto; }
.nd__act-note { margin-left: auto; font-size: 12px; color: var(--text-faint); }
.nd__arrow { margin-left: auto; color: var(--text-faint); }
.nd__ext { margin-left: auto; color: var(--text-faint); font-size: 13px; }
/* the config shortcut rides in the "Lab" section header — label + folder-gear icon
   together read as "Lab config dir". A quiet icon button, no text, no full row. */
.nd__lbl-row { display: flex; align-items: center; gap: 9px; margin-bottom: 10px; }
.nd__lbl-row .nd__lbl { margin: 0; }
/* frame is UiIconButton; just size the gear glyph */
.nd__cfg svg { width: 19px; height: 19px; flex: 0 0 auto; }

/* Pico fleet rows: one card per declared board. The chip id is the board's identity,
   so it leads in full; role + deploy ownership + connection follow as attributes. */
.nd__pico { padding: 8px 10px; margin-bottom: 8px; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; }
.nd__pico-id { display: flex; align-items: center; gap: 4px; margin-bottom: 5px; }
.nd__pico-id-text { font-family: var(--font-mono); font-size: 12.5px; font-weight: 600; color: var(--text); word-break: break-all; }
/* an alias is a human NAME, not an ID -> sans + a touch larger; raw chip-id fallback stays mono. */
.nd__pico-id-text.is-alias { font-family: var(--font-sans); font-size: 13.5px; word-break: normal; }
/* the chip id shown after an alias: mono + muted, the data behind the name. */
.nd__pico-id-sub { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); word-break: break-all; }
.nd__pico-main { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 8px; }
.nd__pico-role { font-size: 13px; font-weight: 600; color: var(--text-muted); }
/* Pills: every badge carries the SAME visible border (surface-3 fill, line-strong
   border, strong text) so they read crisply in light mode too -- pluto is the one
   accent-tinted state, unknown is a dashed ghost. No more invisible off-white chips. */
.nd__pico-badge { font-size: 10px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; padding: 2px 7px; border-radius: 6px; border: 1px solid var(--line-strong); background: var(--surface-3); color: var(--text); }
.nd__pico-badge.is-pluto   { color: var(--accent); background: var(--accent-soft); border-color: var(--accent); }
.nd__pico-badge.is-unknown { color: var(--text-muted); background: transparent; border-style: dashed; }
/* HID mode (generic/ps3/switch): the profile the board presents to the console. */
.nd__pico-badge.is-iface { color: var(--accent); background: var(--accent-soft); border-color: var(--accent); }
.nd__pico-uart { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); }
</style>
