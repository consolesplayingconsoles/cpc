// Per-ROM actions shared by the Media drawer and the game cards: open the ROM's folder and
// play it. One place, so a card and the drawer can never disagree about what's possible.
import { computed, ref, type Ref } from 'vue'
import type { CatalogueFile } from '../api/catalogue'
import { catalogueApi } from '../api/catalogue'
import { API_BASE, type NodeMap } from './useNodes'
import { useAchievement } from './useAchievement'
import consolesConfig from '../../config/consoles.json'

// Open the ROM's FOLDER (not the file, so Finder doesn't try to launch a .chd). Any node
// with an SMB share (node.smb, the same field as the network drawer's Files button)
// gets a client-side smb:// link: Batocera straight to share/roms/<system>/<dir>, other
// nodes to their share root until their ROM layout is known. The lab node has no share
// (it IS the API host), so it asks the API to open the folder there.
const ROM_DIRS: Record<string, (system: string) => string[]> = {
  batocera: (system) => ['share', 'roms', system],
}

export function useRomActions(system: Ref<string>, nodes: Ref<NodeMap>) {
  function smbUrl(f: CatalogueFile): string | null {
    const base = nodes.value[f.node]?.smb
    if (!base) return null
    const layout = ROM_DIRS[f.node]
    const parts = layout ? [...layout(system.value), ...f.path.split('/').slice(0, -1)] : []
    return [base.replace(/\/+$/, ''), ...parts.map(encodeURIComponent)].join('/') + '/'
  }

  // Play: lab files in the desktop emulator config associates with the system
  // (systems.<x>.emulator, else defaultEmulator); Batocera files boot remotely on the box.
  // Not gated on the node's ping status: you can always press it, a failure says why.
  const emulator = computed(() => {
    const key = (consolesConfig.systems as Record<string, { emulator?: string }>)[system.value]?.emulator ?? consolesConfig.defaultEmulator
    return key ? (consolesConfig.emulators as Record<string, { name: string }>)[key] ?? null : null
  })

  // Nodes Pluto can boot a game on: Batocera through EmulationStation's web API, the PS3
  // through webMAN. Never ping-gated -- press it and let the API say why not.
  const REMOTE_BOOT = ['batocera', 'ps3']
  const canPlay = (f: CatalogueFile) => f.status === 'present' &&
    ((f.node === 'lab' && !!emulator.value) || REMOTE_BOOT.includes(f.node))
  const playTitle = (f: CatalogueFile) => f.node === 'lab' ? 'Play in ' + (emulator.value?.name ?? 'emulator') : 'Play on ' + (nodes.value[f.node]?.name ?? f.node)
  const canOpen = (f: CatalogueFile) => f.status === 'present' && (f.node === 'lab' || !!smbUrl(f))

  // Quit: stop whatever game is running on the node (Batocera), e.g. before testing a
  // rebuild. Only Batocera can be told to quit; a PS3 game ends from the console.
  const canQuit = (f: CatalogueFile) => f.status === 'present' && f.node === 'batocera'
  function quit(f: CatalogueFile) {
    actionError.value = ''
    fetch(`${API_BASE}/native/${f.node}/quit-game`, { method: 'POST' })
      .then(r => r.json()).then(j => { if (!j?.ok) actionError.value = j?.error || 'quit failed' })
      .catch(() => { actionError.value = 'API unreachable' })
  }

  const actionError = ref('')
  function play(f: CatalogueFile) {
    actionError.value = ''
    catalogueApi.play(system.value, f.path, f.node).catch(err => { actionError.value = (err as Error).message })
  }
  function openFolder(f: CatalogueFile) {
    actionError.value = ''
    if (f.node === 'lab') {
      catalogueApi.openLocal(system.value, f.path).catch(err => { actionError.value = (err as Error).message })
      return
    }
    const url = smbUrl(f)
    if (!url) { actionError.value = `No folder access on ${nodes.value[f.node]?.name ?? f.node} (no SMB share)`; return }
    const a = document.createElement('a')
    a.href = url
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    a.remove()
  }

  // Send: a lab ROM to a node that takes games on its drive (node.send, the PS2 HDD) and hosts
  // this system. The API can't write that drive: it answers with the Terminal command to run.
  const hosts = (consolesConfig as { nodeConsoles?: Record<string, string[]> }).nodeConsoles ?? {}
  const sendTargets = computed(() => Object.values(nodes.value)
    .filter(n => n.send && ((hosts[n.id] ?? []).includes(system.value) || (hosts[n.id] ?? []).includes('*')) &&
      (!n.sendSystems || n.sendSystems.includes(system.value))))
  const canSend = (f: CatalogueFile) => f.status === 'present' && f.node === 'lab'
  // The API answers either with a Terminal command (PS2 drive: root only) or having done the
  // copy itself (SD card): then the success banner, and sentAt tells the page to reload.
  const sendCommand = ref('')
  const sending = ref('')                                   // target node id while a send runs
  const sentAt = ref(0)
  const { unlock } = useAchievement()
  function send(f: CatalogueFile | null, node: string) {    // null = every game the node lacks
    actionError.value = ''
    sendCommand.value = ''
    sending.value = node
    const startedAt = Date.now()
    catalogueApi.send(system.value, f?.path ?? '', node, !f, f?.node ?? 'lab')
      .then(r => {
        if (r.status === 'command') sendCommand.value = r.command ?? ''
        else {
          sentAt.value = Date.now()
          unlock(`Sent ${r.count ?? 0} game${r.count === 1 ? '' : 's'} to ${nodes.value[node]?.name ?? node}`, `${Math.round((Date.now() - startedAt) / 1000)}s`)
        }
      })
      .catch(err => { actionError.value = (err as Error).message })
      .finally(() => { sending.value = '' })
  }

  return { emulator, canPlay, playTitle, canOpen, canQuit, play, quit, openFolder, actionError, sendTargets, canSend, send, sendCommand, sending, sentAt }
}
