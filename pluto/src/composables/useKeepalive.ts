import { onUnmounted } from 'vue'

// A periodic "still here" POST, for backends that hold something open only while
// Pluto keeps saying so: the drive sink (pluto-drive), AI mode on the roomba
// handset (modules/fxos/listen.py). The backend's watchdog does the real work --
// this just has to stop when we stop caring, so a closed tab, a navigated-away
// browser or a crashed Pluto all release whatever was being held.
//
// Lifted out of ControlKeyboard.vue and KinectControl.vue, which grew the same
// eight lines independently, when AI mode would have made three.
//
// onUnmounted(stop) is the part the hand-rolled copies did not have: they relied
// on their own teardown() being called. For something that holds a MICROPHONE
// open, "we forgot to call teardown on this path" is not an acceptable failure
// mode, so unmount always stops the pings.

export interface KeepaliveOptions {
  url: string
  body?: unknown
  intervalMs?: number
  // Checked before every ping, not just at start: a source that loses the right
  // to drive mid-hold should stop asserting it immediately.
  guard?: () => boolean
}

export function useKeepalive(opts: KeepaliveOptions) {
  const intervalMs = opts.intervalMs ?? 2000
  let timer = 0

  function ping(): void {
    if (opts.guard && !opts.guard()) return
    window.fetch(opts.url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(opts.body ?? {}),
    }).catch(() => { /* a missed ping is what the watchdog is for */ })
  }

  function start(): void {
    if (timer) return
    if (opts.guard && !opts.guard()) return
    // Ping immediately: waiting a full interval leaves a window where the
    // backend thinks nobody is watching yet.
    ping()
    timer = window.setInterval(ping, intervalMs)
  }

  function stop(): void {
    if (timer) { window.clearInterval(timer); timer = 0 }
  }

  onUnmounted(stop)

  return { start, stop, running: (): boolean => timer !== 0 }
}
