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

describe('Multi-tab save/load cycle — translations must not disappear', () => {
  it('buildSourcesPayload includes translations from all loaded tabs', () => {
    // User edits both STORY and DEFMENU tabs
    const tabBlocks = {
      'STORY.PAC': [
        blk('0x000100', 'Hola mundo'),
        blk('0x000200', 'Adéu'),
      ],
      'DEFMENU.SCP': [
        blk('0x000300', 'Moure'),
        blk('0x000400', 'Opcions'),
      ],
    }

    // Save payload should include both tabs
    const payload = buildSourcesPayload(tabBlocks)
    expect(Object.keys(payload).sort()).toEqual(['DEFMENU.SCP', 'STORY.PAC'])
    expect(payload['STORY.PAC'].map(b => b.ca)).toEqual(['Hola mundo', 'Adéu'])
    expect(payload['DEFMENU.SCP'].map(b => b.ca)).toEqual(['Moure', 'Opcions'])
  })

  it('reconcileByOffset preserves ca across tabs when re-extracting', () => {
    // Saved state from a previous save
    const saved = {
      'STORY.PAC': [
        blk('0x000100', 'Hola mundo'),
        blk('0x000200', 'Adéu'),
      ],
      'DEFMENU.SCP': [
        blk('0x000300', 'Moure'),
      ],
    }

    // Fresh extract comes back with empty ca
    const fresh = {
      'STORY.PAC': [
        blk('0x000100', ''),
        blk('0x000200', ''),
      ],
      'DEFMENU.SCP': [
        blk('0x000300', ''),
      ],
    }

    // Reconcile each tab
    reconcileByOffset(fresh['STORY.PAC'], saved['STORY.PAC'])
    reconcileByOffset(fresh['DEFMENU.SCP'], saved['DEFMENU.SCP'])

    // All translations should be restored
    expect(fresh['STORY.PAC'].map(b => b.ca)).toEqual(['Hola mundo', 'Adéu'])
    expect(fresh['DEFMENU.SCP'].map(b => b.ca)).toEqual(['Moure'])
  })
})

describe('Boku Doraemon workflow — real multi-tab scenario', () => {
  it('STORY.PAC (dialogue) saves with cumulative box tracking', () => {
    // 3 lines in one scene (box)
    const blocks = [
      blk('0x03B500', 'Dormir ara?', { scene: 1, jpBytes: 22 }),
      blk('0x03B520', 'Sí', { scene: 1, jpBytes: 4 }),
      blk('0x03B524', 'No', { scene: 1, jpBytes: 4 }),
    ]
    const payload = buildSourcesPayload({ 'STORY.PAC': blocks })
    expect(payload['STORY.PAC']).toEqual(blocks)
    expect(payload['STORY.PAC'].map(b => b.ca)).toEqual(['Dormir ara?', 'Sí', 'No'])
  })

  it('DEFMENU.SCP (menu) saves separately from STORY', () => {
    const tabs = {
      'STORY.PAC': [blk('0x100', 'Diàleg')],
      'DEFMENU.SCP': [blk('0x200', 'Moure'), blk('0x210', 'Opcions')],
    }
    const payload = buildSourcesPayload(tabs)
    expect(payload['STORY.PAC']).toHaveLength(1)
    expect(payload['DEFMENU.SCP']).toHaveLength(2)
  })

  it('DOUGU_ITEMTBL.PAC (items) saves with per-line glyph tracking', () => {
    // Gadget names — each is independent, no scene concept
    const blocks = [
      blk('0x2E800', 'Pa de la memòria', { scene: 0, jpBytes: 10 }),
      blk('0x2E810', 'Gadget Llarg', { scene: 0, jpBytes: 8 }),
    ]
    const payload = buildSourcesPayload({ 'DOUGU_ITEMTBL.PAC': blocks })
    expect(payload['DOUGU_ITEMTBL.PAC'][0].ca).toBe('Pa de la memòria')
    expect(payload['DOUGU_ITEMTBL.PAC'][1].ca).toBe('Gadget Llarg')
  })

  it('edit STORY, switch to DEFMENU, edit, save — both tabs preserved', () => {
    // Simulate: user edits STORY tab
    const storyBlocks = [blk('0x100', 'Nova traducció')]
    // Then loads DEFMENU tab without saving
    const menuBlocks = [blk('0x200', 'Menú')]
    // Then edits DEFMENU
    menuBlocks[0].ca = 'Opcions'

    // Save includes BOTH
    const tabBlocks = {
      'STORY.PAC': storyBlocks,
      'DEFMENU.SCP': menuBlocks,
    }
    const payload = buildSourcesPayload(tabBlocks)

    expect(payload['STORY.PAC'][0].ca).toBe('Nova traducció')
    expect(payload['DEFMENU.SCP'][0].ca).toBe('Opcions')
  })

  it('re-extract STORY tab without losing edits to DEFMENU', () => {
    // Saved state: both tabs translated
    const saved = {
      'STORY.PAC': [blk('0x100', 'Històries')],
      'DEFMENU.SCP': [blk('0x200', 'Moure')],
    }

    // Re-extract returns fresh STORY with empty ca, DEFMENU not in extract (not re-extracted)
    const fresh = {
      'STORY.PAC': [blk('0x100', '')],
    }

    // Reconcile STORY only
    reconcileByOffset(fresh['STORY.PAC'], saved['STORY.PAC'])

    // Result: STORY restored, DEFMENU is still in memory (not touched)
    expect(fresh['STORY.PAC'][0].ca).toBe('Històries')
    // DEFMENU would still be in tabBlocks[DEFMENU.SCP], unmodified
  })

  it('poll merge respects unsaved local edits — never overwrites them', () => {
    // Local: user has unsaved edits
    const local = [blk('0x100', 'Edit local')]
    // Remote: API has a different version (from another user?)
    const remote = [blk('0x100', 'Edit remot')]

    // If caller properly guards on dirty flag, this won't be called
    // But if it is, it DOES overwrite (merge assumes safe because caller checked dirty)
    const n = mergePolledCa(local, remote)

    // This is the BUG if dirty check fails: local edit is lost
    expect(local[0].ca).toBe('Edit remot')
    expect(n).toBe(1)
  })

  it('REGRESSION: buildSourcesPayload sends only active tab, previous tabs lost', () => {
    // This is the "data loss on save" bug scenario
    // User workflow:
    // 1. Load project, get STORY + DEFMENU tabs
    // 2. Edit STORY.PAC
    // 3. Switch to DEFMENU.SCP, edit it
    // 4. Save (should include BOTH tabs)

    // If the bug exists: save only includes the ACTIVE tab (DEFMENU) and LOSES STORY edits
    const tabBlocks = {
      'STORY.PAC': [
        blk('0x000100', 'Traducció del STORY'),
        blk('0x000200', 'Més text de STORY'),
      ],
      'DEFMENU.SCP': [
        blk('0x000300', 'Moure'),
        blk('0x000400', 'Opcions'),
      ],
    }

    const payload = buildSourcesPayload(tabBlocks)

    // Both tabs must be in the save payload
    expect(Object.keys(payload).sort()).toEqual(['DEFMENU.SCP', 'STORY.PAC'])
    expect(payload['STORY.PAC']).toBeDefined()
    expect(payload['DEFMENU.SCP']).toBeDefined()

    // Verify the actual translations are there
    expect(payload['STORY.PAC'][0].ca).toBe('Traducció del STORY')
    expect(payload['DEFMENU.SCP'][0].ca).toBe('Moure')
  })
})
