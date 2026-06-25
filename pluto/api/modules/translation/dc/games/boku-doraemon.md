# Boku Doraemon — Dreamcast (2001)

Translation target: **Japanese → Catalan**

## Game

Virtual companion / interactive storybook game by Sega Toys. Uses DreamPassport 3.0 browser engine. Doraemon helps Nobita through illustrated story episodes with gadgets, mini-interactions, and chat features. Japan-only, no existing translation.

Console guide: `../consoles/dc.md`

## Technical notes

### Text sources (found by content scan — `dc_text_scan.py`, ranked by kana ratio)

Translatable text lives in **four** files; ITEMTBL surfaced purely from Shift-JIS
density (the name gives nothing away):

Full ranked inventory (`dc_text_scan.py`, sorted by kana ratio):

| File | Kana% | What | Status |
|---|---|---|---|
| `INFO\SECRET.TBL` | 86% | Secret / unlockables table | untried |
| `DOUGU\ITEMTBL.PAC` | 74% | Gadget names (どこでもドア, タケコプター, ほんやくコンニャク…), clean Shift-JIS, closed set | **NEW** — wiki-localizable, not yet wired |
| `STORY.PAC` (track05) | 71% | Primary dialogue — 7,649 null-split blocks, speaker tags `\x02\xff<id>` (21 speakers, ID 01 = protagonist) | extract→patch→rebuild→boot **proven** |
| `DPTEX_ORIGINAL\README.TXT` | 68% | Plain-text readme | untried (likely non-game) |
| `DPETC\CHAT.DPS` | 68% | Chat-feature strings | untried |
| `DP3.INI` | 65% | Config strings | untried (likely config) |
| `DPETC\MESSAGE.INI` | 55% | 797 UI / menu strings, plain INI | easy, not yet wired |
| `DPETC\PM.DPS` | 52% | Misc UI (.DPS) | untried |
| `DPETC\DP3.DPS` | 49% | DreamPassport UI (.DPS) | untried |
| `DPETC\SOFTKEY.DPS` | 45% | On-screen keyboard labels | low value |
| `TITLE.PVM` → `press` | — (PVR) | Title menu baked as textures (はじめから…) | done via texture pipeline (`../textures.md`) |

Cut line ≈45% kana: below it are `.PVR`/`.NJ` graphics/models, not text. **Dismissed despite size:** `STORYGRA.PAC` (487 MB story *graphics*, 1.3% kana), `ENDING0*.SFD` (FMV, ~2%), `ADXPACK*.AFS` (voice, ~0.2%), `2_DP.BIN` (loud at 24k pairs but binary, 8% — decodes to garbage). Note: buildgdi emits some names with **literal backslashes** (`DOUGU\ITEMTBL.PAC` is one filename, not a subdir) — match by wildcard.

### Fonts & Rendering
- DreamPassport engine renders Latin/ISO-8859-1 natively
- No font hacking required for Catalan
- Space advantage confirmed: Japanese = 2 bytes/char → Catalan = 1 byte/char
- ~80% of extracted blocks fit within same byte budget

### Byte Budget
- Typical dialogue: 18–60 bytes JP (speaker tag + text)
- Catalan fit: ~80% with smart word-boundary truncation
- Padding: Space-fill remaining bytes after translation

## Translation notes

- Target dialect: Catalan (CA), TV3/Super3 dub era (first broadcast 1994, revived 3Cat June 2026)
- Tone: warm, playful children's adventure — Doraemon speaks gently, Gegant loudly, Suneo slyly
- Source: Japanese direct → Catalan (no pivot language)
- Honorifics: お兄ちゃん (Dorami → Doraemon) = "germà" in context

## Glossary

| JP | Romaji | CA |
|---|---|---|
| ドラえもん | Doraemon | Doraemon |
| のび太 | Nobita | Nobita |
| しずか | Shizuka | Shizuka |
| ジャイアン / 剛田武 | Gian / Takeshi | Gegant |
| スネ夫 | Suneo | Suneo |
| ドラミ | Dorami | Dorami |
| ジャイ子 | Jaiko | Geganteta |
| セワシ | Sewashi | Sewashi |
| のび太のパパ | Nobita's dad | el pare del Nobita |
| のび太のママ | Nobita's mum | la mare del Nobita |
| お兄ちゃん | big brother (Dorami→Doraemon) | germà |
| ドラやき | Dorayaki | dorayaki |
| ひみつ道具 | secret gadget | artefacte secret |
| 四次元ポケット | 4D pocket | butxaca quadridimensional |
| タイムマシン | time machine | màquina del temps |
| どこでもドア | Anywhere Door | porta de qualsevol lloc |
| たけこぷたー | Takecopter | hèlix voladora |
| 空き地 | vacant lot | solar |
| 未来 | future | futur |

## Extraction workflow (proven)

1. ✓ Drop GDI disc image (uncompressed)
2. ✓ Read track 5 raw file (827MB)
3. ✓ Search for speaker tag pattern `\x02\xff`
4. ✓ Extract Shift-JIS text following each tag
5. ✓ Filter by MIN_TEXT_LEN=8 + require ≥1 multi-byte char (Japanese)
6. ✓ Build offset table: (tag_offset, speaker_id, jp_text, jp_bytes)
7. ✓ Patch: translate each entry, pad with spaces to match byte length
8. ✓ Write back to track05.bin at original offsets
9. ✓ Repack GDI and test in Flycast

### Coverage
- `STORY.PAC` dialogue fully extracted (**7,649 blocks**) and round-trips through rebuild.
- The old "~40% missing / different encoding" theory was wrong: the on-screen JP text
  that wasn't in STORY.PAC lives in **other files**, now mapped in *Text sources* above
  (gadgets in `ITEMTBL.PAC`, UI in `MESSAGE.INI`, title menu in `TITLE.PVM`). The
  content scan replaced the guesswork.
- Open: wire `ITEMTBL.PAC` into the workbench (needs its own block parser — fixed-record
  or null-split, TBD).

**Glossary notes:**
- **Gadget names** (`ITEMTBL.PAC`) localize against the Doraemon *inventions* wiki — most gadgets have canonical CA/ES dub names (どこでもドア = porta de qualsevol lloc, タケコプター = hèlix voladora, ほんやくコンニャク = gelatina traductora). Use the wiki as the gadget glossary; only a handful need invented CA names. These are the easiest wins on the disc: short, closed-set, reference-backed.
- **Gegant** is the key edge case — non-derivable from Japanese (Gian), Spanish (Giant), or English (Big G). TV3 dub canonical name confirmed.
- **Geganteta** = Jaiko (Gian's sister) — follows same pattern, equally non-derivable.
- Dorayaki kept untranslated — it's a named food item and known loanword in context.
- Voice sources: Eduard Itchart (Doraemon), Geni Rey (Nobita), Josep Sobrevia (Gegant), Olga Supervia (Shizuka), Noemí Bayarrí (Suneo), Júlia Chalmeta (Dorami).
- Doraemon returned to 3Cat on 2026-06-15 with 200 classic episodes — naming is current and canonical.
