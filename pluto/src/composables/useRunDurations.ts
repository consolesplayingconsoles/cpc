import { ref } from 'vue'

/**
 * How long a run took last time, remembered per key and kept across reloads.
 *
 * The terminal pairs it with the live elapsed timer, so a slow step reads as predictable
 * rather than hung. Deploys key by node; homebrew builds key by item and action, because a
 * disc build and a send to a console take very different times.
 *
 * Keys follow the cpc.<domain>.<leaf> convention (see the storage-keys memory). Only
 * SUCCESSFUL runs are remembered: a run that failed early would make the next one look quick.
 */
export function useRunDurations(storageKey: string) {
  function load(): Record<string, number> {
    try { return JSON.parse(localStorage.getItem(storageKey) || '{}') } catch { return {} }
  }

  const durations = ref<Record<string, number>>(load())

  function remember(key: string, ms: number) {
    durations.value = { ...durations.value, [key]: ms }
    try { localStorage.setItem(storageKey, JSON.stringify(durations.value)) } catch { /* ignore */ }
  }

  return { durations, remember }
}
