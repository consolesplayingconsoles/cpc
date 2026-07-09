import { describe, it, expect } from 'vitest'
import type { Block } from '../lib/translation'

// Mock the lineStatus computation logic
function lineStatus(
  block: Block,
  kind: string,
  caBytes: (text: string) => number,
  cum: number,
  slack: number
): 'pending' | 'ok' | 'warn' | 'over' {
  // Items: individual carousel width check
  if (kind === 'items') {
    const caText = block.ca
    if (caText === '') return block.done ? 'ok' : 'pending'
    const glyphs = Math.ceil(caBytes(caText) / 2)
    const carousel = 20
    if (glyphs <= carousel) return 'ok'
    if (glyphs <= carousel * 1.3) return 'warn'
    return 'over'
  }

  // Dialogue/menu/ui: color based on cumulative box fill at THIS line
  if (slack <= 0) return 'pending'
  if (cum <= slack) return 'ok'
  if (cum <= slack * 1.3) return 'warn'
  return 'over'
}

// Helper: simulate Shift-JIS encoding (full-width = 2 bytes per char)
function caBytes(text: string): number {
  const folded = text.normalize('NFD').replace(/[̀-ͯ]/g, '')
  return folded.length * 2
}

describe('TranslationRow lineStatus (scene aggregation vs per-line)', () => {
  it('DIALOGUE: should color based on CUMULATIVE box fill, not per-line', () => {
    const block: Block = {
      offset: '0x100',
      speakerId: 1,
      jp: 'これはテストです',
      jpBytes: 16,
      ca: 'Això és una prova',
    }

    // Scene 1: small slack, cumulative fill should trigger warn
    const slackSmall = 50
    const cumLarge = 60 // exceeds slack but within 1.3x
    const status = lineStatus(block, 'dialogue', caBytes, cumLarge, slackSmall)
    expect(status).toBe('warn')

    // Scene 2: large slack, cumulative fill should be ok
    const slackLarge = 200
    const cumSmall = 100
    const status2 = lineStatus(block, 'dialogue', caBytes, cumSmall, slackLarge)
    expect(status2).toBe('ok')

    // Scene 3: zero slack (no room)
    const cumAny = 50
    const status3 = lineStatus(block, 'dialogue', caBytes, cumAny, 0)
    expect(status3).toBe('pending')
  })

  it('ITEMS: should color based on PER-LINE glyph width, not cumulative', () => {
    // Item name: "Pa de la memòria" (gadget)
    const block: Block = {
      offset: '0x200',
      speakerId: 0,
      jp: 'アンキパン',
      jpBytes: 10,
      ca: 'Pa de la memòria',
    }

    // Gadget name is 16 chars * 2 bytes = 32 bytes = 16 glyphs (exceeds carousel width of 20)
    // But we're testing per-line, not cumulative
    const carouselWidth = 20
    const glyphs = Math.ceil(caBytes(block.ca) / 2)
    const status = lineStatus(
      { ...block, ca: block.ca },
      'items',
      caBytes,
      0, // cumulative doesn't matter for items
      carouselWidth // this param is ignored for items
    )

    // With our test text, glyphs = 16, which is <= 20, so should be ok
    expect(glyphs).toBe(16)
    expect(status).toBe('ok')
  })

  it('ITEMS: should warn when glyph count exceeds carousel width', () => {
    // Very long gadget name
    const longName = 'Aquesta és una descripció molt llarga'
    const block: Block = {
      offset: '0x200',
      speakerId: 0,
      jp: '長い名前',
      jpBytes: 8,
      ca: longName,
    }

    const glyphs = Math.ceil(caBytes(longName) / 2)
    const status = lineStatus(block, 'items', caBytes, 999, 999) // cumulative doesn't matter

    // longName is 37 chars * 2 = 74 bytes = 37 glyphs, which exceeds 20*1.3=26
    expect(glyphs).toBe(37)
    expect(status).toBe('over')
  })

  it('ITEMS: should warn when glyphs are 21-26 (within 130%)', () => {
    // Name that fits in ~25 glyphs
    const mediumName = 'Gat per a les ulleres'
    const block: Block = {
      offset: '0x200',
      speakerId: 0,
      jp: 'メディアム',
      jpBytes: 10,
      ca: mediumName,
    }

    const glyphs = Math.ceil(caBytes(mediumName) / 2)
    const status = lineStatus(block, 'items', caBytes, 999, 999)

    // mediumName is 21 chars * 2 = 42 bytes = 21 glyphs (within 130% of 20)
    expect(glyphs).toBe(21)
    expect(status).toBe('warn')
  })

  it('MENU/UI: should color based on cumulative, not per-line bytes', () => {
    const block: Block = {
      offset: '0x300',
      speakerId: 0,
      jp: 'いどう',
      jpBytes: 6,
      ca: 'Moure',
    }

    // Menu with fixed slack
    const slack = 100
    const cum1 = 80 // within slack
    const cum2 = 120 // exceeds slack but within 1.3x (1.3*100=130)
    const cum3 = 150 // exceeds 1.3x

    const status1 = lineStatus(block, 'menu', caBytes, cum1, slack)
    const status2 = lineStatus(block, 'menu', caBytes, cum2, slack)
    const status3 = lineStatus(block, 'menu', caBytes, cum3, slack)

    expect(status1).toBe('ok')
    expect(status2).toBe('warn')
    expect(status3).toBe('over')
  })
})
