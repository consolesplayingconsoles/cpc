import { ref } from 'vue'
import { API_BASE } from './useNodes'
import type { NodeMap } from './useNodes'

export interface DeployResult { raw: string; ok: boolean }

const SUCCESS_BANNER = `
──────────────────────────────────────────────────
  ✔ DEPLOYMENT SUCCESSFUL
──────────────────────────────────────────────────`

export function useDeploy(getNodes: () => NodeMap) {
  const deploying        = ref<string | null>(null)
  const deployOutput     = ref<Record<string, DeployResult | null>>({})
  const showToast        = ref(false)
  const toastConsoleName = ref('')
  const toastDuration    = ref('')

  async function deploy(id: string) {
    if (id === 'host') {
      await fetch(`${API_BASE}/workspace/${id}`, { method: 'POST' })
      return
    }
    deploying.value    = id
    deployOutput.value = { ...deployOutput.value, [id]: null }

    const startTime = performance.now()
    try {
      const res  = await fetch(`${API_BASE}/deploy/${id}`, { method: 'POST' })
      const data = await res.json()
      let raw = String(data.output ?? data.error ?? '').replace(/\n{3,}/g, '\n\n').trim()

      const elapsed = ((performance.now() - startTime) / 1000).toFixed(2)

      if (data.status === 'ok') {
        raw = `${raw}\n${SUCCESS_BANNER}`
        setTimeout(() => {
          toastConsoleName.value = getNodes()[id]?.name ?? id.toUpperCase()
          toastDuration.value    = `${elapsed}s`
          showToast.value        = true
          setTimeout(() => { showToast.value = false }, 4000)
        }, 800)
      }

      deployOutput.value = { ...deployOutput.value, [id]: { raw, ok: data.status === 'ok' } }
    } finally {
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
    deploying, deployOutput,
    showToast, toastConsoleName, toastDuration,
    deploy, openLocal, clearOutput, dismissToast,
  }
}
