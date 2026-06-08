import { ref, onMounted, onUnmounted } from 'vue'

export type NodeStatus = 'up' | 'down' | 'unconfigured'

export interface NodeData {
  id:     string
  name:   string
  ip:     string
  color:  string | null
  status: NodeStatus
  smb:    string | null
  // Per-node action-button availability. A node is expandable iff it has at
  // least one configured button; each button renders only when configured.
  deploy: boolean   // DEPLOY button (console) / CODE button (host)
  folder: boolean   // FILES button (console SMB) / DIR button (host LOCAL_PATH)
}

export type NodeMap = Record<string, NodeData>

// Derive from the page's hostname so the same build works on localhost
// and when accessed via the LAN IP — no extra env config required.
export const API_BASE = `http://${window.location.hostname}:7700`
const POLL_MS  = 5000

export function useNodes() {
  const nodes   = ref<NodeMap>({})
  const loading = ref(true)
  const error   = ref<string | null>(null)
  let   timer:  ReturnType<typeof setInterval> | null = null

  async function fetch() {
    try {
      const res  = await window.fetch(`${API_BASE}/nodes`)
      nodes.value   = await res.json()
      error.value   = null
    } catch (e) {
      error.value = 'api unreachable'
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    fetch()
    timer = setInterval(fetch, POLL_MS)
  })

  onUnmounted(() => {
    if (timer) clearInterval(timer)
  })

  return { nodes, loading, error }
}
