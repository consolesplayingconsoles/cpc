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

### Fonts & rendering (corrected 2026-06-26 by on-screen testing)

The earlier "renders Latin natively / 1 byte per char / no font hack" notes were
wrong. What the game actually does:

- In-game dialogue renders through the game's own font `S18RM04.FON` (root-level,
  JIS-indexed). Format **CRACKED 2026-06-27: plain linear 2bpp, 20px cells** (not
  compressed/vector as first feared) — general format + method in [`../fonts.md`](../fonts.md).
- The font has **full-width Latin only** (JIS row 0x23); ASCII / half-width draw as
  dots (no half-width font, proven by probe), so Catalan costs **2 bytes per char**.
- **Accents — SOLVED** via the Greek-slot trick (method in `../fonts.md`). Game-specific
  facts: **0 of this game's 1817 text codes fall in the Greek range** (`0x839F–0x83D6`),
  so it's safe to overwrite; 20 Catalan accents authored into slots `0x839F–0x83C8`
  by `fon_codec.build_patched_font`; the patched `.FON` is a regen-able artifact.
  Open: `ŀl` middot (folded to `ll`), uppercase marks are tight.
- Menus are not text: the title screen and options are **PVR textures** (see
  `../textures.md`), translated by repainting the atlas.
- `DPETC\MESSAGE.INI` is the Dream Passport **browser** string table, not the game
  UI. **OFF-LIMITS**: latinizing it boots the INTERNET page blank/grey (browser
  chokes) and it needs DreamPi anyway.

### Capacity: expand, don't truncate

Size-preserving in-place patching is NOT required. `STORY.PAC` is an `SCP`
container of 76 sector-aligned scenarios; dialogue is read sequentially (no
absolute text pointers for most lines) and the engine paginates natively via the
`04ff` control code. So you can write **more** Catalan than the Japanese budget:
expand a line, wrap to the (generous) box with `01ff`, paginate with `04ff`, shift
the trailing bytes into the scenario's slack (~1.4 KB each, ~81 KB total), update
any u32 message-table pointers that point past the edit, and keep the scenario at
its 0x800-aligned size so the other 75 don't move. Proven on screen 2026-06-26
(opening line expanded 67→111 B). Scripts in `dist/scripts/`
(`expand-line.py` dialogue, `itemtbl-expand.py` gadgets); the ROM extracts,
patches and dub corpus are the gitignored working data in `sandbox/`.

## Translation notes

- Target dialect: Catalan (CA), TV3/Super3 dub era (first broadcast 1994, revived 3Cat June 2026)
- Tone: warm, playful children's adventure — Doraemon speaks gently, Gegant loudly, Suneo slyly
- Source: Japanese direct → Catalan (no pivot language)
- Honorifics: お兄ちゃん (Dorami → Doraemon) = "germà" in context

### Tone source — the official dub (authoritative)

Match the **official TV3/3Cat Catalan dub**, not a literal translation and not the
fan wiki (the wiki is for facts and names only). Build the register from the real
dub dialogue: 201 episodes of `Doraemon, el gat còsmic` subtitles are pulled
locally as a reference corpus (≈79k lines).

How to fetch (no scraping; the public media API exposes the subtitle track):

1. List episodes: `https://api.3cat.cat/videos?_format=json&programatv_id=119987484&items_pagina=100&pagina=N`
   (program `119987484`, 201 episodes over 3 pages). Take each item's `id`.
2. Per id, `https://api-media.ccma.cat/pvideo/media.jsp?media=video&version=0s&idint=<id>&profile=pc`
   returns JSON with `subtitols[].url` (a Catalan `.vtt`). Strip the WebVTT
   timestamps/tags to get plain dialogue.

The cleaned corpus lives in `sandbox/boku-doraemon-japan/dub-subs/` (gitignored).
**It is CCMA copyright: local reference only, never commit it.** The dub voice is casual,
colloquial Catalan kid speech (contractions, exclamations, "M'ho passaria
superbé") with gadgets named in-flow.

### Characters & voice (Catalan dub)

Speakers carry the dub name, not the Japanese one. Roster: Doraemon, Nobita,
Shizuka, **Gegant** (ジャイアン/Takeshi), Suneo, Dorami, **Geganteta** (ジャイ子/Jaiko),
**Dekisugi** (出木杉, the model student), **Sewashi** (セワシ, Nobita's descendant who
sent Doraemon), **Tamako**/**Nobisuke** (Nobita's parents), **Sr. Kaminari** (the
grumpy neighbour), the Professor. Write each in voice: Doraemon the worrier, Suneo
"repel·lent i mentider", Gegant "l'animalot" with a horrible singing voice, Nobita
the good-hearted scatterbrain, Dorami the sensible one. Full roster + the ~30-name
TV3 voice cast (for the credits) in memory `reference_doraemon_catalan_names`.

### Franchise / Catalan history (for credits and the launch article)

`Doraemon, el gat còsmic` first aired in Catalan **7 Feb 1994** (TV3/Super3), ran
until 2018, then only in Castilian on the mainland until **3Cat revived it 2026**
(~200 classic episodes + a 24h channel + films, 32 years on). Three historical
Catalan dubs: TV3, Canal 9→À Punt (València), IB3 (Balears). Spanish distributor:
Luk Internacional. Angle for the writeup: a fan **Catalan** translation of a
Japan-only Doraemon game, landing on the exact revival wave and the long-running
"bring it back in Catalan" sentiment. Credit both the dub cast and the Dreamcast
RE community whose breadcrumbs made the hack possible (see
`reference_boku_doraemon_english_tl`: yzb, ateam, Sappharad/GDIBuilder, megavolt85).

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
| どこでもドア | Anywhere Door | **Porta màgica** |
| タケコプター | Takecopter | **Casquet volador** |
| タイムふろしき | Time cloth | **El mocador del temps** |
| 通り抜けフープ | Pass-through hoop | **Cercle de pas** |
| アンキパン | Memory bread | **Pa de la memòria** |
| 空き地 | vacant lot | solar |
| 未来 | future | futur |

Canonical gadget names come from the Catalan wiki *Llista d'aparells d'en
Doraemon* (full list captured in memory `reference_doraemon_catalan_names`). The
wiki covers ~64 curated gadgets; the game has **156**, so only ~15-25 map
directly. The rest are obscure/episode-specific and must be **coined in the dub
register**, then reviewed. Note nearly every canonical name is accented, so
faithful gadget names depend on the font glyph-add above. When a gadget or speaker
is unclear, ask rather than guess.

## Extraction workflow (proven)

> Note: the steps below are the early speaker-tag/offset method. The current
> pipeline parses `STORY.PAC` with `nullsplit` (7,649 blocks), rebuilds the disc
> with GDIBuilder (Modified-files, mirror the subdir path so subdir files like
> `DOUGU\ITEMTBL.PAC` are *replaced* not duplicated), and fits longer Catalan via
> the *Capacity: expand, don't truncate* section above rather than space-padding.

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
- **Gadget names** (`ITEMTBL.PAC`) localize against the Catalan *Llista d'aparells*
  wiki, but the wiki only covers ~64 of the game's 156 gadgets, so most names you
  coin yourself in the dub register and get reviewed. They are **not** the easy
  early win the old note claimed: the canonical names are heavily accented, so they
  are blocked on the font glyph-add. Use the canonical name where the wiki has one
  (`タケコプター`=Casquet volador, `どこでもドア`=Porta màgica), coin the rest.
- **Gegant** is the key edge case — non-derivable from Japanese (Gian), Spanish (Giant), or English (Big G). TV3 dub canonical name confirmed.
- **Geganteta** = Jaiko (Gian's sister) — follows same pattern, equally non-derivable.
- Dorayaki kept untranslated — it's a named food item and known loanword in context.
- Voice sources: Eduard Itchart (Doraemon), Geni Rey (Nobita), Josep Sobrevia (Gegant), Olga Supervia (Shizuka), Noemí Bayarrí (Suneo), Júlia Chalmeta (Dorami).
- Doraemon returned to 3Cat on 2026-06-15 with 200 classic episodes — naming is current and canonical.
