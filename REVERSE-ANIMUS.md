# Reverse Animus: Rules of Engagement
    
In the Animus, a human relives an ancestor's memories through a machine. Reverse
animus inverts it: the machine relives the game. Claude plays a real console live,
on whatever console is in front of it. This doc is console-agnostic; ultimately
you play on any of them.

The roles:
* **Pluto is the eyes and limbs.** It sees through the capture and acts through the
  pad. Claude reads the frame and issues the inputs.
* **The operator is the guide**, coaching live through the **Guide Dog** channel
  (that is its name; do not rename it).

Status: the eyes-and-limbs integration is a first version, a partial POC with some
shortcuts in place to test the idea. Expect rough edges and confirm behavior live
rather than trusting the wiring blindly.

This file is the game-agnostic doctrine: the rules of engagement that hold for
every game and every console. Per-game playbooks live under
`nodes/local/<console>/reverse-animus/` and cover only that title (its controls,
structure, walkthrough, enemies). Keep those clean. Anything true across games or
consoles belongs here, and each game file backlinks here instead of repeating it.
This doc is also why the next game starts faster: the doctrine is already learned.

## Core principles
* **Guide dog over capture.** The operator guides Claude live through the Guide
  Dog channel, over the capture loop.
* **Record learnings.** Everything learned by playing goes back into these files
  (the knowledge base), so the next run and the next game start ahead.
* **Pre-process the image.** Frames are pre-processed before the read to make them
  easier to act on.
* **Lean on walkthroughs.** You have access to every guide and walkthrough ever
  written; use them. Positioning first, then the precise action.

## The loop
One turn is: a look is requested, you read the frame, decide one short action,
issue it, then wait for the next look.
* Capture is the external USB3 Video card only. Never a built-in camera or mic.
  This is a hard rule (see memory `feedback_never_laptop_camera`).
* **GO / WAIT / look** are operator signals on the control log. GO starts capture
  if it is not already running; WAIT logs a pause and does not stop the stream;
  **look** ("Take a look") is the operator asking you to read the current frame
  now. Free-text guidance rides the same log. Reads are operator-paced and cost,
  so play discrete, not continuous.
* The latest frame lives under a per-session capture dir namespaced by timestamp
  (`dist/<session>/latest`). Frames may be pre-processed before the read.
* Capture liveness runs on a kill-switch flag (`state.flag`) that anyone may
  write: Pluto on GO, the open page as a heartbeat, **you bump it on every frame
  read**, and a Stop button. A watchdog stops capture on `stop`, on staleness
  (nobody refreshed it), or at a max-duration cap. Bump it on each read and honor
  `stop` immediately. (Confirm exact paths live; the integration is still moving.)
* Below the frame, inputs leave as pad commands over the per-console adapter path
  (a drive watchdog stops the drive if the player's keepalive goes silent). The
  contract is "read frame, emit pad input"; the pipeline beneath is config, not
  contract, and differs per console.
* Driving the console is a write action on physical hardware. The signals above,
  the kill-switch, and operator presence are the safety layer; the per-action
  discipline in [`SECURITY.md`](./SECURITY.md) applies.

## Talking to the guide
The operator guides you over the Guide Dog coaching feed: free text on the control
log, plus the look button. Post your observation, your intended next move, and any
blocker or question into it so the operator can correct you before you commit.
But **guidance is optional**: the loop must never block waiting for a reply. If
none comes, act on the frame and the playbook and keep going.

## The latency reality
The round trip (capture, read, decide, command, render) is far slower than a human
reflex window, so anything needing a frame-accurate reaction loses. Convert every
problem into a latency-proof form:

1. **Position, not timing.** Prefer outcomes that depend on where the avatar is,
   not on reacting within milliseconds. Plan from one frame, fire the move
   open-loop, then re-read.
2. **Slow the game to the loop.** Walk, do not run, near hazards. Use any
   "careful" or "cautious" mode on offer. Open menus to buy thinking time.
3. **Save constantly.** Save before every risky action and reload on any bad
   outcome. Detect that outcome from the frame (health, position, death); reload
   is itself a menu sequence you drive, not one button. This is the single biggest
   lever: it turns a reflex problem into a retry problem.
4. **Discrete, not continuous.** One frame, one short move sequence, re-read. No
   long blind runs; discrete is recoverable.

## Inputs are held: calibrate distance as time
You never move "two tiles"; you hold a direction for a duration. Each game needs
its movement units measured and recorded: how long to hold to cross one tile or
take one step, how long for a 90-degree turn, how long a press for a standing
versus a running jump. Measure them once, store them in the game file, and fire
them open-loop. Without them, the grid plan has no mapping to a real input. Treat
them as LIVE/TBD until measured.

## Combat: avoid, then dodge, then fight
Reflexes are slow, so take the fewest, lowest-risk engagements possible.
* **Avoid first.** Run past trivial enemies. Take high ground they cannot reach.
  Break line of sight against ranged or projectile enemies (use cover). Skip
  every optional fight.
* **Dodge second.** Exploit any auto-aim or lock-on the game gives you so you
  never have to aim: your only job becomes movement (retreat while firing, strafe,
  reverse). Stay off the enemy's aim line.
* **Fight last, only when forced.** Save first, every time. Find the weak point
  and the cover, then commit.

## Timed sections
The one place latency truly bites. For each: scout the whole path first, save, run
it open-loop with any sprint or burst reserved for it, and retry from the save
until it lands. Never improvise a timed run live.

## Confidence tiers
Mark every claim so the driver knows what to trust:
* **ENGINE / public**: documented, true across the engine or platform. High
  confidence, act on it.
* **Platform-confirmed**: verified for this exact console build (a button read off
  the in-game Controls screen, or validated on the pad).
* **LIVE / TBD**: must be calibrated by playing. State it as unknown and fill it
  in once measured.

Never present a guess as confirmed.

## Control validation (the guide-dog practice)
Controls are the first thing to lock, and the start of a game is the safe place to
do it, over chat:
* At game start, walk the operator through the proposed mapping over the guide-dog
  chat. The operator uses the assist to press each binding and validate it live.
* Resolve every unknown binding against the in-game Options/Controls screen read
  off the capture, plus the operator's test.
* Write confirmed bindings back into the game file and promote them to
  Platform-confirmed. Never assume a binding you have not seen on screen or had
  validated.

## Per-game playbook: the proven format
A shared structure is a shared value: one format means the next game is faster to
write and faster to drive from. The order below is the proven shape (it goes
top-down, from how to operate the game to the specifics of playing it). Treat it
as a loose template, not a contract: drop sections that do not apply, add ones a
title demands.

* Location: `nodes/local/<console>/reverse-animus/`
* Name: `<disc serial> <Game Title>.md` (e.g. `T-36815D Tomb Raider 5: Chronicles.md`).
* Backlink to this file near the top, then do not restate doctrine.

Canonical sections, in order:
1. **Header and framing**: game, serial, engine, one line on the title, backlink
   to this RoE.
2. **Menu and boot**: title-screen flow, where the Controls screen lives, how
   saving works, the inventory model.
3. **Controls**: a confidence-tiered table (move, function, reference binding,
   this-console binding). Unknowns marked, not guessed.
4. **Engine and game facts**: the few mechanics that shape play (movement model,
   what Walk does, the save model, any auto-aim or lock-on).
5. **Signature moves**: the traversal and combat primitives worth pre-canning.
6. **Enemies and avoidance**: this game's application of the combat doctrine, plus
   a table (enemy, where, threat, plan).
7. **Game structure**: the macro map (acts or levels) and where you start.
8. **Walkthrough**: the early levels as route beats, with timed sections flagged.
9. **Calibration / LIVE**: the TBDs to fill by playing.
10. **Sources**: a citation for every public claim.

## Voice and format
* Concise technical writing, not narrative. Terse and scannable.
* Address the driver directly (imperative).
* No dash-as-pause. Use colons, commas, parentheses, periods. Keep real
  hyphenated compounds.
* ASCII only. Plain `-`, `|`, `+` if you need a symbol.
* Cite a source for any public claim.
