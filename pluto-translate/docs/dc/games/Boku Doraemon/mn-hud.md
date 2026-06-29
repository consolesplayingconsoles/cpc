# Boku Doraemon — mini-game HUD textures (MN1/2/3.PVM)

The three help-Mum chore mini-games that refill Doraemon's dorayaki gauge. **Reach them in-game by
going to Mama at home and accepting her お手伝い (help) request** (the TAM dialogue, already Catalan:
"Ah, Doraemon, que em vols ajudar?"). They cycle when your dorayaki runs low. All text baked as PVR
textures (not strings), translated via `pvr_codec` + the fill-and-redraw method in `../textures.md`.

Each `MN*.PVM` is ONE game over a different background. Chunk index is NOT stable across the files —
identify by content. **Kept untranslated** (already Latin / universal): PAUSE, POINT, Perfect!, the
0123456789 number font, ○×, the food/kitchen icons, character portraits, the colour gauges.

All baked into `sandbox/.../patch/MN{1,2,3}.PVM` (byte-identical chunk swaps; rebuild + Flycast to verify).

## MN1 = 肩たたき (shoulder massage) — room background
| chunk | JP | Catalan |
|---|---|---|
| counter (256²) | ドラやき / ゲット数 | **PASTISSETS / CRUSPITS** (gold/green; "cruspits"=gobbled, dub-attested, in-tone) |
| c2 | Aボタン / Bボタン | Botó A / Botó B |
| c2 | 〜そうさ方法〜 + body | ~ COM ES JUGA ~ · "Mira el cursor que es mou per la barra de sota, prem el botó en el moment just i fes un bon massatge a la mare!!" · **Al vermell, botó A** (red) / **al blau, botó B** (blue) · "Fes-ho ben fet!" |
| c3 | massage praise ×2 | "Que bé, Doraemon! / Que bé que fas el massatge! / Menja molts pastissets!" · "Gràcies, Doraemon. / Té, et donaré pastissets!" |
| c4 | 用意して〜/スタート!!/終了〜!! | **Preparats, llestos… / Ja!! / Fi!** (race call; 〜→ellipsis, !!→Ja) |
| c4 | scold bubble | "Escolta, Doraemon… / Que no hi poses ganes?! / Doncs res de pastissets!" |
| c5 | 残りじかん 秒 | Temps: __ s |

## MN2 = 草むしり (weeding) — garden background
| chunk | JP | Catalan |
|---|---|---|
| counter | ドラやき/ゲット数 | PASTISSETS / CRUSPITS |
| c2 | cleaning praise ×2 | "Ostres, ha quedat ben net! / Moltes gràcies, Doraemon." · "Bona feina, Doraemon. / Ha quedat força net, oi?" |
| c3 | tutorial + 残りじかん | ~ COM ES JUGA ~ · "Prem el botó A per agafar l'herba, remena la creueta a banda i banda i l'arrencaràs! Compte amb les rates que t'empaiten! Salta amb el botó B per esquivar-les" · Temps: s |
| c4 | ready/go/finish | Preparats, llestos… / Ja!! / Fi! |

## MN3 = おかたづけ (tidying) — park/kitchen background
| chunk | JP | Catalan |
|---|---|---|
| counter | ドラやき/ゲット数 | PASTISSETS / CRUSPITS |
| c2 | tidying praise ×2 | "Ha quedat ben net! / Gràcies, Doraemon. / Té, menja't el berenar." · "Gràcies, Doraemon. / Torna a ajudar-me, eh? / Té, un pastisset!" |
| c3 | tutorial + 残りじかん | ~ COM ES JUGA ~ · "Memoritza bé on va cada cosa i porta-la al lloc just dins del temps. Amb el botó A agafes i deixes les coses. Esquiva les rates saltant amb el botó B. Amb el botó Y pots acabar abans d'hora" · Temps: s |
| c4 | ready/go/finish + instruction | Preparats, llestos… / Ja!! / Fi! · **Posa-ho / en aquest lloc!** |

## Notes & verify-points (when you reach each chore in-game)
- **"pastissets" short form on the HUD** (counter, bubbles) — the dub clips it; the full "pastisset de
  melmelada" stays in the STORY.PAC dialogue where there's room. Uniform font per bubble for even borders.
- The green-board text is a **flat/gradient fill + redraw** (the JP can't be erased to transparent without
  punching the board); flagged if the fill green ever looks off against the board gradient in motion.
- **Highlight/scale is engine-side** — the only things to check live are that the selection pulse still
  lands on the moved STEREO/MONO·S/L (options screen) and that these HUD labels aren't clipped/over-pulsed.
- MESWIN.PVM (dialogue border) and OPTION4.PVR (frame) have no text. PAUSE/POINT/Perfect!/numbers stay Latin.
