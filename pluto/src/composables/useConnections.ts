import { ref, onMounted, onUnmounted } from 'vue'
import { API_BASE } from './useNodes'

export interface Connection {
  from:  string
  to:    string
  label: string
}

const POLL_MS = 5000

export function useConnections() {
  const connections = ref<Connection[]>([])

  async function fetch() {
    try {
      const res = await window.fetch(`${API_BASE}/connections`)
      connections.value = await res.json()
    } catch { /* ignore — nodes error state covers this */ }
  }

  let timer: ReturnType<typeof setInterval> | null = null
  onMounted(() => { fetch(); timer = setInterval(fetch, POLL_MS) })
  onUnmounted(() => { if (timer) clearInterval(timer) })

  return { connections }
}
