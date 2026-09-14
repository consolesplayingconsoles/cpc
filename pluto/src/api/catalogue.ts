// REST wrappers for the /catalogue API (the Media tab). Same contract as translation.ts:
// one place for URLs, failures are THROWN so the tab can say "API unreachable" instead of
// showing an empty catalogue that looks real.
import { API_BASE } from '../composables/useNodes'

const BASE = `${API_BASE}/catalogue`
const enc = encodeURIComponent

export interface Variant { kind: 'mod' | 'translation'; name: string; version: string | null; author?: string | null }

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
  firstSeen: string
  lastSeen: string
  save: string[]                  // nodes holding a save for this file's stem
  scraped?: { name: string | null; image: string | null; thumbnail: string | null }
}

export interface PhysicalItem { title: string; id?: string; format?: string; notes?: string }

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
  cover: 'custom' | 'cached' | 'miss' | null   // custom = uploaded; null = never tried (URL fetches on first ask)
}

export interface SystemSummary { system: string; games: number; nodes: string[]; physical: number }
export interface SystemView { system: string; games: Game[]; hosts: string[]; syncedAt: string | null }

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`GET ${url} -> ${r.status}`)
  return r.json() as Promise<T>
}

export const catalogueApi = {
  systems: () => getJson<{ systems: SystemSummary[] }>(BASE),
  system:  (system: string) => getJson<SystemView>(`${BASE}/${enc(system)}`),
  setFavourite: async (system: string, game: string, on: boolean) => {
    const r = await fetch(`${BASE}/${enc(system)}/favourite`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ game, on }),
    })
    if (!r.ok) throw new Error(`favourite ${system}/${game} -> ${r.status}`)
  },
  play: async (system: string, path: string) => {
    const r = await fetch(`${BASE}/${enc(system)}/play`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path }),
    })
    if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.error || `play -> ${r.status}`)
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
  // SSE, read-only against nodes. '*' = everything Batocera has.
  syncUrl: (system: string) => `${BASE}/sync/stream?system=${enc(system)}`,
}
