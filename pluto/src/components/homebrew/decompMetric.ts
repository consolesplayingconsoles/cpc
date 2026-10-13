// A decomp's main metric: the number that reads 100% when the project is complete. For a decomp
// the share that is equivalent C (an older report: matching C), for a disassembly the share
// that is equivalent source (rebuilt byte for byte as named, readable code and data). Every report puts it first; looking it
// up by label keeps a report that does not still right, and one with none of them falls back to
// its first percentage. Shared by the list's pill and the progress table's bold row.
export const MAIN_METRICS = ['done: equivalent C', 'matching C, bytes', 'done: equivalent source']

export interface Metric { label: string; pct: string }

export function mainMetric(text: string): Metric | null {
  const rows = text.split('\n')
    .map(l => /^\s+(.+?)\s{2,}(\d+(?:\.\d+)?%)/.exec(l))
    .filter((m): m is RegExpExecArray => m !== null)
    .map(m => ({ label: m[1], pct: m[2] }))
  return MAIN_METRICS.map(l => rows.find(r => r.label === l)).find(Boolean) ?? rows[0] ?? null
}

// The pill's colour moves with the number, from the bad tone at 0% to the ok tone at 100%: the
// same token pairs as every status pill, mixed. The number is always printed in the pill too.
export function progressStyle(pct: string): Record<string, string> {
  const p = Math.max(0, Math.min(100, parseFloat(pct) || 0))
  return {
    background: `color-mix(in oklab, var(--ok-soft) ${p}%, var(--bad-soft))`,
    color: `color-mix(in oklab, var(--ok-ink) ${p}%, var(--bad-ink))`,
  }
}
