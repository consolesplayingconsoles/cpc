# Tee Off (Dreamcast)

T-8108N. Acclaim, 2000. Cartoony, low-challenge golf (Hot Shots style). Seed,
untested: this file separates public data (high confidence) from what must be
calibrated by playing (Tee Off specific, currently unknown).

Operating doctrine (the loop, latency, confidence tiers, the Guide Dog, this
file's format) lives in [`REVERSE-ANIMUS.md`](../../../../REVERSE-ANIMUS.md). This
file is Tee Off only.

## Engine and game facts (public, HIGH confidence)
A classic three-click power meter (the "Swing-O-Meter"), 1 to 120% of the club's
distance rating:
1. **start**: a press starts the meter sweeping up.
2. **power**: a press at the top sets power (higher is farther, up to 120%).
3. **accuracy**: a press as the meter sweeps back down to the sweet spot at the
   bottom. Dead-on is straight; early or late is a hook or slice.

**Cautious mode** slows the meter (wider timing margin, less distance); **Standard**
is faster. Spin (topspin/backspin) and hooks/slices shape the shot. Clubs are
picked by terrain, distance, and shot angle.

## Signature play: beat the meter open-loop
The meter is DETERMINISTIC, so do not react to it. Memorize the intervals and fire
the three presses open-loop, pre-loaded as one sequence (RoE timed-section
doctrine). The accuracy press is the precision-critical one, where upstream jitter
bites. `dt_accuracy` depends on where the power press stopped (the down-sweep
starts there), so calibrate accuracy timing **per power level**.

## Controls
Minimal and unconfirmed. The swing button is likely A; validate on the pad over
the Guide Dog before driving. **TBD.**

## Calibration / LIVE (fill by playing)
The exact millisecond timings are not published. Measure by playing:
* Start in **Cautious** mode (widest timing margin to calibrate against).
* `dt_power`: start to power press, for a target power (e.g. 100%). **TBD.**
* `dt_accuracy`: power to accuracy press, hitting the sweet spot. **TBD (per power).**

The coaching loop refines these ("too far" adjusts `dt_power`; pull or push adjusts
`dt_accuracy`), and the converged values live here for future replays.

## Watch-outs
* Confirm the meter actually runs start, power, accuracy on the first swing (some
  three-click variants add a separate swing-path press).
* Cautious first, Standard once the timings are nailed.

## Sources
* Three-click mechanic (general): PGA Tour 2K / EA "3-click swing" guides.
* Tee Off specifics: GameFAQs and the PlanetDreamcast review (1 to 120%
  Swing-O-Meter, Cautious/Standard modes, spin, Gate Ball mode).
