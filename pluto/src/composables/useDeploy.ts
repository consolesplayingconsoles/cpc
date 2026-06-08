import { ref } from 'vue'
import { API_BASE } from './useNodes'
import type { NodeMap } from './useNodes'

export interface DeployResult {
  raw:       string
  ok:        boolean | null  // null = in progress
  step:      string          // current step name
  startedAt: number          // epoch ms when this deploy began
}

// Remembered duration (ms) of the last SUCCESSFUL deploy per console, persisted
// across reloads so the terminal can show a "~last time" reference and the slow
// sync step feels predictable instead of hung.
const DURATIONS_KEY = 'cpc.deploy.lastMs'
function loadDurations(): Record<string, number> {
  try { return JSON.parse(localStorage.getItem(DURATIONS_KEY) || '{}') } catch { return {} }
}

const SUCCESS_BANNER = `
──────────────────────────────────────────────────
  DEPLOY SUCCESSFUL
──────────────────────────────────────────────────`

export function useDeploy(getNodes: () => NodeMap) {
  const deploying        = ref<string | null>(null)
  const deployOutput     = ref<Record<string, DeployResult | null>>({})
  const lastDurations    = ref<Record<string, number>>(loadDurations())
  const showToast        = ref(false)
  const toastConsoleName = ref('')
  const toastDuration    = ref('')

  function rememberDuration(id: string, ms: number) {
    lastDurations.value = { ...lastDurations.value, [id]: ms }
    try { localStorage.setItem(DURATIONS_KEY, JSON.stringify(lastDurations.value)) } catch { /* ignore */ }
  }

  function deploy(id: string) {
    if (id === 'host') {
      fetch(`${API_BASE}/workspace/${id}`, { method: 'POST' })
      return
    }

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
        rememberDuration(id, ms)   // only successful runs become the reference
        raw += SUCCESS_BANNER
        setTimeout(() => {
          toastConsoleName.value = getNodes()[id]?.name ?? id.toUpperCase()
          toastDuration.value    = `${elapsed}s`
          showToast.value        = true
          setTimeout(() => { showToast.value = false }, 4000)
        }, 600)
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

  async function openLocal(id: string) {
    await fetch(`${API_BASE}/open/${id}`, { method: 'POST' })
  }

  function clearOutput(id: string) {
    deployOutput.value = { ...deployOutput.value, [id]: null }
  }

  function dismissToast() { showToast.value = false }

  return {
    deploying, deployOutput, lastDurations,
    showToast, toastConsoleName, toastDuration,
    deploy, openLocal, clearOutput, dismissToast,
  }
}
