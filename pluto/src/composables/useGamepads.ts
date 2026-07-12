import { ref, onMounted, onUnmounted } from 'vue'

// Raw HID gamepad state -- INDICES ONLY, no assumed button meaning. DreamPicoPort presents
// each of its 4 ports as a separate browser Gamepad (a DC wheel racer and a regular pad
// report DIFFERENT layouts), so we never hardcode "button 0 = A" here. This is the inspector
// layer: read what the browser reports, verbatim, so a mapping can be authored from what's
// ACTUALLY seen rather than guessed (the same "read real numbers first" approach as the
// Roomba telemetry -- don't assume, observe).
export interface GamepadSnapshot {
  index: number
  id: string            // the raw HID id string browsers report -- e.g. distinguishes wheel vs pad
  connected: boolean
  buttons: { pressed: boolean; value: number }[]
  axes: number[]
}

const POLL_MS = 50   // ~20fps: fast enough for responsive input, cheap enough to poll always

export function useGamepads() {
  const pads = ref<GamepadSnapshot[]>([])
  let raf = 0
  let timer = 0

  function poll() {
    const raw = navigator.getGamepads ? navigator.getGamepads() : []
    const out: GamepadSnapshot[] = []
    for (const gp of raw) {
      if (!gp) continue
      out.push({
        index: gp.index,
        id: gp.id,
        connected: gp.connected,
        buttons: gp.buttons.map(b => ({ pressed: b.pressed, value: b.value })),
        axes: Array.from(gp.axes),
      })
    }
    pads.value = out
  }

  function onConnChange() { poll() }

  onMounted(() => {
    poll()
    // setInterval (not a rAF loop) so it keeps sampling even when the tab is backgrounded
    // enough to matter for a drive input -- rAF throttles hard in inactive tabs.
    timer = window.setInterval(poll, POLL_MS)
    window.addEventListener('gamepadconnected', onConnChange)
    window.addEventListener('gamepaddisconnected', onConnChange)
  })
  onUnmounted(() => {
    if (timer) clearInterval(timer)
    if (raf) cancelAnimationFrame(raf)
    window.removeEventListener('gamepadconnected', onConnChange)
    window.removeEventListener('gamepaddisconnected', onConnChange)
  })

  return { pads }
}
