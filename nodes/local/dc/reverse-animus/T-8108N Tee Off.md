# Tee Off (Dreamcast) — reverse animus

Acclaim, 2000. Cartoony, low-challenge golf (Hot Shots style). This seed separates
what's known from public data (high confidence) from what must be calibrated by
playing (Tee-Off-specific, currently unknown).

## Swing mechanic — public data, HIGH confidence
A classic three-click power meter (the "Swing-O-Meter"), 1 to 120% of the club's
distance rating:
1. **start** — a press starts the meter sweeping up.
2. **power** — a press at the top sets power (higher = farther, up to 120%).
3. **accuracy** — a press as the meter sweeps back down to the sweet spot at the
   bottom; dead-on = straight, early/late = hook/slice.

**Cautious mode** slows the meter (wider timing margin, less distance); **Standard**
is faster. Spin (topspin/backspin) and hooks/slices shape the shot. Clubs are picked
by terrain, distance, and shot angle.

## How the AI wins — the precision play
The meter is DETERMINISTIC, so don't react to it: **memorize the intervals and fire
the three presses open-loop on the Pico's local clock** (frame-perfect). The accuracy
press is the precision-critical one (where upstream jitter bites), so pre-load the
whole sequence to the Pico and let its clock fire it. `dt_accuracy` depends on where
the power press stopped (the down-sweep starts there), so calibrate accuracy timing
**per power level**.

## Calibration — LIVE play fills this (Tee-Off-specific, currently UNKNOWN)
The exact millisecond timings aren't published. Measure by playing:
- start in **Cautious** mode (widest timing margin to calibrate against).
- button: the swing button (confirm on the pad, likely A).
- `dt_power`    : start to power press, for a target power (e.g. 100%).   **TBD**
- `dt_accuracy` : power to accuracy press, hitting the sweet spot.        **TBD (per power)**

The coaching loop refines these ("too far" adjusts `dt_power`; pull/push adjusts
`dt_accuracy`), and the converged values live here for future frame-perfect replays.

## Watch-outs
- Confirm the meter actually runs start to power to accuracy on the first swing
  (some three-click variants add a separate swing-path press).
- Cautious first, Standard once the timings are nailed.

## Sources
- Three-click mechanic (general): PGA Tour 2K / EA "3-click swing" guides.
- Tee Off specifics: GameFAQs and the PlanetDreamcast review (1 to 120% Swing-O-Meter,
  Cautious/Standard modes, spin, Gate Ball mode).
