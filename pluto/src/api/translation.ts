// REST wrappers for the /translate API. ONE place for every endpoint URL, its method/body/encoding,
// and error handling — so components don't inline `fetch`, the surface shrinks, and an API-down
// failure is a thrown Error the caller can surface (offline banner) instead of a silent swallow that
// loses translations. Keep this thin: no app state, no Vue — just typed HTTP.
import { API_BASE } from '../composables/useNodes'
import type { Block } from '../lib/translation'

const BASE = `${API_BASE}/translate`
const enc = encodeURIComponent
const JSON_HEADERS = { 'Content-Type': 'application/json' }

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`GET ${url} -> ${r.status}`)
  return r.json() as Promise<T>
}
async function sendJson<T>(method: string, url: string, body: unknown): Promise<T> {
  const r = await fetch(url, { method, headers: JSON_HEADERS, body: JSON.stringify(body) })
  if (!r.ok) throw new Error(`${method} ${url} -> ${r.status}`)
  return r.json() as Promise<T>
}

// Only the fields the workbench reads are typed; the rest of each payload passes through as unknown
// and the caller casts (the component owns those view types).
export type ExtractResp = { blocks?: unknown[]; scenes?: unknown[]; total?: number }
export type MeasureResp = { used?: Record<string, number>; line?: Record<string, number> }
export type MeasureBlock = Pick<Block, 'offset' | 'ca' | 'jpBytes'>

export const translationApi = {
  // discovery / listing
  listProjects: () => getJson<{ projects?: unknown[] }>(`${BASE}/projects`),
  listSystems:  () => getJson<{ systems?: unknown[] }>(`${BASE}/systems`),
  listGames:    (system: string) => getJson<{ games?: unknown[] }>(`${BASE}/games?system=${enc(system)}`),
  meta:         (path: string) => getJson<Record<string, unknown>>(`${BASE}/meta?path=${enc(path)}`),
  sources:      (path: string) => getJson<{ sources?: unknown[] }>(`${BASE}/sources?path=${enc(path)}`),
  extract:      (path: string, file: string) =>
                  getJson<ExtractResp>(`${BASE}/extract?path=${enc(path)}&file=${enc(file)}`),
  measure:      (path: string, file: string, blocks: MeasureBlock[]) =>
                  sendJson<MeasureResp>('POST', `${BASE}/measure?path=${enc(path)}&file=${enc(file)}`, { blocks }),

  // per-project state (the save path — getState/putState carry sources, speakers, tone, budgets)
  getState:    (ns: string) => getJson<Record<string, unknown>>(`${BASE}/${enc(ns)}`),
  putState:    (ns: string, body: unknown) => sendJson<Record<string, unknown>>('PUT', `${BASE}/${enc(ns)}`, body),
  createState: (ns: string, body: unknown) => sendJson<Record<string, unknown>>('POST', `${BASE}/${enc(ns)}`, body),

  // actions
  run:     (path: string) => sendJson<{ error?: string }>('POST', `${BASE}/run`, { path }),
  openDir: (ns: string) => fetch(`${BASE}/open`, { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ ns }) }),
  remove:  (ns: string) => fetch(`${BASE}/delete`, { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ ns }) }),
}
