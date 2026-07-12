import { ref, watch, onBeforeUnmount } from 'vue'
import { useGamepads } from './useGamepads'

// Turns live DreamPicoPort gamepad state into the SAME /control/drive `hold` POSTs
// ControlKeyboard fires -- the server already resolves an arbitrary `btn` string through
// the mapping's `actions` (RoombaSink et al don't care whether a btn name came from a key
// press or a raw gamepad index), so this composable's only job is to detect PRESS/RELEASE
// edges on whichever BTN<n>/AXIS<n>+/AXIS<n>- keys the loaded mapping actually declares in
// `actions`, and post the same body shape. No hardcoded button list -- it reads directly
// off the mapping, so any future mapping (console pad, another target) works unchanged.
const AXIS_HOT = 0.5   // |value| above this counts as "pressed" for an axis-as-button key

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
  const actionKeys = ref<string[]>([])   // the BTN<n>/AXIS<n>+/- keys this mapping cares about
  const held = new Set<string>()

  async function fetchActionKeys() {
    actionKeys.value = []
    const src = opts.source(), map = opts.mapping()
    if (!src || !map) return
    try {
      const r = await fetch(`${API}/mappings/${src}/${map}`)
      const j = await r.json().catch(() => null)
      const actions = (j && j.actions) || {}
      actionKeys.value = Object.keys(actions).filter(k => /^(BTN\d+|AXIS\d+[+-])$/.test(k))
    } catch { actionKeys.value = [] }
  }
  watch([opts.source, opts.mapping], fetchActionKeys, { immediate: true })

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

  function releaseAllHeld() {
    for (const k of Array.from(held)) { held.delete(k); post(k, false) }
  }

  watch(pads, (list) => {
    if (!opts.active() || !opts.canDrive()) return
    const idx = opts.padIndex()
    const p = idx === null ? undefined : list.find(g => g.index === idx)
    if (!p) { releaseAllHeld(); return }

    for (const key of actionKeys.value) {
      let isDown = false
      const btnMatch = key.match(/^BTN(\d+)$/)
      const axisMatch = key.match(/^AXIS(\d+)([+-])$/)
      if (btnMatch) {
        isDown = !!p.buttons[Number(btnMatch[1])]?.pressed
      } else if (axisMatch) {
        const v = p.axes[Number(axisMatch[1])] ?? 0
        isDown = axisMatch[2] === '+' ? v > AXIS_HOT : v < -AXIS_HOT
      }
      const wasDown = held.has(key)
      if (isDown && !wasDown) { held.add(key); post(key, true) }
      else if (!isDown && wasDown) { held.delete(key); post(key, false) }
    }
  }, { deep: true })

  watch(() => [opts.active(), opts.canDrive()], ([a, c]) => { if (!a || !c) releaseAllHeld() })
  onBeforeUnmount(releaseAllHeld)

  return { actionKeys }
}
