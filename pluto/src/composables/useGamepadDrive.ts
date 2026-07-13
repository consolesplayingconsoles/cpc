import { ref, watch, onBeforeUnmount } from 'vue'
import { useGamepads } from './useGamepads'
import { resolveDriveVerb, type DriveMapping } from '../lib/driveVerb'

// Live DreamPicoPort gamepad -> the SAME /control/drive `hold` POSTs the on-screen pad fires.
// Two kinds of input, handled differently (this is what the old version got wrong -- it fired
// every held key independently, so two directions FOUGHT instead of blending into an arc, and
// a face-button sound counted as "movement"):
//   MOVEMENT (dpad / stick / triggers -> drive-/turn- verbs): resolved to ONE blended verb via
//     the SHARED resolver (lib/driveVerb) so diagonals become forward-left etc., matching the
//     keyboard path exactly. Only a verb CHANGE is posted.
//   DISCRETE (face buttons -> robot/warble/horn/lights/session): fired once per press edge,
//     independent of movement, so pressing the horn while driving doesn't stop the drive.
const AXIS_HOT = 0.5   // |value| above this counts as "pressed" for an axis-as-button key
const isMoveVerb = (v: string) => /^(drive-|turn-|forward-|back-)/.test(v)

export function useGamepadDrive(opts: {
  active: () => boolean
  canDrive: () => boolean
  padIndex: () => number | null      // which gamepad to read; null = none selected
  source: () => string
  target: () => string
  mapping: () => string
  targetDev: () => string
  onError?: (msg: string) => void
}) {
  const API = `http://${window.location.hostname}:7700`
  const { pads } = useGamepads()
  const mapping = ref<DriveMapping | null>(null)
  const actionKeys = ref<string[]>([])          // the BTN<n>/AXIS<n>+/- keys this mapping declares
  const heldDiscrete = new Set<string>()        // discrete verbs currently held (one-shots)
  let activeMoveVerb: string | null = null       // the single blended movement verb in flight

  async function fetchMapping() {
    mapping.value = null; actionKeys.value = []
    const src = opts.source(), map = opts.mapping()
    if (!src || !map) return
    try {
      const r = await fetch(`${API}/mappings/${src}/${map}`)
      const j = await r.json().catch(() => null)
      if (j && !j.error) {
        mapping.value = { actions: j.actions || {}, combinations: j.combinations || {} }
        actionKeys.value = Object.keys(j.actions || {}).filter(k => /^(BTN\d+|AXIS\d+[+-])$/.test(k))
      }
    } catch { /* leave empty */ }
  }
  watch([opts.source, opts.mapping], fetchMapping, { immediate: true })

  async function post(btn: string, down: boolean) {
    if (!opts.canDrive()) return
    try {
      const r = await fetch(`${API}/control/drive`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'hold', down, btn,
          target: opts.target(), source: opts.source(), mapping: opts.mapping(),
          ...(opts.targetDev() ? { dev: opts.targetDev() } : {}),
        }),
      })
      const j = await r.json().catch(() => null)
      opts.onError?.(j && j.ok === false ? (j.error || 'hold failed') : '')
    } catch { opts.onError?.('API unreachable') }
  }

  // New movement verb DOWN before old goes UP -> the sink never sees an empty-held gap.
  function setMoveVerb(v: string | null) {
    if (v === activeMoveVerb) return
    if (v) post(v, true)
    if (activeMoveVerb) post(activeMoveVerb, false)
    activeMoveVerb = v
  }

  function releaseAll() {
    for (const v of Array.from(heldDiscrete)) { heldDiscrete.delete(v); post(v, false) }
    if (activeMoveVerb) { post(activeMoveVerb, false); activeMoveVerb = null }
  }

  watch(pads, (list) => {
    if (!opts.active() || !opts.canDrive()) return
    const idx = opts.padIndex()
    const p = idx === null ? undefined : list.find(g => g.index === idx)
    const m = mapping.value
    if (!p || !m || !m.actions) { releaseAll(); return }

    // 1) which declared action keys are down right now?
    const downKeys: string[] = []
    for (const key of actionKeys.value) {
      let isDown = false
      const btnMatch = key.match(/^BTN(\d+)$/)
      const axisMatch = key.match(/^AXIS(\d+)([+-])$/)
      if (btnMatch) isDown = !!p.buttons[Number(btnMatch[1])]?.pressed
      else if (axisMatch) {
        const v = p.axes[Number(axisMatch[1])] ?? 0
        isDown = axisMatch[2] === '+' ? v > AXIS_HOT : v < -AXIS_HOT
      }
      if (isDown) downKeys.push(key)
    }

    // 2) MOVEMENT: blend the down movement-keys into one verb (arcs via combinations)
    const moveKeys = downKeys.filter(k => isMoveVerb(m.actions![k] || ''))
    setMoveVerb(resolveDriveVerb(moveKeys, m))

    // 3) DISCRETE: sounds/lights/session -- one-shot per press edge, keyed by verb
    for (const key of actionKeys.value) {
      const verb = m.actions![key]
      if (!verb || isMoveVerb(verb)) continue
      const down = downKeys.indexOf(key) !== -1
      const was = heldDiscrete.has(verb)
      if (down && !was) { heldDiscrete.add(verb); post(verb, true) }
      else if (!down && was) { heldDiscrete.delete(verb); post(verb, false) }
    }
  }, { deep: true })

  watch(() => [opts.active(), opts.canDrive()], ([a, c]) => { if (!a || !c) releaseAll() })
  onBeforeUnmount(releaseAll)

  return { actionKeys }
}
