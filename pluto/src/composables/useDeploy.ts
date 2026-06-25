import { ref } from 'vue'
import { API_BASE } from './useNodes'
import type { NodeMap } from './useNodes'
import { useAchievement } from './useAchievement'

export interface DeployResult {
  raw:       string
  ok:        boolean | null  // null = in progress
  step:      string          // current step name
  startedAt: number          // epoch ms when this deploy began
}

// Remembered duration (ms) of the last SUCCESSFUL deploy per console, keyed BY NODE
// id and persisted across reloads, so the terminal can show a "~last time" reference
// and the slow sync step feels predictable instead of hung. The ETA references only
// the SAME node's past runs. The pi's Pico propagation is a STEP of its deploy, so
// flashing more boards lengthens this number -- that drift is expected, not a bug.
// (Key follows the cpc.<domain>.<leaf> convention; see the storage-keys .claude memory.)
const DURATIONS_KEY = 'cpc.deploy.lastMs'
function loadDurations(): Record<string, number> {
  try { return JSON.parse(localStorage.getItem(DURATIONS_KEY) || '{}') } catch { return {} }
}

// When (epoch ms) each node last deployed successfully, keyed BY NODE id. Parallel to
// lastMs (duration); this is the timestamp. Lets the drawer show "last deployed N ago"
// for any deployable node (pi, pluto, the python clients) -- the pi's covers its Picos
// too, since their flashing is a step of the pi deploy.
const LASTAT_KEY = 'cpc.deploy.lastAt'
function loadLastAt(): Record<string, number> {
  try { return JSON.parse(localStorage.getItem(LASTAT_KEY) || '{}') } catch { return {} }
}

const SUCCESS_BANNER = `
──────────────────────────────────────────────────
  DEPLOY SUCCESSFUL
──────────────────────────────────────────────────`

export function useDeploy(getNodes: () => NodeMap = () => ({})) {
  const { unlock } = useAchievement()

  const deploying        = ref<string | null>(null)
  const deployOutput     = ref<Record<string, DeployResult | null>>({})
  const lastDurations    = ref<Record<string, number>>(loadDurations())
  const lastDeployedAt   = ref<Record<string, number>>(loadLastAt())

  function rememberDuration(id: string, ms: number) {
    lastDurations.value = { ...lastDurations.value, [id]: ms }
    try { localStorage.setItem(DURATIONS_KEY, JSON.stringify(lastDurations.value)) } catch { /* ignore */ }
  }

  function rememberDeployedAt(id: string, at: number) {
    lastDeployedAt.value = { ...lastDeployedAt.value, [id]: at }
    try { localStorage.setItem(LASTAT_KEY, JSON.stringify(lastDeployedAt.value)) } catch { /* ignore */ }
  }

  function deploy(id: string) {
    const startedAt    = Date.now()
    deploying.value    = id
    deployOutput.value = { ...deployOutput.value, [id]: { raw: '', ok: null, step: 'starting', startedAt } }

    const es = new EventSource(`${API_BASE}/deploy/${id}/stream`)

    function current() { return deployOutput.value[id] }

    es.addEventListener('line', (e: MessageEvent) => {
      const c = current()
      if (!c) return
      deployOutput.value = { ...deployOutput.value, [id]: { ...c, raw: c.raw + e.data + '\n' } }
    })

    es.addEventListener('step', (e: MessageEvent) => {
      const c = current()
      if (!c) return
      deployOutput.value = { ...deployOutput.value, [id]: { ...c, step: e.data } }
    })

    es.addEventListener('done', (e: MessageEvent) => {
      es.close()
      const ok      = e.data === 'ok'
      const ms      = Date.now() - startedAt
      const elapsed = (ms / 1000).toFixed(1)
      const c       = current()
      let raw       = c?.raw ?? ''

      if (ok) {
        rememberDuration(id, ms)        // only successful runs become the reference
        rememberDeployedAt(id, Date.now())
        raw += SUCCESS_BANNER
        const name = getNodes()[id]?.name ?? id.toUpperCase()
        setTimeout(() => unlock(`Successfully Deployed to ${name}`, `${elapsed}s`), 600)
      }

      deployOutput.value = { ...deployOutput.value, [id]: { raw, ok, step: ok ? 'done' : 'failed', startedAt } }
      deploying.value    = null
    })

    es.onerror = () => {
      es.close()
      const c = current()
      deployOutput.value = {
        ...deployOutput.value,
        [id]: { raw: (c?.raw ?? '') + '\n[connection lost]', ok: false, step: 'failed', startedAt },
      }
      deploying.value = null
    }
  }

  function clearOutput(id: string) {
    deployOutput.value = { ...deployOutput.value, [id]: null }
  }

  return {
    deploying, deployOutput, lastDurations, lastDeployedAt,
    deploy, clearOutput,
  }
}
