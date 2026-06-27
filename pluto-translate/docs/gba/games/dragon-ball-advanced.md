# Dragon Ball - Advance Adventure — GBA (Japan & USA)

Translation target: **Japanese → Catalan** (or reference US version for structure)

## Game Info
- **Developer**: BANDAI/NAMCO
- **Released**: 2002 (Japan), 2003 (USA)
- **Type**: Action/RPG with dialogue
- **Availability**: JP and US ROM versions available for comparative analysis

Console guide: `../consoles/gba.md`

## Technical Status
- **Extraction**: 5% attempted (NO working method yet)
- **Blocker**: Text is compressed/binary-encoded; simple pattern matching fails
- **Approach**: Compression format identification needed

## What We Know
- ROM size: 16 MB (both JP and US identical)
- Encoding (assumed): Shift-JIS (JP), ASCII (US)
- Text likely stored with pointer tables or compressed blocks

## Failed Approaches
| Method | Result | Why |
|--------|--------|-----|
| Speaker tag pattern (DC-style) | 0 blocks | Not used in GBA |
| Shift-JIS null-terminated search | 8,772 entries (mostly garbage) | Too many false positives |
| High-ASCII region mapping | US ↔ JP mismatch | Text compressed differently per version |

## Extraction Path (When Format Identified)

1. **Identify compression** (LZ77/LZ4 signatures, custom format)
2. **Locate pointer table** (arrays of offsets to text blocks)
3. **Decompress dialogue** (implement/find decompressor)
4. **Map JP ↔ US** (verify structure by comparing versions)
5. **Extract & translate** (build glossary, translate, reinsert)
6. **Test in mGBA/Dolphin**

## Research Needed
- [ ] Compression header identification (LZ77 `0x10`, LZ4 magic, custom sig?)
- [ ] Fan translation documentation (check GBAtemp, Assembler Games)
- [ ] Pointer table format (typical: 4-byte offsets at known addresses)
- [ ] Text block boundaries (how does game determine string length?)

## Community Resources
- **GBAtemp ROM hacking**: Game-specific tools often posted
- **Assembler Games**: GBA reverse-engineering discussions
- **XentaxBackup**: Game format archive
- Check for existing fan translation patches (may include extraction tools)

## Translation Notes
- **Glossary**: Use Dragon Ball franchise standard (character names consistent across DBZ Mega Drive port)
- **Tone**: Action game, minimal dialogue; use snappy Catalan
- **Source**: Japanese direct (no English pivot)

---
**Status**: Awaiting compression format identification  
**Estimated completion**: Unknown (depends on complexity of decompression)  
**Last updated**: 2026-06-25
