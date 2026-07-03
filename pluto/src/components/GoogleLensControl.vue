<script setup lang="ts">
// Google (Vision + Translate) source.
//   LEFT  = compact drop strip (top) + Vision output + translations (scrolling)
//   RIGHT = ControlCapture + scan/translate buttons (top), ControlKeyboard full-width (bottom)
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import ControlCapture from './ControlCapture.vue'
import ControlKeyboard from './ControlKeyboard.vue'
import UiClose from './ui/UiClose.vue'
import UiIconButton from './ui/UiIconButton.vue'
import { LANGUAGES } from '../lib/languages'

const props = defineProps<{
  active:     boolean
  mapSource:  string
  target:     string
  mapping:    string
  targetDev?: string
}>()
const emit = defineEmits<{ 'drive-error': [string] }>()

const rumble = ref(false)
let _rumbleTimer = 0
function onRumble() {
  rumble.value = true
  if (_rumbleTimer) clearTimeout(_rumbleTimer)
  _rumbleTimer = window.setTimeout(() => { rumble.value = false }, 400)
}

const API = `http://${window.location.hostname}:7700`
const captureRef     = ref<InstanceType<typeof ControlCapture> | null>(null)
const captureRunning = computed(() => captureRef.value?.capture.running ?? false)

watch(captureRunning, (running) => { if (running) clearImage() })

const canScan = computed(() => captureRunning.value || !!imageUrl.value)

// subtitle mode: user-toggled — full-width output, bigger font, right panel hidden
const subtitleMode = ref(false)

// ── Vision usage counter (scans, 900 / 1000 safety cap) ──────────────────
const USAGE_KEY   = 'cpc.lens.usage'
const MONTHLY_CAP = 900

function _yyyymm() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}
function _loadCounter(key: string): { month: string; count: number } {
  try {
    const raw = localStorage.getItem(key)
    if (raw) { const p = JSON.parse(raw); if (p.month === _yyyymm()) return p }
  } catch {}
  return { month: _yyyymm(), count: 0 }
}
function _increment(key: string, current: { month: string; count: number }, by = 1) {
  const month = _yyyymm()
  const count = (current.month === month ? current.count : 0) + by
  const next = { month, count }
  try { localStorage.setItem(key, JSON.stringify(next)) } catch {}
  return next
}

const usage     = ref(_loadCounter(USAGE_KEY))
const overLimit = computed(() => usage.value.count >= MONTHLY_CAP)

// ── Translate usage counter (chars, 450k / 500k safety cap) ──────────────
const TRANSLATE_KEY = 'cpc.lens.translate'
const TRANSLATE_CAP = 450_000
const translateUsage    = ref(_loadCounter(TRANSLATE_KEY))
const translateOverLimit = computed(() => translateUsage.value.count >= TRANSLATE_CAP)

// ── Language picker ───────────────────────────────────────────────────────
const LANG_KEY = 'cpc.lens.lang'
const translateLang = ref(localStorage.getItem(LANG_KEY) ?? 'en')
watch(translateLang, (v) => { try { localStorage.setItem(LANG_KEY, v) } catch {} })

async function _fetchDefaultLang() {
  if (localStorage.getItem(LANG_KEY)) return   // user has an explicit preference
  try {
    const r = await fetch(`${API}/control/google/config`)
    if (r.ok) { const j = await r.json(); if (j.lang) translateLang.value = j.lang }
  } catch {}
}

// ── scan + translate results ──────────────────────────────────────────────
interface ScanResult { lines: string[]; error?: string; meta: string; ts: number; translation?: string; translating?: boolean }
const results    = ref<ScanResult[]>([])
const scanning   = ref(false)
const translating = ref(false)
const outputEl   = ref<HTMLElement | null>(null)

function _scrollToBottom() {
  nextTick(() => { if (outputEl.value) outputEl.value.scrollTop = outputEl.value.scrollHeight })
}

function _pushResult(j: Record<string, unknown>) {
  const lines = (j.text_lines as string[] | undefined) ?? []
  if (j.from_cache) {
    if (results.value.length) {
      // just update the meta tag on the existing last result
      results.value[results.value.length - 1].meta = 'cached'
      return
    }
    // results cleared or first load — show the cached text so translate works
  } else {
    usage.value = _increment(USAGE_KEY, usage.value)
  }
  results.value.push({
    lines: lines.length ? lines : ['(no text detected)'],
    meta: j.from_cache ? 'cached' : `${j.changed_lines ?? 0} changed`,
    ts: Date.now(),
  })
  _scrollToBottom()
}

function _pushError(msg: string) {
  results.value.push({ lines: [], error: msg, meta: '', ts: Date.now() })
  _scrollToBottom()
}

async function scan() {
  if (scanning.value || overLimit.value) return
  const req = imageB64.value
    ? fetch(`${API}/control/google/lens`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image: imageB64.value }),
      })
    : fetch(`${API}/control/google/lens`)
  scanning.value = true
  try {
    const r = await req
    const j = await r.json().catch(() => null)
    if (!r.ok || j?.error) _pushError(j?.error ?? `HTTP ${r.status}`)
    else _pushResult(j)
    emit('drive-error', '')
  } catch { emit('drive-error', 'API unreachable') }
  finally { scanning.value = false }
}

// translate the most recent result that has real text
const lastTranslatable = computed(() => {
  for (let i = results.value.length - 1; i >= 0; i--) {
    const r = results.value[i]
    if (!r.error && r.lines.length && r.lines[0] !== '(no text detected)') return i
  }
  return -1
})
const canTranslate = computed(() =>
  lastTranslatable.value >= 0 && !translating.value && !translateOverLimit.value)

async function translate() {
  const idx = lastTranslatable.value
  if (idx < 0 || translating.value || translateOverLimit.value) return
  const text = results.value[idx].lines.join('\n')
  const charCount = text.length
  if (translateUsage.value.count + charCount > TRANSLATE_CAP) {
    _pushError('Translate cap reached (' + TRANSLATE_CAP.toLocaleString() + ' chars / month)')
    return
  }
  translating.value = true
  results.value[idx].translating = true
  try {
    const r = await fetch(`${API}/control/google/translate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, target: translateLang.value }),
    })
    const j = await r.json().catch(() => null)
    if (!r.ok || j?.error) {
      results.value[idx].translation = '(error: ' + (j?.error ?? `HTTP ${r.status}`) + ')'
    } else {
      results.value[idx].translation = j.translated
      translateUsage.value = _increment(TRANSLATE_KEY, translateUsage.value, charCount)
    }
    emit('drive-error', '')
  } catch { emit('drive-error', 'API unreachable') }
  finally { translating.value = false; results.value[idx].translating = false }
  _scrollToBottom()
}

function clearResults() { results.value = [] }

// ── image drop / file-pick test path ─────────────────────────────────────
const fileInput  = ref<HTMLInputElement | null>(null)
const dropActive = ref(false)
const imageUrl   = ref<string | null>(null)
const imageB64   = ref<string | null>(null)

function clearImage() {
  if (imageUrl.value) URL.revokeObjectURL(imageUrl.value)
  imageUrl.value = null; imageB64.value = null
}

function onDragOver(e: DragEvent) { e.preventDefault(); dropActive.value = true }
function onDragLeave()             { dropActive.value = false }

async function handleFile(file: File) {
  if (!file.type.startsWith('image/') || captureRunning.value) return
  clearImage()
  imageUrl.value = URL.createObjectURL(file)
  dropActive.value = false
  const reader = new FileReader()
  reader.onload = async () => {
    const b64 = (reader.result as string).split(',')[1]
    imageB64.value = b64
    await scan()
  }
  reader.readAsDataURL(file)
}

function onDrop(e: DragEvent) {
  e.preventDefault(); dropActive.value = false
  const file = e.dataTransfer?.files[0]; if (file) handleFile(file)
}
function onFileChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]; if (file) handleFile(file)
  ;(e.target as HTMLInputElement).value = ''
}

// ── auto-scan every 3 s when capture is running ──────────────────────────
let poll = 0
function startPoll() { if (!poll) poll = window.setInterval(() => { if (captureRunning.value) scan() }, 3000) }
function stopPoll()  { if (poll) { clearInterval(poll); poll = 0 } }

// ── hardware-triggered results (Pi L+R → /control/google/translate-last) ───
let _hwLastTs = 0
let hwPoll = 0

async function _pollHardware() {
  try {
    const r = await fetch(`${API}/control/google/latest`)
    if (!r.ok) return
    const j = await r.json()
    const tr = j?.translation
    if (!tr || tr.ts <= _hwLastTs) return
    _hwLastTs = tr.ts
    const lines: string[] = j?.scan?.lines ?? []
    // attach to last result if it has no translation yet; otherwise push a new entry
    const last = results.value[results.value.length - 1]
    if (last && !last.translation && !last.error) {
      last.translation = tr.text
    } else {
      results.value.push({
        lines: lines.length ? lines : ['(no text detected)'],
        meta: 'hardware',
        ts: Date.now(),
        translation: tr.text,
      })
    }
    _scrollToBottom()
  } catch {}
}

function startHwPoll() { if (!hwPoll) hwPoll = window.setInterval(_pollHardware, 3000) }
function stopHwPoll()  { if (hwPoll) { clearInterval(hwPoll); hwPoll = 0 } }

onMounted(() => { if (props.active) startPoll(); startHwPoll(); _fetchDefaultLang() })
onBeforeUnmount(() => { stopPoll(); stopHwPoll() })
watch(() => props.active, (on) => { if (on) startPoll(); else stopPoll() })

function fmtTime(ts: number) {
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`
}
</script>

<template>
  <div class="gl" :class="{ 'gl--rumble': rumble }">
    <div class="gl-body" :class="{ 'gl-body--subtitle': subtitleMode }">

      <!-- LEFT: compact drop strip + Vision output -->
      <div class="gl-left">

        <!-- drop strip -->
        <div class="gl-strip"
             :class="{ 'gl-strip--over': dropActive, 'gl-strip--locked': captureRunning, 'gl-strip--loaded': !!imageUrl }"
             @dragover="onDragOver" @dragleave="onDragLeave" @drop="onDrop"
             @click="!captureRunning && !imageUrl && fileInput?.click()">
          <template v-if="imageUrl">
            <img :src="imageUrl" class="gl-strip-thumb" alt="test" />
            <span class="gl-strip-name">Test image</span>
            <UiClose class="gl-strip-x" @click.stop="clearImage" title="Clear" />
          </template>
          <template v-else-if="captureRunning">
            <span class="gl-strip-hint">Stop capture to test an image</span>
          </template>
          <template v-else>
            <svg viewBox="0 0 16 16" width="14" height="14" fill="none" class="gl-strip-icon">
              <rect x="1" y="3" width="14" height="10" rx="1.5" stroke="currentColor" stroke-width="1.4"/>
              <circle cx="5.5" cy="7" r="1.5" stroke="currentColor" stroke-width="1.2"/>
              <path d="M1 11l4-3 3 2.5 2.5-2 4.5 4.5" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
              <path d="M8 2.5V.5M8 .5L6.5 2M8 .5L9.5 2" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
            </svg>
            <span class="gl-strip-hint">Drop an image to test, or click to browse</span>
          </template>
          <input ref="fileInput" type="file" accept="image/*" class="gl-drop-input" @change="onFileChange" />
        </div>

        <!-- output header -->
        <div class="gl-output-head">
          <div class="gl-output-head-row">
            <span class="gl-output-title">Vision Output</span>
            <UiIconButton variant="bordered" :active="subtitleMode"
                          @click="subtitleMode = !subtitleMode"
                          :title="subtitleMode ? 'Exit subtitle mode' : 'Subtitle mode: full-width, larger text'">
              <svg viewBox="0 0 16 16" width="14" height="14" fill="none">
                <rect x="1" y="4" width="14" height="8" rx="1.5" stroke="currentColor" stroke-width="1.4"/>
                <path d="M4 8h4M4 10.5h2.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
              </svg>
            </UiIconButton>
            <UiClose v-if="results.length" @click="clearResults" title="Clear results" />
          </div>
          <div v-if="usage.count || translateUsage.count" class="gl-quota-block mono">
            <span class="gl-quota-row"><span class="gl-quota-label">Vision</span>{{ usage.count }} / {{ MONTHLY_CAP }} scans</span>
            <span v-if="translateUsage.count" class="gl-quota-row"><span class="gl-quota-label">Translate</span>{{ translateUsage.count.toLocaleString() }} / {{ TRANSLATE_CAP.toLocaleString() }} chars</span>
          </div>
        </div>

        <!-- scrolling results -->
        <div ref="outputEl" class="gl-output">
          <p v-if="!results.length" class="gl-output-empty">Start capture and scan, or drop a test image.</p>
          <div v-for="(r, i) in results" :key="i" class="gl-result">
            <div class="gl-result-meta mono">
              <span>{{ fmtTime(r.ts) }}</span>
              <span v-if="r.meta" class="gl-result-info">{{ r.meta }}</span>
            </div>
            <p v-if="r.error" class="gl-result-error">{{ r.error }}</p>
            <template v-else>
              <p v-for="(line, li) in r.lines" :key="li" class="gl-result-line">{{ line }}</p>
              <p v-if="r.translating" class="gl-result-xlat gl-result-xlat--pending">Translating…</p>
              <p v-else-if="r.translation" class="gl-result-xlat">{{ r.translation }}</p>
            </template>
          </div>
        </div>
      </div>

      <!-- RIGHT: capture (top) + keyboard (bottom, full width) -->
      <div class="gl-right">

        <ControlCapture ref="captureRef"
          :active="active" :show-game-actions="false"
          :map-source="mapSource" :target="target" :mapping="mapping" :target-dev="targetDev"
          @drive-error="emit('drive-error', $event)"
          @rumble="onRumble">
          <template #extra-actions>
            <div class="cap-divider" />
            <button class="cap-btn cap-btn--scan" :disabled="!canScan || scanning || overLimit" @click="scan"
                    :title="overLimit ? 'Monthly cap reached' : !canScan ? 'Start capture or drop an image first' : 'Scan'">
              <svg :class="{ 'gl-scan-spin': scanning }" viewBox="0 0 22 16" width="22" height="16" fill="none">
                <path d="M1 8 C5 2 17 2 21 8 C17 14 5 14 1 8 Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
                <circle cx="11" cy="8" r="3.8" fill="currentColor"/>
                <circle cx="11" cy="8" r="1.6" fill="var(--surface-3)" class="gl-scan-pupil"/>
              </svg>
            </button>
            <select v-model="translateLang" class="cap-btn cap-lang"
                    :title="`Translate to: ${LANGUAGES.find(l => l.code === translateLang)?.label}`">
              <option v-for="l in LANGUAGES" :key="l.code" :value="l.code">{{ l.code }}</option>
            </select>
            <button class="cap-btn cap-btn--xlat" :disabled="!canTranslate" @click="translate"
                    :title="translateOverLimit ? 'Monthly translate cap reached' : !canTranslate ? 'No text to translate' : `Translate to ${LANGUAGES.find(l => l.code === translateLang)?.label}`">
              <svg :class="{ 'gl-scan-spin': translating }" viewBox="0 0 26 18" width="26" height="18">
                <text x="1" y="14" font-size="14" font-weight="800" fill="currentColor" font-family="sans-serif">A</text>
                <text x="13" y="15" font-size="12" font-weight="700" fill="currentColor" font-family="sans-serif">文</text>
              </svg>
            </button>
          </template>
        </ControlCapture>

        <div class="gl-controller">
          <ControlKeyboard :active="active"
            map-source="google"
            :target="target" :mapping="mapping" :target-dev="targetDev"
            @drive-error="emit('drive-error', $event)" />
        </div>

      </div>

    </div>
  </div>
</template>

<style scoped>
.gl {
  display: flex; flex-direction: column; height: 100%; min-height: 0;
  overflow: hidden; background: var(--surface-2); position: relative;
}
.gl--rumble::after {
  content: ''; position: absolute; inset: 0; background: rgba(220,40,40,0.40);
  pointer-events: none; z-index: 20; animation: gl-rumble 0.4s ease-out forwards;
}
@keyframes gl-rumble { 0% { opacity: 1; } 100% { opacity: 0; } }

.gl-body  { display: flex; flex: 1 1 0; min-height: 0; overflow: hidden; }

/* ── LEFT: drop strip + output ────────────────────────────────────────── */
.gl-left {
  flex: 0 0 50%; min-width: 0; min-height: 0;
  display: flex; flex-direction: column;
  background: var(--surface); border-right: 1px solid var(--line);
}

/* compact horizontal strip at top of left panel */
.gl-strip {
  flex: 0 0 auto; display: flex; align-items: center; gap: var(--sp-2);
  padding: 6px var(--sp-3); border-bottom: 1px solid var(--line);
  min-height: 42px; cursor: pointer;
  background: var(--surface-2); transition: background 0.12s;
}
.gl-strip:not(.gl-strip--locked):not(.gl-strip--loaded):hover { background: var(--accent-soft); }
.gl-strip--over  { background: var(--accent-soft) !important; }
.gl-strip--locked { cursor: default; opacity: 0.5; }
.gl-strip--loaded { cursor: default; }
.gl-strip-icon   { flex-shrink: 0; color: var(--text-faint); }
.gl-strip-hint   { font-size: 11px; color: var(--text-faint); }
.gl-strip--loaded { min-height: 80px; }
.gl-strip-thumb  { width: 110px; height: 66px; object-fit: cover; border-radius: var(--r-sm); flex-shrink: 0; }
.gl-strip-name   { font-size: 11px; color: var(--text-muted); flex: 1 1 auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* layout only — the close look comes from UiClose */
.gl-strip-x { flex-shrink: 0; }

.gl-output-head {
  flex: 0 0 auto; display: flex; flex-direction: column; gap: var(--sp-1);
  padding: var(--sp-2) var(--sp-3); border-bottom: 1px solid var(--line);
}
.gl-output-head-row {
  display: flex; align-items: center; gap: var(--sp-2);
}
.gl-output-title {
  font-size: 11px; font-weight: 700; color: var(--text); text-transform: uppercase;
  letter-spacing: 0.05em; flex: 1 1 auto;
}
.gl-quota-block { display: flex; flex-direction: column; gap: 1px; }
.gl-quota-row   { font-size: 11px; color: var(--text-faint); display: flex; gap: var(--sp-3); }
.gl-quota-label { font-weight: 600; color: var(--text-muted); min-width: 62px; }

/* the Vision-output icon buttons are now UiIconButton (toggle) + UiClose */

.gl-output {
  flex: 1 1 0; overflow-y: auto; padding: var(--sp-3) var(--sp-4);
  display: flex; flex-direction: column; gap: var(--sp-4);
}
.gl-output-empty { font-size: 13px; color: var(--text-faint); text-align: center; margin: auto; }

.gl-result       { display: flex; flex-direction: column; gap: 2px; }
.gl-result-meta  { display: flex; gap: var(--sp-2); font-size: 10px; color: var(--text-faint); margin-bottom: 2px; }
.gl-result-info  { color: var(--text-muted); }
.gl-result-line  { font-size: 13px; color: var(--text); line-height: 1.5; word-break: break-word; overflow-wrap: break-word; margin: 0; }
.gl-result-error { font-size: 12px; color: var(--bad); margin: 0; }
.gl-result-xlat  {
  font-size: 13px; color: var(--accent); line-height: 1.5; margin: 4px 0 0;
  padding: 4px 8px; background: var(--accent-soft); border-radius: var(--r-sm);
  word-break: break-word; overflow-wrap: break-word;
}
.gl-result-xlat--pending { color: var(--text-faint); background: none; padding: 0; }

/* ── RIGHT: capture + keyboard ────────────────────────────────────────── */
.gl-right {
  flex: 0 0 50%; min-width: 0; min-height: 0;
  display: flex; flex-direction: column;
}
.gl-controller {
  flex: 1 1 0; min-height: 0; min-width: 0;
  background: var(--surface); border-top: 1px solid var(--line); overflow: hidden;
}

/* ── slot controls (must replicate cap-btn base — scoped styles don't cross slots) */
:deep(.cap-btn--scan),
:deep(.cap-btn--xlat) {
  flex: 1 1 0; display: flex; align-items: center; justify-content: center;
  height: 38px; line-height: 1;
  border: 1px solid var(--accent); border-radius: var(--r-sm);
  cursor: pointer; transition: background 0.1s, opacity 0.1s;
  background: var(--surface-3); color: var(--accent);
}
:deep(.cap-btn--scan:disabled),
:deep(.cap-btn--xlat:disabled)              { opacity: 0.35; cursor: default; }
:deep(.cap-btn--scan:active:not(:disabled)),
:deep(.cap-btn--xlat:active:not(:disabled)) { transform: scale(0.94); }
:deep(.cap-btn--scan:hover:not(:disabled)),
:deep(.cap-btn--xlat:hover:not(:disabled))  { background: var(--accent); color: var(--accent-ink); }
:deep(.cap-btn--scan svg),
:deep(.cap-btn--xlat svg)                   { display: block; }
:deep(.cap-lang) {
  flex: 0 0 auto; height: 38px; padding: 0 6px;
  font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);
  background: var(--surface-3); border: 1px solid var(--line-strong);
  border-radius: var(--r-sm); cursor: pointer;
}

@keyframes gl-scan-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
.gl-scan-spin { animation: gl-scan-pulse 0.9s ease-in-out infinite; }
.gl-scan-spin .gl-scan-pupil { opacity: 0; }

.gl-drop-input { display: none; }

/* ── subtitle mode: full-width output, right panel hidden ─────────────── */
.gl-body--subtitle .gl-right  { display: none; }
.gl-body--subtitle .gl-left   { flex: 1 1 100%; border-right: none; }
.gl-body--subtitle .gl-strip  { display: none; }

.gl-body--subtitle .gl-output-title { font-size: 10px; }
.gl-body--subtitle .gl-result-line  { font-size: 17px; line-height: 1.6; }
.gl-body--subtitle .gl-result-xlat  { font-size: 17px; line-height: 1.6; padding: 6px 12px; margin-top: 6px; }
.gl-body--subtitle .gl-output-empty { font-size: 15px; }
</style>
