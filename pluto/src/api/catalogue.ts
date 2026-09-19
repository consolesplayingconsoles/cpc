// REST wrappers for the /catalogue API (the Media tab). Same contract as translation.ts:
// one place for URLs, failures are THROWN so the tab can say "API unreachable" instead of
// showing an empty catalogue that looks real.
import { API_BASE } from '../composables/useNodes'

const BASE = `${API_BASE}/catalogue`
const enc = encodeURIComponent

export interface Variant { kind: 'mod' | 'translation'; name: string; version: string | null; author?: string | null; lang?: string }

export interface CatalogueFile {
  node: string
  path: string
  tags: string[]
  version: string | null          // the game's release version (TOSEC v1.001 / No-Intro Rev 1)
  regions: string[]
  variants: Variant[]
  variant: string                 // 'original' | 'T-Cat' | 'Boss Versus' | ...
  id: string | null
  headerTitle: string | null
  status: 'present' | 'deleted'
  card?: string | null            // SD card label when the node's games live on several cards
  firstSeen: string
  lastSeen: string
  save: string[]                  // nodes holding a save for this file's stem
  scraped?: { name: string | null; image: string | null; thumbnail: string | null }
}

// A shelf copy (catalogue/<system>/physical.json). status + notes are free text: "Complete",
// "Disc only", "Missing manual"... title = the Redump/No-Intro name, id = the serial.
export interface PhysicalItem { title: string; id?: string; format?: string; status?: string; notes?: string }

export interface Game {
  key: string
  title: string
  ids: string[]
  files: CatalogueFile[]
  physical: PhysicalItem[]
  nodes: string[]                 // nodes with a PRESENT file
  regions: string[]
  saves: string[]
  favourite: boolean
  kind: 'game' | 'tool'           // tools = boot discs, browsers, loaders (catalogue/kinds.json)
  label?: string | null           // Pluto's name for the game (labels.json); title already shows it
  fileTitle?: string              // the title read from its files, when a label overrides it
  meta: { genre?: string; developer?: string; publisher?: string; year?: string }
  cover: 'custom' | 'cached' | 'miss' | null   // custom = uploaded; null = never tried (URL fetches on first ask)
}

// favourite = starred on the grid; owned = you have the console (catalogue/hardware.json)
export interface SystemSummary {
  system: string; games: number; nodes: string[]; physical: number
  tools: number; translations: number; mods: number   // tools count inside games
  favourite: boolean; owned: boolean; hardware?: { status?: string; notes?: string } | null
}
// catalogue/hardware.json: your console for this system and the peripherals made for it
export interface HardwareConsole { model?: string; region?: string; status?: string; notes?: string }
export interface Peripheral { name: string; model?: string; systems: string[]; count?: number; storage?: string; status?: string; notes?: string }
export interface SystemView {
  system: string; games: Game[]; hosts: string[]; syncedAt: string | null
  hardware?: { console: HardwareConsole | null; peripherals: Peripheral[] }
}

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`GET ${url} -> ${r.status}`)
  return r.json() as Promise<T>
}

export interface MissingCover { system: string; key: string; title: string; info?: string }
export interface GameHit extends MissingCover { kind: 'game' | 'tool' }

export const catalogueApi = {
  systems: () => getJson<{ systems: SystemSummary[] }>(BASE),
  system:  (system: string) => getJson<SystemView>(`${BASE}/${enc(system)}`),
  missingCovers: () => getJson<{ games: MissingCover[] }>(`${BASE}/missing-covers`),
  // every system's games whose title/label contains q (accents and punctuation folded)
  search: (q: string) => getJson<{ games: GameHit[] }>(`${BASE}/search?q=${enc(q)}`),
  // games on a shelf with no digital copy on any node
  physicalOnly: () => getJson<{ games: MissingCover[] }>(`${BASE}/physical-only`),
  // consoles + peripherals as grid rows (system "" = general purpose)
  hardware: () => getJson<{ games: MissingCover[] }>(`${BASE}/hardware`),
  setSystemFavourite: async (system: string, on: boolean) => {
    const r = await fetch(`${BASE}/${enc(system)}/favourite-system`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ on }),
    })
    if (!r.ok) throw new Error(`favourite ${system} -> ${r.status}`)
  },
  setFavourite: async (system: string, game: string, on: boolean) => {
    const r = await fetch(`${BASE}/${enc(system)}/favourite`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ game, on }),
    })
    if (!r.ok) throw new Error(`favourite ${system}/${game} -> ${r.status}`)
  },
  // Set or clear ('') a game's label: Pluto's name for it, also what its art is matched on.
  setLabel: async (system: string, game: string, label: string) => {
    const r = await fetch(`${BASE}/${enc(system)}/label`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ game, label }),
    })
    if (!r.ok) throw new Error(`label ${system}/${game} -> ${r.status}`)
  },
  // node 'lab' = desktop emulator on the API host; 'batocera' = remote boot on the box.
  play: async (system: string, path: string, node = 'lab') => {
    const r = await fetch(`${BASE}/${enc(system)}/play`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path, node }),
    })
    if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.error || `play -> ${r.status}`)
  },
  // Send a lab ROM to a node's drive. The API can't write it (root only): it answers with the
  // Terminal command that does, which reports the drive back to the catalogue when done.
  // all = every lab game the node doesn't have yet, in one command (path ignored).
  // from = the node holding the copy (default lab); the API picks it up from there.
  send: async (system: string, path: string, node: string, all = false, from = 'lab') => {
    const body = all ? { node, all } : { node, files: [{ node: from, path }] }
    const r = await fetch(`${BASE}/${enc(system)}/send`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    })
    const j = await r.json().catch(() => ({}))
    if (!r.ok) throw new Error(j?.error || `send -> ${r.status}`)
    return j as { status: 'command' | 'done'; command?: string; count?: number; lines?: string[]; skipped?: { game: string; why: string }[] }
  },
  // Delete a copy: Lab to the Trash, another node for good. The API says when a node can't.
  deleteCopy: async (system: string, game: string, node: string, path: string) => {
    const r = await fetch(`${BASE}/${enc(system)}/delete`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ game, node, path }),
    })
    if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.error || `delete -> ${r.status}`)
  },
  // Remove a copy the last sync marked deleted (gone from that node's disk).
  forget: async (system: string, game: string, node: string, path: string) => {
    const r = await fetch(`${BASE}/${enc(system)}/forget`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ game, node, path }),
    })
    if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.error || `remove -> ${r.status}`)
  },
  openLocal: async (system: string, path: string) => {
    const r = await fetch(`${BASE}/${enc(system)}/open`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }),
    })
    if (!r.ok) throw new Error(`open ${system}/${path} -> ${r.status}`)
  },
  // v = cache-buster after an upload (the GET is browser-cached for a day)
  coverUrl: (system: string, game: string, v?: number) => `${BASE}/${enc(system)}/cover/${enc(game)}${v ? `?v=${v}` : ''}`,
  uploadCover: async (system: string, game: string, file: File) => {
    const r = await fetch(`${BASE}/${enc(system)}/cover/${enc(game)}`, {
      method: 'POST', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file,
    })
    if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.error || `upload -> ${r.status}`)
  },
  // The API downloads the image at a pasted link and stores it like an upload.
  coverFromUrl: async (system: string, game: string, url: string) => {
    const r = await fetch(`${BASE}/${enc(system)}/cover/${enc(game)}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }),
    })
    if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.error || `cover link -> ${r.status}`)
  },
  // SSE form of send (all = every game the node lacks): line events, a `command` event when
  // the target needs a Terminal command, then done ok/failed. Same console as sync.
  sendStreamUrl: (system: string, node: string) => `${BASE}/${enc(system)}/send/stream?node=${enc(node)}&all=1`,
  // SSE, read-only against nodes. '*' = everything Batocera has.
  syncUrl: (system: string) => `${BASE}/sync/stream?system=${enc(system)}`,
  // SSE. Saved games for ONE console: only the nodes that hold it and have a back-up
  // wired run ('*' = every node, everything it holds).
  savesUrl: (system: string) => `${BASE}/saves/stream?system=${enc(system)}`,
}
