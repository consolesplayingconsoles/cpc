import { ref, onMounted, onUnmounted } from 'vue'

// 'cloud' = an off-network service buddy (cloud drive / LLM agent): present when
// configured, linked rather than pinged, so it never reports up/down.
export type NodeStatus = 'up' | 'down' | 'unconfigured' | 'cloud'

// One Pico board, parsed from the node's `.env` PICO_<chipid>=... line. The host
// (e.g. the Pi) declares its whole fleet this way; the drawer renders it so you can
// see what each locally-deployed board is for.
export interface PicoInfo {
  chipid: string
  alias:  string          // human label (dreamcast, wii) -- the rename-in-Pluto handle; empty when not declared
  iface:  string          // USB/HID profile the board presents: ps3 | generic | switch | xinput ... -- empty when not declared
  role:   string          // firmware / purpose
  conn:   string          // 'usb' | 'uart' -- empty when not declared (shown as unspecified)
  dev:    string          // uart device path (uart only)
  baud:   string          // uart baud (uart only)
  deploy: string          // 'pluto' (deploy pipeline flashes it) | 'pi' (you flash it locally) -- empty = unknown
}

export interface NodeData {
  id:     string
  name:   string
  ip:     string
  color:  string | null
  status: NodeStatus
  smb:    string | null
  // Per-node action-button availability. A node is expandable iff it has at
  // least one configured button; each button renders only when configured.
  deploy: boolean         // DEPLOY button — ship code to the node over SSH
  folder: boolean         // FILES button — open the node's SMB share
  code?:  boolean         // CODE button — open the source in the IDE (pluto only)
  os?:    string | null   // declared runtime; 'linux' shows a Tux on the bubble
  cloud?: boolean         // a cloud-cluster service buddy, not a pinged LAN node
  picos?: PicoInfo[]      // declared Pico fleet (nodes with PICO_<chipid>=... lines)
  controlTarget?: string | null  // CONTROL_TARGET group — this node is a subtarget of that Control target
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
