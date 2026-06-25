# WonderSwan — Translation Guide

## Console Overview
- **Encoding**: Shift-JIS (Japanese games primarily)
- **ROM size**: Typically 64–256 MB (ROM cartridges)
- **Text storage**: Game-specific (varies widely)
- **Architecture**: 16-bit custom CPU
- **Extraction challenge**: Limited documentation; game-specific reverse-engineering

## Known text patterns
- Shift-JIS encoding standard
- Text often embedded in data files within ROM
- Pointer tables or direct offsets common
- Compression varies per game

## Extraction strategy
1. Identify game-specific text storage (hex dump inspection)
2. Locate pointer tables or text markers
3. Extract Shift-JIS blocks
4. Translate and reinsert
5. Test on hardware or emulator

## Tools & Resources
- **Emu2413/WonderSwan emulators**: For testing
- **ROM hacking communities**: Limited, but growing
- **Game-specific documentation**: Per-title approach necessary

## Translation approach
- Build glossary for character names
- Translate Shift-JIS text in-place
- Respect byte budgets (varies per game)
- Test thoroughly

---
**Console expertise level**: Low (limited documentation)  
**Extraction difficulty**: Very High (game-specific reverse-engineering)  
**Status**: Awaiting per-game research  
**Last updated**: 2026-06-25
