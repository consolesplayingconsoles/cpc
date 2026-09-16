// Per-ROM actions shared by the Media drawer and the game cards: open the ROM's folder and
// play it. One place, so a card and the drawer can never disagree about what's possible.
import { computed, ref, type Ref } from 'vue'
import type { CatalogueFile } from '../api/catalogue'
import { catalogueApi } from '../api/catalogue'
import { API_BASE, type NodeMap } from './useNodes'
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

  const REMOTE_BOOT = ['batocera']
  const canPlay = (f: CatalogueFile) => f.status === 'present' &&
    ((f.node === 'lab' && !!emulator.value) || REMOTE_BOOT.includes(f.node))
  const playTitle = (f: CatalogueFile) => f.node === 'lab' ? 'Play in ' + (emulator.value?.name ?? 'emulator') : 'Play on ' + (nodes.value[f.node]?.name ?? f.node)
  const canOpen = (f: CatalogueFile) => f.status === 'present' && (f.node === 'lab' || !!smbUrl(f))

  // Quit: stop whatever game is running on the node (Batocera), e.g. before testing a rebuild.
  const canQuit = (f: CatalogueFile) => f.status === 'present' && REMOTE_BOOT.includes(f.node)
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
    if (!url) return
    const a = document.createElement('a')
    a.href = url
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    a.remove()
  }

  return { emulator, canPlay, playTitle, canOpen, canQuit, play, quit, openFolder, actionError }
}
