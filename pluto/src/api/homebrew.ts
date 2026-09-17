// REST wrappers for the /homebrew API (Mods, Games and Tools tabs). Same contract as
// catalogue.ts: one place for URLs, failures are THROWN so the tab can say so.
import { API_BASE } from '../composables/useNodes'

const BASE = `${API_BASE}/homebrew`
const enc = encodeURIComponent

export type HomebrewKind = 'mods' | 'games' | 'tools'
export type HomebrewAction = 'build'   // scripts present in the folder

export interface HomebrewParam {
  key: string
  default: string
  value: string
  help: string            // the comment lines above the key in .env.sample
  scope: 'game' | 'item'  // game = shared by every mod of the game (mods/<game>/.env)
}

export interface HomebrewRelease {
  url: string
  name: string
  version: string | null  // "1.0", "1.0-beta"
  stable: boolean         // false = only a pre-release exists
}

export interface HomebrewGame {
  system: string          // catalogue system, e.g. "megadrive"
  key: string             // catalogue game key, e.g. "sonic-the-hedgehog"
  title: string           // catalogue title (the key if the game isn't listed)
  listed: boolean         // present in the catalogue: cover + Media link work
}

export interface HomebrewOutput {
  path: string            // the file the last build announced (##OUTPUT:)
  at: string              // when, local time
}

export interface HomebrewTarget {
  id: string              // node id, "lab" first
  name: string
  kind: string            // catalogue send strategy (batocera | sd), or "script" for deploy.sh
}

export interface HomebrewItem {
  id: string              // "<node>/<kind>/<game>/<mod>" or "<node>/<kind>/<name>"
  node: string
  nodeName: string        // the console's full name, e.g. "Mega Drive"
  kind: HomebrewKind
  group: string | null    // the game, for mods
  name: string
  title: string           // README.md heading, else the folder name
  description: string | null
  path: string            // repo-relative folder
  actions: HomebrewAction[]
  params: HomebrewParam[]
  paramsPaths: string[]   // the .env files the params are saved to (game's, then its own)
  running: boolean
  release: HomebrewRelease | null   // from a RELEASE file: newest stable GitHub release
  game: HomebrewGame | null         // from the game's CATALOGUE file
  output: HomebrewOutput | null     // last build output, if the file still exists
  sendTargets: HomebrewTarget[]     // nodes Send can take it to (catalogue send, or its deploy.sh)
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try { msg = (await res.json()).error || msg } catch { /* not json */ }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

export async function listItems(): Promise<HomebrewItem[]> {
  return (await json<{ items: HomebrewItem[] }>(await fetch(BASE))).items
}

export async function saveParams(id: string, values: Record<string, string>): Promise<HomebrewItem> {
  return json<HomebrewItem>(await fetch(`${BASE}/params?id=${enc(id)}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ values }),
  }))
}

export async function stopItem(id: string): Promise<boolean> {
  return (await json<{ stopped: boolean }>(await fetch(`${BASE}/stop?id=${enc(id)}`, { method: 'POST' }))).stopped
}

// Start: the last build, straight from its dev tree (no rebuild, nothing copied), in the
// system's desktop emulator. The API says why when it can't (nothing built, no emulator).
export async function startItem(id: string): Promise<void> {
  await json<{ ok: boolean }>(await fetch(`${BASE}/start?id=${enc(id)}`, { method: 'POST' }))
}

// output: the last build's folder instead of the item's source folder
export async function openFolder(id: string, output = false): Promise<void> {
  await json<{ opened: string }>(await fetch(`${BASE}/open?id=${enc(id)}${output ? '&output=1' : ''}`, { method: 'POST' }))
}

// Build (no node): build, publish to Lab, sync. Send (node): the same, then send it there.
export function streamUrl(id: string, node?: string): string {
  return `${BASE}/stream?id=${enc(id)}${node ? `&node=${enc(node)}` : ''}`
}
