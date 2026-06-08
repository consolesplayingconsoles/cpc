import { ref, onMounted, onUnmounted } from 'vue'
import { API_BASE } from './useNodes'

export interface Message {
  id:     number
  sender: string
  text:   string
  ts:     string   // ISO 8601 UTC from the API, e.g. "2024-01-01T12:00:00Z"
}

const POLL_MS = 3000

// ── Module-level singleton — shared across all consumers ─────────────────────
const messages = ref<Message[]>([])
const lastId   = ref(0)
let   _timer:    ReturnType<typeof setInterval> | null = null
let   _refcount  = 0

async function _poll() {
  try {
    const res = await window.fetch(`${API_BASE}/messages?since=${lastId.value}`)
    if (!res.ok) return
    const data: Message[] = await res.json()
    if (data.length > 0) {
      messages.value.push(...data)
      lastId.value = data[data.length - 1].id
    }
  } catch {
    // API unreachable — silent, status indicator in the header handles this
  }
}

async function sendMessage(sender: string, text: string) {
  try {
    const res = await window.fetch(`${API_BASE}/messages`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ sender, text }),
    })
    if (!res.ok) return
    const msg: Message = await res.json()
    messages.value.push(msg)
    lastId.value = msg.id
  } catch {}
}

export function useMessages() {
  onMounted(() => {
    if (_refcount === 0) {
      _poll()
      _timer = setInterval(_poll, POLL_MS)
    }
    _refcount++
  })

  onUnmounted(() => {
    _refcount--
    if (_refcount === 0 && _timer) {
      clearInterval(_timer)
      _timer = null
    }
  })

  return { messages, sendMessage }
}
