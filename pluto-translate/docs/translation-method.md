# Translation method — names, tone & verification (game-agnostic)

Hard-won lessons from real fan-translation work. **Game- and language-agnostic** — they apply to
any ROM, any target language, any console in this framework. Per-game glossaries and open-flag
trackers live next to each game (e.g. `dc/games/<game>-names.md`, `<game>-flags.md`) and should
**link up to this file** rather than restate it.

## 1. A proposed name is a query, not an answer

Whoever proposes a character/gadget/term name — you, an LLM, even a contributor — that proposal is
a **hypothesis to verify**, never a result. The only input that bypasses verification is the
operator's *explicit* lived-memory confirmation (see §4). Everything else gets checked.

## 2. The oracle: grep the official dub corpus

If a dub of the work exists, its subtitles are the ground truth. Pull the full subtitle corpus
locally and **count episodes per candidate name**:

```sh
grep -rIil "candidate name" <corpus-dir> | wc -l
```

High episode count = canon. Zero = the dub uses a different word — dig for it (search by the
gadget/term's *function* or scene, find the episode, read what it's actually called). Weight
**distinctive** phrases; short/common words match coincidentally, so read sample lines before
trusting a count.

> Corpus is copyright material → **local reference only, never commit it.** Commit only the
> derived glossary (the name → episode-count mapping).

## 3. LLMs are not sources

An LLM "confirming" a name is **not** verification, no matter how authoritative it looks.
Documented failure (2026-06-27): an LLM first declared a term "definitive canon," then reversed
itself in the same conversation; when asked for episode/source citations it **fabricated** them
(citing a *different* item's episode as the source). Tells to watch for:

- **Echo**: it hands your own guesses back verbatim (sycophancy, not retrieval).
- **Fabricated specifics**: precise-looking episode numbers / volumes that don't check out.
- **Mismatched sources**: the cited scene/title is for a different item.

Use LLMs to *generate candidates* and gloss function; let the corpus or the operator arbitrate.

## 4. The corpus is *a* dub, not *the* memory — operator override

The corpus you can pull is usually the **most recent / most available** dub. Re-dubs and revivals
often localize *less* (the audience now knows the source culture). The audience you're translating
*for* may have grown up on an **earlier dub that localized more** — and that older dub may not be in
your corpus at all. So:

- Grep gives the **modern floor**.
- The **operator's lived memory of the classic dub overrides** it for *imprinted* terms.

Proof: a beloved term scored **0** corpus lines (the revival dropped it) yet is the name a whole
generation knows. The operator's "I grew up with this, 100%" is a real source; an LLM's recall is not.

## 5. Translate the memory, not the recipe

The goal is fidelity to what the audience *carries*, not to the literal source. If the classic dub
made a "mistake" the audience remembers fondly (e.g. renaming an unfamiliar food to a familiar one
that's technically wrong), **keep the beloved mistake** — it belongs in that world more honestly
than the accurate answer. A literal translator fixes it and is forgotten; a localizer keeps it and
lands. This is also the line a machine can't hold alone: it optimizes for *correct*; only someone
who *was that kid* can overrule the accurate answer with the true one. Grep finds the floor; the
operator supplies the soul.

## 6. Coins vs canon — flag, don't silently promote

When the corpus is silent and there's no operator memory, you still need *a* name to keep moving:

- **Coin it** in the dub's house style, using **dub-attested vocabulary** where possible (grep the
  individual *words* even if the full name isn't there — a coin built from real dub words beats one
  with invented words).
- **Flag it** in the per-game open-flags tracker (JP + function + offset). Never quietly present a
  coin as confirmed canon.
- Names are **consistent strings** → a wrong coin is a one-pass find-replace later, not a
  re-translation. Keep each spelled identically everywhere so the fix stays cheap. This is what
  makes it safe to coin-and-keep-moving instead of blocking on every name.

## 7. The loop, in one line

**propose → grep the corpus → (hit ⇒ canon) / (miss ⇒ coin + flag) → operator lived-memory can
override either way.** No blind guessing anywhere in the chain.

## 8. There is no unified canon — pick a lane, ship, invite collaboration

A long-running franchise usually has **several non-agreeing localizations**: an old dub and a newer
re-dub (different eras, different studios, different names for the same thing), multiple manga/print
editions, and a fan wiki with its own third set plus errors. They will never reconcile. Chasing a
single "true" name across all of them is a treadmill.

So pick **one base register** and be consistent:

- **Base = the most verifiable localization you actually hold** (here: the *revival* dub, because we
  have its full subtitle corpus and it's airing now as viewers return). "Grep-confirmed" therefore
  means *confirmed in that one register* — say so; never relabel it "canon."
- **Operator lived-memory overrides** the base for imprinted terms (§4, §5) — that's the rule, not an
  exception.
- **Everything else stays a faithful literal coin, flagged** (§6). Tag each confirmed name with its
  source (which dub/episode) so a later reader doesn't mistake one lane for universal truth.
- **Don't try to reconcile sources that disagree.** Record the disagreement and move on.

And the stance that makes this sustainable: **do your best, ship, invite collaboration.** The flagged
coins are an open door — helpful players supply the names the corpus can't (the real long-tail oracle);
indifferent players cost nothing; hostile nitpickers are not the maintainer's problem. A transparent
"here's what's confirmed, here's what's a coin, corrections welcome" beats a silent claim of false
perfection every time. Verifiability + honesty + an open door, not exhaustiveness.
