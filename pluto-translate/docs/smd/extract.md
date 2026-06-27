 # Mega Drive / Genesis — Translation Guide

## Console Overview
- **Encoding**: Shift-JIS (Japanese), ASCII (English/European)
- **ROM size**: Typically 2–4 MB
- **Text storage**: Compressed (LZ77, LZSS common on Genesis)
- **Architecture**: Motorola 68000 + Z80
- **Extraction challenge**: Text almost always compressed; format varies per game

## Text Storage Patterns

### Typical Mega Drive approach
1. **Compression**: Text compressed with LZ77/LZSS (saves cartridge space)
2. **Pointer tables**: Arrays of 4-byte offsets point to compressed blocks
3. **Headers**: Compressed blocks start with size or magic bytes
4. **Pointer location**: Usually early in ROM or data section

### Compression types
- **LZ77**: Common, often with 3-byte size header
- **LZSS**: Alternative LZ variant, similar structure
- **Uncompressed**: Rare, but some games mix compressed/raw

## Extraction Strategy

### Phase 1: Format Identification
1. Examine ROM hex dump for compression signatures
2. Look for repeating patterns at block starts
3. Compare JP vs translated version (same ROM, different compression = useful)
4. Check fan translation communities for this specific game

### Phase 2: Locate pointer table
1. Usually at ROM start (after header)
2. Entries are sequential 4-byte offsets
3. Verify: offsets should be increasing
4. Check known fan patches for offset documentation

### Phase 3: Decompression
1. Implement LZ77/LZSS decompressor
2. Test on known blocks
3. Verify output is readable (Shift-JIS or ASCII)

### Phase 4: Text extraction
1. Loop pointer table
2. Decompress each block
3. Extract text (until null or length field)
4. Build offset map for reinsert

## Tools & Resources

### Decompression
- **LZSS/LZ77**: Public implementations available
- **Python**: `struct` module for binary parsing
- **Existing tools**: ROM hacking communities often have Genesis-specific utils

### Communities
- **Assembler Games**: Mega Drive reverse-engineering
- **ROM hacking forums**: Genesis compression guides
- **Fan translation patches**: Often include extraction/insertion tools

### Emulators (testing)
- **Gens/GS**: Classic Mega Drive emulator
- **Fusion**: Accurate emulation
- **BlastEm**: Modern option

## Translation approach

1. Build glossary (characters, items, locations)
2. Decompress → translate → recompress
3. Recalculate pointer table (new offsets)
4. Update ROM if size changed
5. Test in Gens/Fusion

## Known blockers
- **No universal tool**: Compression format varies per game
- **Pointer table format**: Different per developer
- **Recompression**: Rebuilding ROM requires offset recalculation

## Best resource
Check for existing fan translations of your specific game — extraction tools often included in patches.

---
**Console expertise level**: Medium (compression known, no universal tool)  
**Extraction difficulty**: High (game-specific reverse-engineering)  
**Best approach**: Find existing fan tools for your title  
**Last updated**: 2026-06-25
