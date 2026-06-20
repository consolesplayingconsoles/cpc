import { ref, computed } from 'vue'
import { API_BASE } from './useNodes'

// WHO YOU ARE on this instance — shared singleton so the global header (shows/edits
// it) and the chat (sends as it) agree. Either the server recognizes your IP as a
// known node (authoritative, locked) or you're an editable guest whose name persists
// in localStorage (cpc.<domain>.<leaf> convention; see the storage-keys .claude memory).
const GUEST_KEY     = 'cpc.chat.name'
const GUEST_KEY_OLD = 'cpc-chat-name'   // pre-namespacing; read once as a fallback
const INSTANCE_LABEL = import.meta.env.DEV ? 'Lab' : 'C2'

const meNode    = ref<string | null>(null)   // server-recognized device, else null
const guestName = ref('')
let started = false

function loadGuestName() {
  let n = localStorage.getItem(GUEST_KEY) || localStorage.getItem(GUEST_KEY_OLD)
  if (!n) n = `${INSTANCE_LABEL} Guest ${Math.floor(1000 + Math.random() * 9000)}`
  localStorage.setItem(GUEST_KEY, n)
  guestName.value = n
}

async function fetchWhoami() {
  try {
    const r = await fetch(`${API_BASE}/whoami`)
    if (r.ok) { const j = await r.json(); meNode.value = j.node ?? null }
  } catch { /* offline — stay a guest */ }
}

export function useIdentity() {
  if (!started) { started = true; loadGuestName(); fetchWhoami() }

  const isGuest  = computed(() => !meNode.value)
  // The value MESSAGES are sent as: a node id when recognized, else the guest string.
  const identity = computed(() => meNode.value ?? guestName.value)

  function setGuestName(v: string) {
    const t = v.trim().slice(0, 24)
    if (t) { guestName.value = t; localStorage.setItem(GUEST_KEY, t) }
  }

  return { meNode, guestName, isGuest, identity, setGuestName }
}
