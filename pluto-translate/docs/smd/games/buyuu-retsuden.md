# Dragon Ball Z - Buyuu Retsuden — Mega Drive (Japan & France)

Translation target: **Japanese → Catalan** (or reference French version for structure)

## Game Info
- **Developer**: BANDAI/NAMCO
- **Released**: 1994 (Japan as BDVJD9), France (as BDVE70)
- **Type**: Fighting/Action game with story dialogue
- **ROMs**: JP (BDVJD9) and FR (BDVE70) available for comparative analysis

Console guide: `../consoles/megadrive.md`

## Technical Status
- **Extraction**: 5% attempted (NO working method yet)
- **Blocker**: Text is compressed/binary-encoded; pattern matching fails
- **Approach**: Compression format identification + pointer table location

## What We Know
- ROM size: 2.0 MB (both JP and FR identical)
- Encoding: Shift-JIS (JP), ASCII (FR)
- Text likely packed with compression (LZ77/LZSS common on Genesis)

## Failed Approaches
| Method | Result | Why |
|--------|--------|-----|
| Speaker tag pattern (DC-style) | 0 blocks | Not used on Genesis |
| Shift-JIS null-terminated search | 2,405 entries (mostly garbage) | Compressed data falsely matches |
| ASCII region mapping | US ↔ JP mismatch | Compressed differently or offset |

## Extraction Path (When Format Identified)

1. **Find compression headers** (LZ77: `0x10` magic, size bytes; LZSS: check frame markers)
2. **Locate pointer table** (arrays of offsets pointing to compressed blocks)
3. **Build decompressor** (LZ77/LZSS most likely for Genesis era)
4. **Decompress & extract** (dialogue blocks become readable)
5. **Map JP ↔ FR** (verify structure by comparing versions at same offsets)
6. **Translate & reinsert** (glossary-driven, pack compressed)
7. **Test in Gens/Fusion**

## Test Results (2026-06-25)

**Exploratory extraction ran successfully. Findings:**

- **LZ77 signatures** (`0x10`): 20,775 occurrences → Compression confirmed
- **LZSS signatures** (`0xC0`): 43,302 occurrences → Multiple compression types likely
- **Pointer table candidates**: 126,477 sequences → Too many false positives without more context
- **Early ROM structure**: Offsets visible at `0x000008` onwards (likely ROM header + pointer table)

**Conclusion**: Text IS compressed. Need to:
1. Locate the actual pointer table (likely in ROM header area)
2. Identify which compression format (LZ77 vs LZSS)
3. Find decompression details (size fields, etc.)

## Research Needed
- [ ] Fan translation patches (check GBAtemp, ROM hacking forums for Buyuu Retsuden specifically)
- [ ] ROM header documentation (Mega Drive ROM structure standard)
- [ ] Pointer table location (likely 0x000008 or early in header)
- [ ] Decompression spec (LZ77/LZSS implementation details)

## Community Resources
- **Assembler Games**: Mega Drive reverse-engineering
- **ROM hacking forums**: SNES/Genesis compression discussions (LZ77 often documented)
- **Fan translation patches**: May include extraction tools or offset tables
- LZSS/LZ77 libraries exist (e.g., Pucrunch archives)

## Translation Notes
- **Glossary**: Use Dragon Ball Z standard names
  - Goku = Son Goku / Kakarot = Goku (French uses "Sangoku")
  - Vegeta = Vegeta (no change across languages)
  - Frieza = Frieza (Français: "Freezer", keep Catalan "Frieza")
- **Tone**: Fighting game; action-focused, minimal story
- **Source**: Japanese direct (FR version available as reference only)

---
**Status**: Awaiting compression format identification  
**Estimated completion**: Unknown (depends on decompression complexity)  
**Last updated**: 2026-06-25
