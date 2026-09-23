import { ref, shallowRef, isRef, type Ref } from 'vue'
import type { TerminalOutput } from '../components/Terminal.vue'

/**
 * Every streamed run (deploys, builds, sends, syncs) in one global list, shown as tabs in the
 * terminal drawer. Module-level, so a run outlives the tab that started it and two runs never
 * share one console.
 *
 * A producer opens a run and keeps writing to the ref it gets back. Pass a ref instead of an
 * initial output to mirror state the producer already owns (the deploy engine's per-node output).
 * A `key` makes a run reusable: opening the same key again focuses its tab instead of adding one.
 */
export interface Run {
  id:       number
  key?:     string
  title:    string
  output:   Ref<TerminalOutput>
  lastMs:   number | null
  onClose?: () => void
}

const runs     = shallowRef<Run[]>([])
const activeId = ref<number | null>(null)
const open     = ref(false)
// How many tabs fit the drawer's row at their minimum width (the drawer measures it). Past
// that, opening a run closes the oldest: finished runs go first, so a live one stays visible.
const maxRuns  = ref(7)
let seq = 0

function trim() {
  while (runs.value.length > Math.max(1, maxRuns.value)) {
    const victim = runs.value.find(r => r.output.value.ok !== null && r.id !== activeId.value)
      ?? runs.value.find(r => r.id !== activeId.value)
    if (!victim) return
    closeRun(victim.id)
  }
}

function setMaxRuns(n: number) {
  maxRuns.value = n
  trim()
}

function focus(id: number) {
  activeId.value = id
  open.value = true
}

function openRun(
  title: string,
  output: TerminalOutput | Readonly<Ref<TerminalOutput>>,
  opts: { key?: string; lastMs?: number | null; onClose?: () => void } = {},
): Ref<TerminalOutput> {
  const existing = opts.key ? runs.value.find(r => r.key === opts.key) : undefined
  if (existing) {
    runs.value = runs.value.map(r => r === existing ? { ...r, lastMs: opts.lastMs ?? null } : r)
    focus(existing.id)
    return existing.output
  }
  const run: Run = {
    id: ++seq, key: opts.key, title,
    output: (isRef(output) ? output : ref(output)) as Ref<TerminalOutput>,
    lastMs: opts.lastMs ?? null, onClose: opts.onClose,
  }
  runs.value = [...runs.value, run]
  focus(run.id)
  trim()
  return run.output
}

// Closing a tab only drops it from the drawer: a run still streaming finishes unseen.
function closeRun(id: number) {
  const i = runs.value.findIndex(r => r.id === id)
  if (i < 0) return
  runs.value[i].onClose?.()
  const next = runs.value.filter(r => r.id !== id)
  runs.value = next
  if (activeId.value === id) activeId.value = (next[i] ?? next[i - 1])?.id ?? null
  if (!next.length) open.value = false
}

export function useRuns() {
  return { runs, activeId, open, openRun, closeRun, focus, setMaxRuns }
}
