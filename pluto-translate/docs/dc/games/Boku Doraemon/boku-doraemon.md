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

### Capacity: expand into slack, fixed-position (≈40% ceiling)

`STORY.PAC` is an `SCP` container of 76 sector-aligned scenarios; each is
`[ASM][CMD]`, where `CMD` is a u32 pointer table over variable-size commands and
~1 in 7 commands carry text (`02ff <spk>` + SJIS). The script addresses commands
**by index** through that table, so a text command can grow as long as you bump the
later table entries. Dialogue paginates natively via `04ff`.

**Build** (the repeatable way): `dc/build_patch.py` via `packers/nullsplit.py` with
`grow=False`. Per scenario it greedily fills the trailing zero-slack with Catalan
line-by-line, repoints the CMD table, and keeps the scenario at its 0x800-aligned
size so the other 75 do not move. Lines that do not fit the slack stay Japanese.
The technique was first proven on the opening line alone (67→111 B, 2026-06-26) and
is now folded into the packer; build only via `build_patch.py`.

**CONFIRMED on screen 2026-06-28** (Flycast, full safe build): loads, opening line
and accents render, placement correct.

**Ceiling ≈40%.** Slack is ~1.4 KB/scenario (~81 KB total) and full-width Catalan
costs 2 bytes/char, so only ~3040 of 7575 lines fit; the rest render Japanese. This
is a cartridge-space limit, not a code limit.

**Do NOT relocate scenarios.** Growing scenarios and re-concatenating sector-aligned
(the abandoned `grow=True` mode) **CRASHES**: the game locates scenarios by hardcoded
offsets, not by scanning `SCP\0` (confirmed: New Game hangs / black screen
2026-06-28). Fixed-position `grow=False` is the only viable mode.

**Pagination is required.** Encode each line wrapped to **box=15** (the native box is
~16 wide and 1–2 lines tall) and paginate with `04ff` every **2 lines**. A single
`01ff`-only blob overflows the box and pushes the text out of vertical placement.

**The clamp is required.** The `nullsplit` parser over-reads ~4 bytes past a `04ff`
into the next command's header; the packer clamps each run to its command boundary so
it does not corrupt the next command. (Skipping this corrupted commands and was an
earlier crash cause; the clamp is also what took coverage from ~1% to ~40%.)

**Path past ~30%: CONDENSE TO FIT, not engine hacks.** Both escape hatches are confirmed
dead (2026-06-29): relocation crashes (hardcoded scattered offsets, confirmed even with a
correct splice) and half-width is impossible (the font is 100% full-width, no half-width
render path, engine draws dots for 1-byte codes). So the ~30% slack ceiling is the hard
floor for full text; the only way up is writing tighter Catalan to fit each box's slack.
Bar = comprehension + a wink at the dub, NOT dub fidelity (that's the licensor's job). See
the per-box budget approach and [[feedback_translation_bar]].

### Compression pass (2026-06-29): 232 KB overflow → 54.5 KB, ~77% recovered

Starting point was **232 KB of overflow across 74 over-scenes**, i.e. 3.8× the 83 KB
total slack (full Catalan wants ~4× the room that exists). Measure everything with
`nullsplit.measure` + `fon_codec.fw` (the packer's real byte cost, not a char estimate);
the number that matters is **per-scene overflow** `sum(max(0, used - slack))`, since slack
never crosses scenes. Levers, biggest first, all at near-zero narrative loss:

- **Terse menus** (~−97 KB): the navigation `Vols entrar a…? A:sí B:no` family is 1698
  blocks. Drop `Botó` (the A/B labels are in the original JP, just verbose), then cut the
  question to the room noun: `Passadís?`, `Habitació?` (のび太の部屋), `Cambra?`
  (となりの部屋, the next room), `Sala?` (いま), `Saló?` (おうせつま), `Dormitori?` (しんしつ).
- **Boilerplate by identical JP**: the dorayaki hunger-loop repeats 47–95×. `pastisset de
  melmelada`→`pastisset` (the dub itself drops the qualifier for lip-sync), one short
  canonical per recurring line.
- **Tidy regex** (~−15 KB, zero judgment): `...`→`…` (the JP's own ellipsis glyph 0x8163,
  6B→2B), `!!`→`!`, de-elongate (`Doraemooon`→`Doraemon`), destutter.
- **`Gràcies`→`Merci`**, `Doraemon`→`D` in casual lines, terminal-period drop on
  single-sentence lines.

**Contraction combo-glyphs** (fon_codec.py, deployed, **−3.5 KB**): `l' L' d' D' m' M' n' N'
s' S' t' T'` (apostrophe hugging the cell's right edge, wide M/N `_squeeze`d to 15 cols),
enclitic-hyphen `-l -m -t -s -n -h -v` (dash at the left edge), enclitic-apos `'l 'n 's 't
'm`. 24 glyphs in the free Greek slots after the 20 accents (`_CSPEC`/`_CSLOT`/`_FREE`).
`fw()` does longest-match sequence encoding, so each combo is one glyph (2B not 4B): the
text stays readable Catalan (`l'aigua`), the saving is encode-time only. The full-width cell
has enough air that an edge-hugging mark never crowds the letter.

**Kana reserve**: once nothing on screen renders kana (100% translated across every file),
the whole hiragana+katakana block (~170 glyphs) is free to overwrite, so the glyph budget
stops being a ceiling.

**Propagate-by-identical-line** (Pluto, `TranslationTable.vue`): the `propagate to N` button
fills every same-JP block with one canonical Catalan and saves. Use it so one edit lands on
all copies, and to heal divergent duplicates (the same line had drifted into ~1000
inconsistent translations).

**Composition glyphs** (fon_codec.py, deployed, **−4.4 KB**): Sí/No menu glyphs, menu-only
via the `A:sí`/`B:no` 4-char pattern in `fw()` so prose `sí`/`no` stay normal, plus one `?!`
glyph mapped from both `!?` and `?!`. Built by `_compose` (`_COMPOSE`/`_OSLOT`): crop each
letter to its ink, resize, set with even left/mid/right gaps (`no` is n8 + o9). Two-letter
cells are denser than single glyphs but only ever land isolated (menu slot, line-end
punctuation), never mid-prose. **Overflow now ~50 KB / 42 over, ~78% of the original 232 KB
recovered.**

**Character faces + clean digraph pairs** (fon_codec.py, deployed): two hand-drawn 20x19 faces
(`_FACES`, math-drawn rings/disks) mapped from `D` (Doraemon, 0 B, charm) and `Nobita` (−10 B
each, kept whole in `Nobita Nobi`); only the two leads, the supporting cast keeps names so the
player learns them. Plus the top-6 "clean" glyph pairs `qu ss ti it ix gu` (Catalan digraphs +
narrow-letter pairs, `_CLEAN`/`_CLSLOT`, composed evenly, applied everywhere, lowercase only):
−9.3 KB. All 35 free Greek slots are now used. Arbitrary frequent bigrams (`es ar en de`, ~53
KB) were REJECTED as "weird/dirty"; digraphs + narrow pairs are the clean ceiling within Greek.

### Glyph state (after the first Flycast playtest, 2026-06-30)

**CONFIRMED on screen** (scene 41 played in full Catalan): accents, contractions (`d'`, `T'`),
digraphs (`qu`, `gu`, `ss`, `ix`), both faces, the `A:sí B:no` menus all render and read. The
end-to-end build (`build_patch.py` + `fon_codec.py` → GDIBuilder → boot) is proven.

**NEEDS TWEAKING** (seen in-game): `T'` apostrophe hugs the T too tight, add a column of gap;
`gu`/`qu` squeeze the `u` thin (`Enguany` reads near `Engany`), widen the 2nd letter; `ix` good,
a hair wider helps; sentence-start capitals (`Qu`, `Ss`) stay unglyphed (lowercase-only,
inconsistent); uneven inter-letter spacing accepted as fan-TL reality.

**NOT TESTED**: only scene 41 was played. Most glyphs (Sí/No, `?!`, the enclitics, `M'`/`N'`,
the faces in varied contexts) are not yet visually confirmed beyond it.

**NEXT CANDIDATES** (ranked): more clean narrow pairs `tr ri ir rt lt li fi il` (+~7.5 KB, but
out of Greek slots); **the unlock** = the kana reserve (~170 slots) frees once nothing renders
kana on ANY surface (all 9 files translated), then digraph/narrow coverage can close most of
the rest; capital pair variants (`Qu`, `Ss`) for consistency; refine the squeezed glyphs.
Quality bar holds: digraphs + narrow pairs only, no dirtying the text for bytes.

**Overflow now ~37 KB / 36 over, ~84% of the original 232 KB recovered.** Scene 41 (the whole
first chapter) fits and is playtested in full Catalan.

**Next (translation, not glyphs)**: per-scene condensing of the remaining ~37 KB (worst is
scene 22, the farewell monologue, the emotional climax you cannot truncate). Modelled at
~1,700 hand-edits @25% condense (longest-first); the clean glyphs shave ~400-700 of those.
The reproducible pipeline (`scripts/compress.py`, GET→transform→PUT→measure via the Pluto API)
owns the mechanical layer; the rest is choosing small sacrifices or smart rewordings.

ROM extracts, patches, and the dub corpus are gitignored working data in `sandbox/`.

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
