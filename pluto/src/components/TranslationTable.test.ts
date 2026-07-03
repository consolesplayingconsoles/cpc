import { describe, it, expect } from 'vitest'
import { type Block, caBytes } from '../lib/translation'
import {
  formatOffset, buildSourcesPayload, reconcileByOffset, mergePolledCa,
} from './TranslationTable.logic'

// Minimal Block factory so tests read as data, not boilerplate.
function blk(offset: string, ca = '', extra: Partial<Block> = {}): Block {
  return { offset, speakerId: 0, jp: 'ジェイピー', jpBytes: 10, ca, ...extra }
}

describe('caBytes — full-width Shift-JIS cost (the byte meter depends on this)', () => {
  it('counts 2 bytes per character', () => {
    expect(caBytes('abc')).toBe(6)
    expect(caBytes('')).toBe(0)
  })
  it('folds accents to a single base char (stock font has no accented glyphs)', () => {
    expect(caBytes('à')).toBe(2)          // NOT 4 — à must cost the same as a
    expect(caBytes('Opció')).toBe(caBytes('Opcio'))
  })
})

describe('formatOffset — MUST match the on-disk state key format', () => {
  it('is 0x + UPPERCASE, zero-padded to 6 hex digits', () => {
    expect(formatOffset(24)).toBe('0x000018')
    expect(formatOffset(58)).toBe('0x00003A')   // uppercase A, not a
    expect(formatOffset(78)).toBe('0x00004E')
    expect(formatOffset(0x278)).toBe('0x000278')
  })
  it('round-trips against the extract int -> the reconcile key', () => {
    const stateKey = formatOffset(0x3b40c)      // extract returns int; state stores this string
    expect(stateKey).toBe('0x03B40C')
    expect(parseInt(stateKey, 16)).toBe(0x3b40c)
  })
})

describe('buildSourcesPayload — save EVERY loaded tab (the multi-tab regression)', () => {
  it('includes every tab that has blocks, not just one', () => {
    const out = buildSourcesPayload({
      'STORY.PAC': [blk('0x000018', 'Hola')],
      'DEFMENU.SCP': [blk('0x000028', 'Sac')],
    })
    expect(Object.keys(out).sort()).toEqual(['DEFMENU.SCP', 'STORY.PAC'])
  })
  it('skips a tab that never loaded (empty array) so an aborted extract cannot wipe a source', () => {
    const out = buildSourcesPayload({ 'STORY.PAC': [blk('0x1')], 'MENU.SCP': [] })
    expect(Object.keys(out)).toEqual(['STORY.PAC'])
    expect(out['MENU.SCP']).toBeUndefined()     // omitted, so the API keeps its saved value
  })
  it('returns an empty object when nothing is loaded (caller then skips the PUT)', () => {
    expect(buildSourcesPayload({})).toEqual({})
    expect(buildSourcesPayload({ a: [] })).toEqual({})
  })
})

describe('reconcileByOffset — re-extracting must NEVER drop saved ca', () => {
  it('overlays saved ca onto a fresh extract by offset', () => {
    const fresh = [blk('0x000018', ''), blk('0x000028', '')]
    reconcileByOffset(fresh, [blk('0x000018', 'Anar'), blk('0x000028', 'Sac')])
    expect(fresh.map(b => b.ca)).toEqual(['Anar', 'Sac'])
  })
  it('carries order + done alongside ca', () => {
    const fresh = [blk('0x000018', '')]
    reconcileByOffset(fresh, [blk('0x000018', 'Anar', { order: 3, done: true })])
    expect(fresh[0]).toMatchObject({ ca: 'Anar', order: 3, done: true })
  })
  it('leaves a fresh block with no saved match untouched (new/moved line, empty ca)', () => {
    const fresh = [blk('0x000099', '')]
    reconcileByOffset(fresh, [blk('0x000018', 'Anar')])
    expect(fresh[0].ca).toBe('')
  })
  it('no-ops on empty/undefined prior (first load) — never blanks the fresh blocks', () => {
    const fresh = [blk('0x000018', '')]
    expect(reconcileByOffset(fresh, undefined)).toBe(fresh)
    expect(reconcileByOffset(fresh, [])[0].ca).toBe('')
  })
  it('a lowercase/mismatched offset FAILS to overlay — the "translations look cleared" bug', () => {
    // Guards formatOffset: if the two sides ever disagree on case/width, ca silently vanishes.
    const fresh = [blk('0x00003A', '')]                 // extract/mapBlocks: uppercase
    reconcileByOffset(fresh, [blk('0x00003a', 'Info')]) // stale lowercase key
    expect(fresh[0].ca).toBe('')                        // proves why formatOffset must be exact
  })
})

describe('mergePolledCa — pull external edits without scrambling the table', () => {
  it('updates changed ca in place and reports the count', () => {
    const local = [blk('0x1', 'old'), blk('0x2', 'same')]
    const n = mergePolledCa(local, [blk('0x1', 'new'), blk('0x2', 'same')])
    expect(n).toBe(1)
    expect(local[0].ca).toBe('new')
  })
  it('does nothing when lengths differ (a re-extracted tab) — never index-scrambles', () => {
    const local = [blk('0x1', 'keep')]
    const n = mergePolledCa(local, [blk('0x1', 'x'), blk('0x2', 'y')])
    expect(n).toBe(0)
    expect(local[0].ca).toBe('keep')
  })
  it('handles missing local/remote safely', () => {
    expect(mergePolledCa(undefined, [blk('0x1')])).toBe(0)
    expect(mergePolledCa([blk('0x1')], undefined)).toBe(0)
  })
})
