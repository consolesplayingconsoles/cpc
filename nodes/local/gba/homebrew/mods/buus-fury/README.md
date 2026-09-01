# Buu's Fury meme mods (CPC)

Patch the game's on-screen text (menus, item/ability descriptions, and the story
quest goals) into memes. Pure data editing -- no compiler, no ARM Developer Suite.

## Files
- `rom/baserom.gba`   - the base game (sha1 f1c4b075...), your copy
- `tools/extract_text.py`  - dump every editable string: `python3 tools/extract_text.py rom/baserom.gba 12 > tools/all_text.tsv`
- `tools/all_text.tsv`     - the editable-text list: `ADDRESS  <bytelen>  text`
- `edits.tsv`         - your meme edits: `0xADDRESS <TAB> new text`
- `./build.sh`        - applies edits -> `rom/buus-memes.gba`
- `buusfury/`         - the full disassembly (reference/map; its ADS rebuild is NOT needed)

## Workflow
1. Browse `tools/all_text.tsv`, pick lines (the `0x0805E0..` block is the story goals).
2. Add each to `edits.tsv` as `0xADDR <TAB> your meme text`.
3. **Keep it <= the original line's length** (the patcher skips + warns if too long; terser is funnier).
4. `./build.sh`, then load `rom/buus-memes.gba` in an emulator or flash it to a GBA cart.

## Not (yet) editable
Deep NPC cutscene dialogue is in a compressed script format -- a separate RE job.
The menus / item descriptions / quest goals above are all live now.
