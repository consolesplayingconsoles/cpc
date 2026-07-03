// Pure persistence logic for TranslationTable.vue — extracted here so it can be UNIT TESTED
// (TranslationTable.test.ts). These four bits are exactly what silently LOSE translations when they
// regress, so they live as pure functions guarded by tests instead of buried inline in the SFC.
// A red test here means a translation-eating regression; change the tests only when the behaviour
// change is deliberate.
import type { Block } from '../lib/translation'

// Absolute file offset -> the canonical on-disk state key. MUST stay `0x` + UPPERCASE, 6 hex digits:
// the extract returns an int, the state stores this string, and reconcile matches BY THIS STRING.
// Any drift (lowercase, different width) makes saved `ca` fail to overlay and look "cleared".
export function formatOffset(n: number): string {
  return '0x' + n.toString(16).toUpperCase().padStart(6, '0')
}

// Save payload = EVERY loaded tab, not just the active one. Under the manual-save model, edits pile
// up across tabs (mutated in place in tabBlocks) and only reach disk on Save. Sending just the active
// tab dropped the rest (menus reverted to their old state value). Skip a tab that never loaded (empty
// array) so an aborted extract can't wipe a source; the API deep-merges by key, so omitted keys stay.
export function buildSourcesPayload(tabBlocks: Record<string, Block[]>): Record<string, Block[]> {
  const out: Record<string, Block[]> = {}
  for (const [safe, arr] of Object.entries(tabBlocks)) {
    if (arr && arr.length) out[safe] = arr
  }
  return out
}

// Reconcile: a fresh extract (scene tags + jpBytes, empty ca) overlaid with any saved draft's
// ca/order/done BY OFFSET, so re-extracting to gain scene tags never loses translation work.
// Mutates + returns `fresh`. Unmatched fresh blocks keep their empty ca (new/moved lines).
export function reconcileByOffset(fresh: Block[], prior: Block[] | undefined | null): Block[] {
  if (prior && prior.length) {
    const byOff = new Map(prior.map(b => [b.offset, b]))
    for (const b of fresh) {
      const s = byOff.get(b.offset)
      if (s) { b.ca = s.ca || ''; b.order = s.order; b.done = s.done ?? b.done }
    }
  }
  return fresh
}

// External-poll merge: pull changed `ca` from saved state into the open table IN PLACE, but only when
// the arrays line up (same source, same length) so it can't scramble a re-extracted tab. Returns the
// count changed. NEVER call while there are unsaved local edits (dirty) — remote is stale then and
// this would revert them; the caller guards on `dirty`.
export function mergePolledCa(local: Block[] | undefined, remote: Block[] | undefined): number {
  if (!remote || !local || remote.length !== local.length) return 0
  let n = 0
  for (let i = 0; i < local.length; i++) {
    if (local[i].ca !== remote[i].ca) { local[i].ca = remote[i].ca; n++ }
  }
  return n
}
