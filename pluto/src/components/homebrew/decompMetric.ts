// A decomp's main metric: the number that reads 100% when the project is complete.
//
// progress.py 2.0 opens its report with three headline lines, not indented:
//   TOTAL TEST COVERAGE   82.8%            how much of the C the cases exercise (the quality figure)
//   FUNCTIONS LEFT  (91.0% complete) 299   functions still to do, and the share done
//   BYTES LEFT      (60.0% complete) 310622
// The main metric is the share of functions complete (what the old "done: equivalent C" row carried).
// An older report has the indented "done: equivalent C" / "matching C, bytes" / "done: equivalent
// source" rows instead; they are looked up by label, and a report that has none of either falls back
// to its first percentage, so a changed progress.py degrades, never breaks. Shared by the list's pill
// and the progress table's bold row.
export const MAIN_METRICS = ['done: equivalent C', 'matching C, bytes', 'done: equivalent source']

const COVERAGE = /^TOTAL TEST COVERAGE\s+(\d+(?:\.\d+)?%)(?:\s{2,}(.*))?$/
const LEFT = /^(FUNCTIONS|BYTES) LEFT\s+\((\d+(?:\.\d+)?%) complete\)\s+(\d+)(?:\s{2,}(.*))?$/

// One headline line of a 2.0 report as a table row (label, the number the bar shows, the rest), or null.
export function headline(line: string): { label: string; pct: string; detail: string } | null {
  const c = COVERAGE.exec(line)
  if (c) return { label: 'Test coverage', pct: c[1], detail: c[2] ?? '' }
  const l = LEFT.exec(line)
  if (l) {
    const what = l[1] === 'FUNCTIONS' ? 'Functions' : 'Bytes'
    return { label: what, pct: l[2], detail: `${l[3]} left${l[4] ? '  ' + l[4] : ''}` }
  }
  return null
}

export interface Metric { label: string; pct: string }

export function mainMetric(text: string): Metric | null {
  for (const line of text.split('\n')) {
    const h = headline(line)
    if (h && h.label === 'Functions') return { label: h.label, pct: h.pct }
  }
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
