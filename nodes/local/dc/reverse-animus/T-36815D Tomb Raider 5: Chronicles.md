# Tomb Raider Chronicles (Dreamcast)

T-36815D. Core Design / Eidos, 2000. The fifth game, running the classic Tomb
Raider engine (TR1 through TR4 share it). You drive Lara live off the capture
frame. This is the pilot game file.

Operating doctrine (the loop, latency, save-scum, avoid-then-fight, confidence
tiers, the format of this file) lives in [`REVERSE-ANIMUS.md`](../../../../REVERSE-ANIMUS.md).
This file is Tomb Raider Chronicles only.

## Menu and boot
* **Title screen**: New Game / Load Game / Options. Start opens menus.
* **First action each session**: open Options and read the **Controls** screen off
  the capture frame. It is ground truth for the live pad mapping. Reconcile it
  against the table below and validate over the guide-dog chat before driving.
* **Saving**: anywhere, through the inventory ring (Save Game icon), to the VMU.
  Title screen has Load. Confirm a VMU is mounted before relying on saves.
* **Inventory ring**: one ring with pistols and other weapons, medipacks (small
  and large), flares, the headset, found items, the TMX watch, and the save/load
  icons. Rotate to an item, press Action to use or equip.
* **Soft reset / bail**: hold A + B + X + Y + Start together to return to the
  title screen (documented for the DC version).

## Controls
Functional moves are ENGINE-certain. PlayStation is the documented reference the
DC pad mirrors. The Dreamcast column mixes Platform-confirmed bindings with an
operator reference that is not fully reliable: validate every `op-ref` and `?` on
the pad before trusting it.

| Move | Function | PlayStation (ref) | Dreamcast |
|------|----------|-------------------|-----------|
| Run / back / turn | Up run, Down hop back, Left/Right **rotate** (tank steering, not strafe) | D-pad / stick | D-pad / stick (ENGINE) |
| Walk (hold) | Slow; cannot fall off an edge or trip a trap tile | R1 | **B** (op-ref, validate) |
| Sidestep | Strafe without turning | R1 + Left/Right | **B + Left/Right** (op-ref) |
| Jump | Standing (1 tile); add direction for a directional jump | Square | **X** (by elimination, validate) |
| Action | Grab, pull, lever, pick up, **fire weapon** | Action btn | **A (confirmed)** |
| Draw / holster | Ready or stow weapon | Triangle | **Y** (op-ref, validate) |
| Roll | Instant 180 turn-around | Circle | `?` (TBD) |
| Look | Free-look to survey | L1 + D-pad | `?` (TBD) |
| Duck / crawl | Crouch, then crawl with direction | L2 | `?` (op-ref: crouch into a crawlspace via Action; validate) |
| Sprint | Burst speed, drains stamina | R2 | **R trigger** (op-ref) |
| Zoom (sight up) | In / out / reset while aiming a laser sight or binoculars | n/a | **R in, B out, Y normal (confirmed)** |
| Inventory | Open the ring | Select | `?` (likely Start) |

Note the modal triggers: R is Sprint in normal play but Zoom-in while a laser
sight or binoculars is raised; B is Walk normally but Zoom-out while a sight is up.

## Engine and game facts
* **Grid world.** The level is a grid of square tiles; height is measured in
  clicks (4 per tile). Movement quantizes to it, so traversal is predictable: plan
  a tile-by-tile route off one frame and fire it open-loop. Standing jump clears
  about one tile, running jump about two.
* **Walk is the safety.** Holding Walk (B), Lara stops at the lip of any drop and
  will not enter a marked trap tile. Default to Walk near anything dangerous.
* **Save anywhere.** Through the inventory ring to the VMU. Save before every jump
  chain, fight, and trap; reload on a bad outcome.
* **Auto-aim.** With weapons drawn (Y) and Fire held (A), Lara locks and tracks
  the nearest enemy on her own. You never aim. You can run, jump, and roll while
  firing and she keeps the lock. Pistols carry infinite ammo.

## Signature moves
* **Running jump + grab**: walk to the edge, step back once, run forward, Jump,
  hold Action through the landing to catch a ledge (~2 tiles).
* **Standing jump + grab**: Jump, then hold Action to catch a ledge one tile out.
* **Safe ledge grab (no timing)**: walk to the edge, hop back one step, standing
  jump with Action held. Deterministic; use it instead of running off drops.
* **Swan dive**: run, Jump, then immediately Action.
* **Safety drop**: at an edge with Lara's back to it, Back + Action to hang, then
  release to drop one storey with little damage.
* **Shimmy**: while hanging (Action held), Left/Right to traverse, Up to pull up.
* **Roll**: instant 180, the core combat dodge and overshoot recovery (button TBD).

## Enemies and avoidance
Doctrine: avoid, then dodge, then fight (see RoE). Tomb Raider specifics:
* **Auto-aim turns combat into movement.** Draw, hold Fire, and your only job is to
  keep moving. Back-hop (hold Fire, tap Back) kills dogs and gunmen before they
  close; pistols never run dry, so favour them for chip damage.
* **Dogs lose to height.** Dobermans cannot climb or jump high. Vault onto a crate
  or ledge and they are harmless.
* **Ignore the trash.** Bats and rats do trivial damage and are hard to hit. Walk
  or run past them to the objective.
* **Fireball throwers lose to cover.** Strafe and keep a pillar, statue, or arena
  structure between you and the enemy to break line of sight.

| Enemy | Where | Threat | Plan |
|-------|-------|--------|------|
| Doberman (about 5) | Streets of Rome | Fast lunge bite, low HP | High ground if available, else back-hop + pistols |
| Bats | Streets of Rome | Trivial, cannot be killed | Ignore, keep moving |
| Rats (swarm) | Rome (barrel/wine store) | Trivial | Run through |
| Larson / Pierre | Streets of Rome (end) | Cutscene only here | None, watch it |
| Mechanical head | Trajan's Markets | Fireballs; eyes are the weak point | Laser-sight revolver on the eyes, strafe between shots |
| Mechanical centurion | Trajan's Markets | Tanky melee | Shotgun, keep circling |
| Larson | Trajan's Markets (garden) | Human gunman | Back-hop + auto-aim, use cover |
| Mechanical gargoyles (3) | Trajan's Markets | Fireballs | Strafe, hide behind the central structure to break LoS and regen |

## Game structure
Four self-contained tales told by Lara's friends, twelve levels total. You start
in **Rome**:
1. Streets of Rome
2. Trajan's Markets
3. The Colosseum

Then Russia (The Base, The Submarine, Deepsea Dive, Sinking Sub), Ireland as young
Lara (Gallows Tree, Labyrinth, Old Mill), and the VCI tower (13th Floor, Escape
with the Iris, Red Alert!). Rome hands Lara her full early kit (pistols, revolver +
laser sight, shotgun), so it is the right place to drill the combat doctrine.

## Walkthrough: Level 1, Streets of Rome
Objective: recover the **Saturn Symbol** for the Philosopher's Stone while rivals
Larson and Pierre circle. The route may open with a short backstage/training
stretch (vaulting, jumps, monkey-swing, swim, tightrope); confirm the opening
against the capture frame rather than assuming.

1. **Into the streets.** A Doberman charges from the first alley: high ground or
   back-hop it. You reach a **fountain courtyard** that is the level hub.
2. **Two-face (Mouth of Truth) mechanism, the one timed bit.** Operating the first
   carved face opens a distant gate; reach and operate the second face before it
   closes (about a 16-second window). Scout the full path first, save, then run it
   with **Sprint** reserved for it, retrying from save. Bats appear after: ignore.
3. **Buildings and dogs.** About five Dobermans total across the level. Lure to
   open space or take high ground; do not get cornered in doorways.
4. **Two Garden Keys.** One in a room of stacked boxes; the other past a rat-swarm
   wine-barrel store (run through the rats).
5. **Revolver + Laser Sight.** Combine them in the ring, then shoot the **padlock**
   on the garden gate. Use both Garden Keys to open the walled garden.
6. **Mercury Stone** into its receptacle in the garden opens a temple with a
   **bell**: shoot the bell with the laser-sighted revolver to progress.
7. **Raven-to-dove puzzle.** Switches turn raven statues into doves; rotating the
   dove pedestals opens doors and arms a swinging battering ram. Cross on Walk,
   timed to the swing, or save and retry. Do not improvise it live.
8. **Saturn Symbol** sits at the temple base. Take it. On exit, Pierre and Larson
   ambush in a cutscene and the receptacle torches Larson. Level ends, on to
   Trajan's Markets.

Notable: small and large medipacks through the buildings; three golden rose
secrets if you want them (optional, skip on a first clear).

## Walkthrough: Level 2, Trajan's Markets
Objective: collect the **Mars** and **Venus** symbols and open the exit.

1. **Opening street.** Grab the **laser sight** and **crowbar** from the two
   flanking buildings. Crowbar a corrugated metal door, then cross scaffolding and
   a tightrope (Walk it, save first) for shotgun shells and supplies.
2. **Two rope/gear rooms.** Pull the vertical rope in the first room once to arm
   the gears, then pull the rope in the second room to open a large circular door
   and reveal a trapdoor.
3. **Trapdoor secret (optional).** Drop through for the first golden rose and ammo.
4. **Golden coin.** Behind the circular door take the ramps down and crowbar a
   **golden coin** from a torch-lit chamber (run through the rats). Place it in a
   statue receptacle to open a gate.
5. **Mechanical head.** Across a pool. Laser-sighted revolver, shoot both **eyes**,
   strafe between shots. Yields the **Mars Symbol**.
6. **Valve wheel and sewers.** Drop through a manhole into sewers with an
   underwater fan. Crowbar the **valve wheel** from a pipe room, fit it to the red
   machine above to stop the fan, then swim the now-safe tunnels.
7. **Shotgun and the centurion.** Take the shotgun in a pool room, then fight the
   **mechanical centurion** with it while circling. Opens the way to **Venus**.
8. **Larson + gargoyles.** Take the Venus Symbol. Larson appears in a garden
   (back-hop + cover), then three **mechanical gargoyles** throw fireballs: strafe
   and use the central structure as cover to break line of sight and regenerate.
9. **Exit.** Place Mars and Venus in their receptacles to open the final gate.
   Running-jump a spike pit onto a collapsing ledge and slide into the next level.

Notable: small and large medipacks throughout. Save before the head, the
centurion, and the gargoyles.

## Walkthrough: Level 3, The Colosseum
TBD (fill on the next pass). Closes the Rome tale; expect more climbing and the
same mechanical-enemy family, so cover-and-strafe carries over.

## Calibration / LIVE (fill by playing)
* Lock the real Dreamcast mapping from Options > Controls and validate over the
  guide-dog chat. Resolve Roll, Look, Duck/crawl, Inventory; confirm B=Walk,
  X=Jump, Y=Draw, R=Sprint. **TBD.**
* Movement units (hold durations, fired open-loop): ms to walk one tile, ms to run
  one tile, ms for a 90-degree turn, press length for a standing jump and a
  running jump. **TBD.**
* Reload drill: read the health bar each frame; the reload path is ring > Load >
  confirm (a menu sequence). Time it once. **TBD.**
* Confirm whether this build opens with a training/backstage stretch, and its
  exits. **TBD.**
* Measure the two-face timer and the sprint route that beats it. **TBD.**
* Record which enemies can be skipped vs. forced, per room, as you clear them. **TBD.**

## Sources
* Controls (PC/PlayStation reference) and game info: Stella's Tomb Raider Site,
  [TR5 controls](https://tombraiders.net/stella/walks/controls/TR5controls.html).
* Dreamcast bindings: operator reference (validate) plus the DC manual notes
  (A = Action/Fire; laser-sight zoom on R/B/Y confirmed).
* Level routes: Stella's TR5 walkthrough,
  [Streets of Rome](https://tombraiders.net/stella/walks/TR5walk/01-streets.html),
  [Trajan's Markets](https://tombraiders.net/stella/walks/TR5walk/02-trajan.html).
