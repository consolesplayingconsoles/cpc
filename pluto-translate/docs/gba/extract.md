# Game Boy Advance — Translation Guide

## Console Overview
- **Encoding**: Shift-JIS (Japanese games), ASCII (English)
- **ROM size**: 16–32 MB typically
- **Text storage**: Heavily compressed (LZ77, LZ4, or custom)
- **Architecture**: 32-bit ARM (GBA CPU)
- **Extraction challenge**: No simple text pattern; all games differ

## Text Storage Patterns

### Typical GBA approach
1. **Compression**: Text almost always compressed (saves ROM space)
2. **Pointer tables**: Arrays of 4-byte offsets point to compressed blocks
3. **Headers**: Compressed blocks have magic bytes or size fields
4. **Pointer location**: Usually early in ROM or in dedicated data section

### Compression types observed
- **LZ77**: Common, signature `0x10` followed by 3-byte size
- **LZ4**: Also used, has frame magic (`0x04 0x22 0x4D 0x18`)
- **Custom**: Some games use proprietary compression (rare but documented)

## Extraction Strategy

### Phase 1: Format Identification
1. Examine ROM hex dump: search for compression signatures
2. Look for repeating patterns (text blocks start with same magic)
3. Compare JP vs US version (same offsets, different compression = useful)
4. Check fan translation communities for this specific game

### Phase 2: Pointer table location
1. Pointer tables are usually:
   - At start of ROM (after header)
   - In dedicated data section
   - At fixed offset (documented in fan patches)
2. Verify: table entries should be sequential offsets, increasing values

### Phase 3: Decompression
1. Implement or find LZ77/LZ4 decompressor (libraries exist)
2. Test on known data blocks
3. Verify output is readable text (Shift-JIS or ASCII)

### Phase 4: Text extraction
1. Loop through pointer table
2. Decompress each block
3. Extract Shift-JIS text (until null or next block)
4. Build offset map for reinsertion

## Tools & Resources

### Compression libraries
- **LZSS/LZ77**: Public domain implementations available
- **LZ4**: Official reference implementation in C
- **Python**: `lz4` module, `struct` for binary parsing

### ROM hacking communities
- **GBAtemp**: ROM hacking section, per-game threads
- **Assembler Games**: Technical discussions, decompression guides
- **XentaxBackup**: Game format archive (may have your game documented)
- **Individual fan patches**: Often include extraction/insertion tools

### Emulators (for testing)
- **mGBA**: Modern, accurate GBA emulation
- **Dolphin**: Also supports GBA (under-utilized option)
- **VBA-M**: Older but stable

## Translation approach

1. Build glossary (character names, items, locations)
2. Translate compressed blocks (decompress → translate → recompress)
3. Recalculate pointer table (new offsets after recompression)
4. Update ROM header (if size changed)
5. Test in mGBA/Dolphin

## Known blockers per game
- **No universal tool**: Each GBA game is different
- **Compression varies**: Even within publisher libraries
- **Pointer table format**: Different per engine

## Community knowledge as primary source
For each GBA game:
1. Search GBAtemp for translation threads (often have tools)
2. Check Assembler Games reverse-engineering posts
3. Look for existing fan patches (ROM hacks often include extraction utils)
4. Ask translation communities directly (active fan bases exist)

---
**Console expertise level**: Medium (compression identified, no universal tool)  
**Extraction difficulty**: High (game-specific reverse-engineering required)  
**Best approach**: Find existing fan translation tools for your specific game  
**Last updated**: 2026-06-25
