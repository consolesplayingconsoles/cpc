# Boku Doraemon — Catalan name glossary (canon tracker)

Single source of truth for character / gadget / culture names in the Catalan patch.
Every entry carries a **source** and a **confidence**, because name recall is exactly
where this project gets burned.

> **The general method behind this file lives in [`../../translation-method.md`](../../translation-method.md)**
> (game-agnostic: the oracle-grep, LLM-isn't-a-source, operator-override, coins-vs-canon, and
> "translate the memory not the recipe"). Below is just the Boku Doraemon-specific canon.

## The rule (learned the hard way)

**An LLM "confirming" a name is NOT a source.** Gemini, in one sitting, first declared
"keep *dorayaki*, definitive canon" and then reversed to "obviously *pastissets de
melmelada*". A grep of the real dub then proved `dorayaki` appears in **0 of 201
episodes** — its first answer was checkably wrong, the second right only by luck.
Neither Gemini's memory nor Claude's is canon; both sound certain when wrong.

**THE ORACLE — grep the dub corpus.** We have all 201 classic TV3 episodes' subtitles
locally at `sandbox/boku-doraemon-japan/dub-subs/*.txt` (~79k lines; gitignored, CCMA
copyright, local reference only). To settle ANY name, count its episodes:

```sh
grep -rIil "porta màgica" sandbox/boku-doraemon-japan/dub-subs | wc -l
```

High episode count = canon. Zero = the dub uses a different word — dig for it. This is
the standard; "an LLM said so" is not. (Caveat: short/common words match coincidentally,
so weight *distinctive* names and read sample lines, per [[reference_doraemon_catalan_names]].)

**SECOND CLAUSE — the corpus is the NEWER (2024 revival) dub.** It's made for an audience
that now knows Japanese culture, so it localizes *less*. The classic 1990s–2000s dub that
the target nostalgic players grew up on localized *more* (the public needed it then) and is
NOT in the corpus. So: grep gives the modern floor; the **operator's lived memory of the
classic dub overrides it for imprinted terms**. Proof: `pastisset de melmelada` = 0 corpus
lines (the revival just says `pastissets`), yet it's the burned-in name a generation knows.
We use the full classic form `pastisset(s) de melmelada` for that nostalgia hit.

Gadget/culture names are **consistent strings** → a wrong one is a one-pass find-replace,
never a re-translation. Keep each name spelled identically everywhere so the fix stays cheap.

## Characters — CONFIRMED (classic TV3 canon, stable across decades)

| JP | Catalan | note |
|---|---|---|
| ドラえもん | Doraemon | **ドラちゃん (the diminutive Mama uses) → "Doraemon", NOT "Dora"** — "Dora" reads as a girl's name in Catalan/Romance (neutral in JP, gendered here); dub drops the ちゃん entirely (Doraemon=4006 corpus hits, standalone "Dora"=address-never). EXCEPTIONS that stay "Dora": the pet cat named ドーラ and the にゃん/ドラにゃ meow pun ("Dora-mèu"). |
| のび太 | Nobita | mum calls him "Nobita, maco/fill" |
| しずか | Shizuka | |
| ジャイアン | **Gegant** | the signature TC localization (not Takeshi/Gian) |
| ジャイ子 | Geganteta | Gegant's sister |
| スネ夫 | Suneo | |
| セワシ | Sewashi | Nobita's descendant |
| ママ (玉子) | Tamako / "la mare" | Doraemon calls her nothing formal; addresses warmly |
| パパ (のび助) | Nobisuke | |
| ドラミ | Dorami | |
| 出木杉 | Dekisugi | |
| おばあちゃん | Àvia | the grandma (tear-jerker scenes) |

## Culture items — CONFIRMED

| JP | Catalan | anchor |
|---|---|---|
| ドラやき | **pastisset(s) de melmelada** | classic-dub nostalgia name — operator confirms 100% from lived memory (a key repeated, imprinted series element). Modern corpus only says bare `pastisset` (442 lines) / `dorayaki` 0 — but the full form is THE term (see second clause above). Masculine, so articles/pronouns match the old `dorayaki`. Used in full in-game; capacity handled by Option-1 expand, not size-preserving. |

## Gadgets — CONFIRMED (corpus-grepped, not LLM-guessed)

| JP | Catalan | corpus anchor | committed |
|---|---|---|---|
| どこでもドア | porta màgica | pervasive (≈all eps) | ×4 |
| タケコプター | casquet volador | pervasive (≈all eps) | ×4 |
| タイムマシン | màquina del temps | 50 eps | ×2 |
| タイムふろしき | (el) mocador del temps | 14 eps | ✓ |
| フエルミラー | (el) mirall multiplicador | 12 eps | ✓ |
| 宝さがしごっこセット | (el) kit per buscar el tresor | **named in ep 5872688** "Un bany deliciós / El kit per buscar el tresor" | ×1 (`0x0E011E`) |
| ガリバートンネル | (el) túnel de Gulliver | 14 eps ("El túnel de Gulliver!") | ✓ |
| 通り抜けフープ | **cèrcol-passadís** | 16 eps — **corrected** memory's "cèrcol túnel" (only 4); the hyphenated form dominates | ✓ |
| きせかえカメラ | (la) càmera per canviar-se | 12 eps ("Farem servir la càmera per canviar-se") | ✓ |
| ほんやくコンニャク | (la) gelatina traductora | 18 eps ("Treu la gelatina traductora") | ✓ |
| 空気砲 | (el) canó d'aire | 18 eps ("El canó d'aire!") | ✓ |
| スモールライト | **(la) llanterna reductora** | 36 eps — **corrected** "llum reductora" (0); dub uses *llanterna* | ✓ |
| ビッグライト | (la) llanterna augmentadora | pair of reductora (verify count) | ✓ pair |
| アンキパン | (el) pa de la memòria | confirmed canon (per memory) | ✓ |
| グレードアップえき | (el) líquid millorador | 14 eps | ✓ |
| 手相セット | (el) joc de quiromància | 4 eps (+ "quiromància" 12) | ✓ weak |
| 重力ペンキ | (la) pintura de la gravetat | 4 eps | ✓ weak |
| 復元光線 | (el) raig reparador | 2 eps | ✓ weak |
| ひらりマント | (la) capa esquivadora | 6 eps ("Faré servir la capa esquivadora") — was a coin, **grep-confirmed 2026-06-28** | ✓ |
| 空気ピストル | (la) pistola d'aire | 2 eps ("El meu amic corre perill! Pistola d'aire!") — distinct from 空気砲 *canó d'aire*; was a coin, **grep-confirmed 2026-06-28** | ✓ |
| まあまあ棒 | (el) bastó tranquil·litzador | 2 eps ("El bastó tranquil·litzador! Nobita!") — was a coin, **grep-confirmed 2026-06-28** | ✓ |
| ねがい星 | (l')estrella dels desitjos | 2 eps ("Doraemon! L'estrella dels desitjos!") — **corrected** my coin "Estel dels desitjos" (dub says *estrella*) 2026-06-28 | ✓ |
| 進化退化放射線源 | (el) raig de l'evolució | 2 eps ("El raig de l'evolució!") — **corrected** my coin "Font de radiació evolutiva" 2026-06-28 | ✓ |
| うらしまキャンディー | (els) caramels d'Urashima | ep 5088652 ("Caramels d'Urashimaaa!") — **corrected** to plural 2026-06-28 | ✓ |
| 精霊よびだしうでわ | (el) braçalet per invocar esperits | ep 4578531 ("El braçalet per invocar esperits!") — **corrected** my coin "Braçalet invoca-esperits" 2026-06-28 | ✓ |
| 人間ラジコン | (el) control remot per humans | 2 eps ("El control remot per humans!") — **corrected** my coin "Teledirigit humà" 2026-06-28 | ✓ |
| ケッシンコンクリート | (el) ciment de la determinació | 2 eps ("El ciment de la determinació!") — **corrected** my coin "Formigó de la decisió" (which only matched the fan wiki) 2026-06-28 | ✓ |
| うらめしドロップ | (els) caramels fantasma | 2 eps + official synopsis ("invent per convertir-se en fantasma i espantar") — **corrected** my coin "Caramel del rancor" 2026-06-28 | ✓ |

> **Coins this run (corpus-silent, flagged):** ナワバリエキス → `Essència de territori` (`0x0E4AE8`); チョージャワラシベ → `Palla de la fortuna` (warashibe lucky-straw folktale; `0x0E928E`); へんしんドリンク → `Beguda transformadora` (`0x0E92D0`). All 0 corpus hits as gadget names.

All three verified against `dub-subs/` — no longer provisional. **Add new gadgets here the
moment they appear in a translated line, with their episode count.** For obscure
episode-specific gadgets not in the corpus, draft in the dub style and FLAG for the
operator (per [[reference_doraemon_catalan_names]] — 13 certain + 143 pending there).

### Coined — SETTLED (game-only gadget, no episode exists to canonize it)

| JP | Catalan | why | committed |
|---|---|---|---|
| 室内旅行機 (indoor travel machine) | **Simulador de viatges** | game-exclusive gadget, **0 corpus hits** and no TV episode (operator confirmed; editorial judgment is final here). Captures the *travel-without-leaving-the-room* gag ("simulador"), reinforced by the dub idiom "sense moure't" in the surrounding line. **Decision: keep — not pending.** | ×1 (`0x0DB9B6`) |

> **Discipline note (2026-06-27):** "La màquina de viatges interiors" was floated and I wrongly
> adopted it — it was an **untested candidate** (operator was checking whether I'd commit an
> unverified name on suggestion alone; 0 corpus hits). Reverted. **Rule reaffirmed: corpus-silent +
> no real source = stays a flagged coin, never canon — regardless of who proposes it or how
> plausible it sounds.** A suggested name is a hypothesis to grep, not an answer.
> **Confirmed this session by grep (not just memory):** タイムふろしき = `mocador del temps` (14 eps), フエルミラー = `mirall multiplicador` (12 eps). 宝さがしごっこセット = `kit per buscar el tresor` (named in ep 5872688) — my coins "Joc de cerca / buscar tresors" were both wrong; the episode title settled it.

## Workflow — match each game scene to its TV episode

The game retells specific TV episodes; each game scene's distinctive gadget/phrase, grepped
against `dub-subs/`, finds the matching episode, which then hands over **canonical gadget
names AND dialogue/tone**. Proven hits (note the consecutive video IDs — the game draws from
a specific episode set):

| game scene | TV episode | local file |
|---|---|---|
| Suneo's broken toy → treasure hunt | "Un bany deliciós / El kit per buscar el tresor" | `5872688_*.txt` |
| Doraemon's birth / time capsule | "La càpsula dels cent anys" | `5872689_*.txt` |

When a new scene's gadget appears: grep its name/phrase first, find the episode, lift canon.
