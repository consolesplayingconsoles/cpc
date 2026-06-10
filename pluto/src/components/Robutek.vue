<script setup lang="ts">
import { ref, computed, watch } from 'vue'

interface Point { x: number; y: number }

interface Device {
  name: string | null
  model: string | null
  firmware: string | null
  activity: string
  status_label: string
  status_int: number | null
  battery: number | null
  online: boolean
}

interface Session {
  session_id: string
  date: string
  start_ts: number | null
  cleaning_min: number | null
  area_m2: number | null
  completed: boolean
  file_name: string
  route: Point[]
  origin_mm: [number, number] | null
  charger_mm: [number, number] | null
  grid_size_mm: number | null
  map_id: number | null
}

interface DreameData {
  authenticated?: boolean
  device: Device | null
  history: Session[]
  updated: string | null
  error?: string | null
}

const props = defineProps<{ name: string; active: boolean }>()
const API = `http://${window.location.hostname}:7700`

const data        = ref<DreameData | null>(null)
const loading     = ref(false)
const fetchedAt   = ref('')
const selIdx      = ref(0)
const showExpired = ref(false)

const svgScale = ref(1)
const svgCx    = ref(0)
const svgCy    = ref(0)

const dev     = computed(() => data.value?.device ?? null)
const history = computed(() => data.value?.history ?? [])

// ── Route expiry (Alibaba OSS retains .bin files ~21 days) ────────
const OSS_DAYS = 21

function expiryDate(dateStr: string): Date | null {
  const m = dateStr.match(/(\d{4})-(\d{2})-(\d{2})/)
  if (!m) return null
  const d = new Date(+m[1], +m[2] - 1, +m[3])
  d.setDate(d.getDate() + OSS_DAYS)
  return d
}

function fmtShortDate(d: Date): string {
  const mo = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  return `${mo[d.getMonth()]} ${d.getDate()}`
}

function isExpiredSession(s: Session): boolean {
  if (s.route.length > 0) return false
  if (!s.file_name)       return false
  const exp = expiryDate(s.date)
  return exp ? exp.getTime() < Date.now() : false
}

function routeCell(s: Session): { text: string; cls: string } {
  if (s.route.length > 0) {
    const exp = expiryDate(s.date)
    return { text: exp ? fmtShortDate(exp) : 'saved', cls: 'rc-saved' }
  }
  if (!s.file_name) return { text: '–', cls: 'rc-none' }
  const exp = expiryDate(s.date)
  if (!exp) return { text: '?', cls: 'rc-none' }
  if (exp.getTime() < Date.now()) return { text: 'expired', cls: 'rc-exp' }
  return { text: fmtShortDate(exp), cls: 'rc-pending' }
}

// ── Filtered history ──────────────────────────────────────────────
const visibleHistory = computed(() =>
  showExpired.value ? history.value : history.value.filter(s => !isExpiredSession(s))
)
const expiredCount = computed(() => history.value.filter(isExpiredSession).length)

watch(visibleHistory, () => { selIdx.value = 0 }, { flush: 'sync' })

const sel = computed<Session | null>(() => visibleHistory.value[selIdx.value] ?? null)
watch(sel, () => { svgScale.value = 1 })

// ── Status labels ─────────────────────────────────────────────────
const STATUS_HUMAN: Record<string, string> = {
  SWEEPING:             'Sweeping',
  IDLE:                 'Idle',
  PAUSED:               'Paused',
  ERROR:                'Error',
  RETURNING:            'Returning',
  CHARGING:             'Charging',
  MOPPING:              'Mopping',
  DRYING:               'Drying',
  WASHING:              'Washing',
  RETURNING_WASHING:    'Returning to wash',
  BUILDING_MAP:         'Building map',
  SWEEPING_AND_MOPPING: 'Sweep + mop',
  CHARGING_COMPLETED:   'Charge complete',
  UPGRADING:            'Updating firmware',
  UNKNOWN:              'Unknown',
}
function humanStatus(label: string): string {
  return STATUS_HUMAN[label] ??
    label.replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase())
}

const actClass = computed(() => {
  switch (dev.value?.activity) {
    case 'cleaning':  return 'act-clean'
    case 'returning': return 'act-return'
    case 'error':     return 'act-error'
    default:          return 'act-idle'
  }
})

// ── Battery ───────────────────────────────────────────────────────
const BLOCKS = 24
const batData = computed(() => {
  const pct = dev.value?.battery ?? null
  if (pct === null) return null
  const filled = Math.round((pct / 100) * BLOCKS)
  const color  = pct > 50 ? '#22a855' : pct > 20 ? '#e6a817' : '#cc1111'
  return { pct, filled, empty: BLOCKS - filled, color }
})

// ── SVG route ─────────────────────────────────────────────────────
const baseBox = computed(() => {
  const s = sel.value
  if (!s?.route?.length) return null
  const pts = s.route
  const xs  = pts.map(p => p.x), ys = pts.map(p => p.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const pad  = Math.max(maxX - minX, maxY - minY) * 0.07
  const cx = s.charger_mm?.[0] ?? null, cy = s.charger_mm?.[1] ?? null
  const bx0 = (cx !== null ? Math.min(minX, cx) : minX) - pad
  const by0 = (cy !== null ? Math.min(minY, cy) : minY) - pad
  const bx1 = (cx !== null ? Math.max(maxX, cx) : maxX) + pad
  const by1 = (cy !== null ? Math.max(maxY, cy) : maxY) + pad
  return {
    fullVB:     [bx0, by0, bx1 - bx0, by1 - by0] as [number,number,number,number],
    polyPoints: pts.map(p => `${p.x},${p.y}`).join(' '),
    cx, cy,
    startX: pts[0].x, startY: pts[0].y,
  }
})

const viewBox = computed(() => {
  if (!baseBox.value) return '0 0 1 1'
  const [bx, by, bw, bh] = baseBox.value.fullVB
  if (svgScale.value <= 1) return `${bx} ${by} ${bw} ${bh}`
  const w = bw / svgScale.value, h = bh / svgScale.value
  return `${svgCx.value - w / 2} ${svgCy.value - h / 2} ${w} ${h}`
})

function onWheel(e: WheelEvent) {
  if (!baseBox.value) return
  e.preventDefault()
  const svg = e.currentTarget as SVGSVGElement
  const pt  = svg.createSVGPoint()
  pt.x = e.clientX; pt.y = e.clientY
  const svgPt    = pt.matrixTransform(svg.getScreenCTM()!.inverse())
  const factor   = e.deltaY < 0 ? 1.18 : 1 / 1.18
  const newScale = Math.max(1, Math.min(20, svgScale.value * factor))
  if (newScale === svgScale.value) return
  const [bx, by, bw, bh] = baseBox.value.fullVB
  const curCx = svgScale.value <= 1 ? bx + bw / 2 : svgCx.value
  const curCy = svgScale.value <= 1 ? by + bh / 2 : svgCy.value
  svgScale.value = newScale
  svgCx.value = svgPt.x + (curCx - svgPt.x) / factor
  svgCy.value = svgPt.y + (curCy - svgPt.y) / factor
}
function resetZoom() { svgScale.value = 1 }

// ── Formatters ────────────────────────────────────────────────────
function fmt(min: number | null): string {
  if (min === null) return '–'
  return min < 60 ? `${min} min` : `${Math.floor(min / 60)}h ${(min % 60).toString().padStart(2, '0')}m`
}
function fmtArea(m2: number | null): string {
  return m2 !== null ? `${m2} m²` : '–'
}
function fmtDate(d: string): string {
  const m = d.match(/(\d{4})-(\d{2})-(\d{2})\s+(\d{2}:\d{2})/)
  if (!m) return d
  const mo = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  return `${mo[+m[2]-1]} ${+m[3]}  ${m[4]}`
}

async function load() {
  loading.value = true
  try {
    const r = await fetch(`${API}/dreame`)
    if (!r.ok) {
      data.value = { device: null, history: [], updated: null, error: `HTTP ${r.status}` }
      return
    }
    data.value = await r.json()
    fetchedAt.value = new Date().toLocaleTimeString([], {
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    })
  } catch {
    data.value = { device: null, history: [], updated: null, error: 'could not reach Pluto API' }
  } finally {
    loading.value = false
  }
}

// ── Login (shown when the API holds no live session) ──────────────
const region     = ref('us')
const email      = ref('')
const password   = ref('')
const submitting = ref(false)
const loginError = ref('')

const needsLogin = computed(() => data.value != null && data.value.authenticated === false)

async function login() {
  if (submitting.value) return
  submitting.value = true
  loginError.value = ''
  try {
    const r = await fetch(`${API}/dreame/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ region: region.value, username: email.value, password: password.value }),
    })
    const body = await r.json().catch(() => ({}))
    if (!r.ok || !body.authenticated) {
      loginError.value = body.error || `sign-in failed (HTTP ${r.status})`
      return
    }
    password.value = ''      // don't retain the password any longer than needed
    await load()             // now authenticated -> shows device + history
  } catch {
    loginError.value = 'could not reach the Pluto API'
  } finally {
    submitting.value = false
  }
}

watch(() => props.active, on => { if (on) load() }, { immediate: true })
</script>

<template>
  <div class="rb">

    <!-- ── hold everything behind a quiet loader until the first response,
         so we never flash the content skeleton before resolving to login ── -->
    <div v-if="!data" class="rb-init"><span class="rb-init-spinner" /></div>

    <!-- ── login gate (API holds no live session) ── -->
    <form v-else-if="needsLogin" class="rb-login" @submit.prevent="login" autocomplete="on">
      <div class="rb-login-card">
        <div class="rb-login-title">Connect to DreameHome</div>

        <label class="rb-login-field">
          <span>Region</span>
          <select v-model="region" autocomplete="off" :disabled="submitting">
            <option value="us">United States</option>
            <option value="eu">Europe</option>
            <option value="cn">China</option>
            <option value="ru">Russia</option>
            <option value="sg">Asia / Pacific</option>
          </select>
        </label>

        <label class="rb-login-field">
          <span>Email</span>
          <input v-model="email" name="username" type="email" autocomplete="username"
                 placeholder="you@example.com" :disabled="submitting" required />
        </label>

        <label class="rb-login-field">
          <span>Password</span>
          <input v-model="password" name="password" type="password" autocomplete="current-password"
                 placeholder="&bull;&bull;&bull;&bull;&bull;&bull;&bull;&bull;" :disabled="submitting" required />
        </label>

        <button class="rb-login-btn" type="submit" :disabled="submitting || !email || !password">
          {{ submitting ? 'Signing in…' : 'Sign in' }}
        </button>

        <p v-if="loginError" class="rb-login-err">{{ loginError }}</p>
      </div>
    </form>

    <template v-else>
    <!-- ── KPI floating cards ── -->
    <div class="rb-kpi">

      <!-- skeleton cards while loading cold -->
      <template v-if="loading && !data">
        <div class="rb-card rb-sk-card" v-for="n in 3" :key="n" :style="{ width: n===2 ? '210px' : n===3 ? '220px' : '160px' }">
          <div class="sk-line sk-lbl" />
          <div class="sk-line sk-val" />
          <div class="sk-line sk-sub" />
        </div>
      </template>

      <template v-else-if="!dev">
        <span class="rb-kpi-err">{{ data?.error || 'no device data' }}</span>
      </template>

      <template v-else>

        <!-- activity -->
        <div class="rb-card" :class="actClass">
          <div class="rb-card-lbl">ACTIVITY</div>
          <div class="rb-card-val">{{ humanStatus(dev.status_label) }}</div>
          <div class="rb-card-sub">
            <span class="rb-dot" :class="dev.online ? 'dot-on' : 'dot-off'" />
            cloud: {{ dev.online ? 'connected' : 'idle' }}
          </div>
        </div>

        <!-- battery -->
        <div class="rb-card rb-card-bat">
          <div class="rb-card-lbl">BATTERY</div>
          <div v-if="batData" class="rb-bat-row">
            <span v-for="i in batData.filled" :key="'f'+i"
              class="rb-block" :style="{ background: batData.color }" />
            <span v-for="i in batData.empty"  :key="'e'+i"
              class="rb-block rb-block-empty" />
            <span class="rb-bat-pct" :style="{ color: batData.color }">{{ batData.pct }}%</span>
          </div>
          <div v-else class="rb-card-sub">–</div>
        </div>

        <!-- device -->
        <div class="rb-card rb-card-dev">
          <div class="rb-card-lbl">DEVICE</div>
          <div class="rb-card-val">{{ dev.name ?? dev.model ?? '–' }}</div>
          <div class="rb-card-sub">{{ dev.model ?? '' }}&nbsp;&nbsp;firmware {{ dev.firmware ?? '–' }}</div>
        </div>

        <div v-if="data?.error" class="rb-kpi-warn">{{ data.error }}</div>

      </template>

      <span class="rb-spacer" />

      <div class="rb-controls">
       <span v-if="fetchedAt && !loading" class="rb-fetched">Last refresh at {{ fetchedAt }}</span>
        <button class="rb-btn" :disabled="loading" @click="load">
          {{ loading && data ? 'refreshing...' : loading ? 'loading...' : 'refresh' }}
        </button>
      </div>
    </div>

    <!-- ── skeleton body (cold load) ── -->
    <div v-if="loading && !data" class="rb-body">
      <div class="rb-hist">
        <div class="rb-hist-head"><div class="sk-line sk-lbl" style="width:120px"/></div>
        <div class="rb-tbl-head sk-tbl-head" />
        <!-- skeleton rows reuse .rb-row so height is identical to real rows -->
        <div v-for="n in 12" :key="n" class="rb-row sk-data-row" :style="{ opacity: 1 - n * 0.07 }">
          <span class="sk-bar" />
          <span class="sk-bar sk-bar-r" style="width:55%" />
          <span class="sk-bar sk-bar-r" style="width:60%" />
          <span class="sk-bar sk-bar-c" style="width:50%" />
          <span class="sk-bar sk-bar-r" style="width:45%" />
        </div>
      </div>
      <div class="rb-canvas sk-canvas" />
    </div>

    <!-- ── body (data available) ── -->
    <div class="rb-body" v-else-if="data">

      <!-- history table -->
      <div class="rb-hist">

        <div class="rb-hist-head">
          <span class="rb-hist-label">CLEANING HISTORY</span>
          <label class="rb-toggle">
            <input type="checkbox" v-model="showExpired" class="rb-chk" />
            <span>show expired</span>
            <span v-if="expiredCount" class="rb-exp-badge">{{ expiredCount }}</span>
          </label>
        </div>

        <div class="rb-tbl-head">
          <span>DATE / TIME</span>
          <span class="th-r">DURATION</span>
          <span class="th-r">AREA</span>
          <span class="th-c">STATUS</span>
          <span class="th-r">DATA EXPIRES</span>
        </div>

        <div
          v-for="(s, i) in visibleHistory"
          :key="s.session_id"
          class="rb-row"
          :class="{ selected: i === selIdx, 'has-rt': s.route.length > 0 }"
          @click="selIdx = i"
        >
          <span class="rb-row-date">{{ fmtDate(s.date) }}</span>
          <span class="rb-row-dur">{{ fmt(s.cleaning_min) }}</span>
          <span class="rb-row-area">{{ fmtArea(s.area_m2) }}</span>
          <span class="rb-row-ok">{{ s.completed ? 'completed' : 'partial' }}</span>
          <span
            class="rb-row-rt"
            :class="routeCell(s).cls"
            :title="s.route.length ? `${s.route.length} pts cached` : s.file_name ? 'not captured before expiry' : 'no route recorded'"
          >{{ routeCell(s).text }}</span>
        </div>

        <div v-if="!visibleHistory.length" class="rb-empty">
          {{ expiredCount && !showExpired
            ? `${expiredCount} expired session${expiredCount > 1 ? 's' : ''} hidden`
            : 'no sessions cached' }}
        </div>
      </div>

      <!-- route canvas -->
      <div class="rb-canvas">

        <template v-if="!sel">
          <div class="rb-canvas-empty">select a session to view its route</div>
        </template>

        <template v-else-if="!baseBox">
          <div class="rb-canvas-empty">
            <div class="rb-canvas-empty-title">{{ fmtDate(sel.date) }}</div>
            <div class="rb-canvas-empty-note">
              {{ sel.file_name ? 'Route data expired before it was captured' : 'No route recorded for this session' }}
            </div>
          </div>
        </template>

        <template v-else>
          <svg
            class="rb-svg"
            :viewBox="viewBox"
            preserveAspectRatio="xMidYMid meet"
            xmlns="http://www.w3.org/2000/svg"
            @wheel="onWheel"
            @dblclick="resetZoom"
          >
            <polyline
              :points="baseBox.polyPoints"
              fill="none"
              stroke="#1a1a1a"
              stroke-width="1.5"
              vector-effect="non-scaling-stroke"
              stroke-linejoin="round"
              stroke-linecap="round"
              opacity="0.75"
            />
            <circle
              :cx="baseBox.startX" :cy="baseBox.startY"
              r="0"
              stroke="#1a1a1a" stroke-width="7"
              vector-effect="non-scaling-stroke"
              fill="none" opacity="0.3"
            />
            <g v-if="baseBox.cx !== null && baseBox.cy !== null">
              <circle
                :cx="baseBox.cx" :cy="baseBox.cy ?? 0"
                r="0"
                stroke="var(--color-primary)" stroke-width="14"
                vector-effect="non-scaling-stroke" fill="none"
              />
              <line
                :x1="baseBox.cx - 1" :y1="baseBox.cy ?? 0"
                :x2="baseBox.cx + 1" :y2="baseBox.cy ?? 0"
                stroke="var(--color-primary)" stroke-width="6"
                vector-effect="non-scaling-stroke"
              />
              <line
                :x1="baseBox.cx" :y1="(baseBox.cy ?? 0) - 1"
                :x2="baseBox.cx" :y2="(baseBox.cy ?? 0) + 1"
                stroke="var(--color-primary)" stroke-width="6"
                vector-effect="non-scaling-stroke"
              />
            </g>
          </svg>

          <div class="rb-route-info">
            <span class="rb-route-date">{{ fmtDate(sel.date) }}</span>
            <span class="rb-route-meta">
              {{ fmt(sel.cleaning_min) }}&ensp;{{ fmtArea(sel.area_m2) }}&ensp;{{ sel.completed ? 'completed' : 'partial' }}&ensp;{{ sel.route.length.toLocaleString() }} pts
            </span>
          </div>

          <div class="rb-zoom-overlay">
            <template v-if="svgScale > 1">
              <span class="rb-zoom-scale">{{ Math.round(svgScale) }}&times;</span>
              <button class="rb-zoom-reset" @click="resetZoom">reset zoom</button>
            </template>
            <span v-else class="rb-zoom-hint">scroll to zoom</span>
          </div>
        </template>

      </div>
    </div>

    <div v-else-if="!loading" class="rb-prefetch">waiting for data</div>
    </template>
  </div>
</template>

<style scoped>
/* ── root ── */
.rb {
  position: absolute;
  inset: 0;
  padding-top: 52px; /* clear floating tab switcher */
  display: flex;
  flex-direction: column;
  font-family: var(--font-mono);
  font-size: 12px;
  overflow: hidden;
}

/* ── KPI row ──
   align-items: stretch so all cards grow to the same height as the tallest one */
.rb-kpi {
  display: flex;
  align-items: stretch;
  gap: 10px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}
.rb-kpi-err  { align-self: center; font-size: 12px; color: #cc1111; }
.rb-kpi-warn { align-self: center; font-size: 10px; color: #cc8800; max-width: 180px; line-height: 1.5; }
.rb-spacer   { flex: 1; }

/* floating card bubbles */
.rb-card {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 5px;
  padding: 9px 16px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: white;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.rb-card-lbl {
  font-size: 9px; font-weight: 700; letter-spacing: 0.16em;
  color: var(--color-secondary); opacity: 0.55;
}
.rb-card-val {
  font-size: 15px; font-weight: 700; letter-spacing: 0.02em; line-height: 1;
  color: var(--color-secondary);
}
.rb-card-sub {
  font-size: 10px; color: var(--color-secondary); letter-spacing: 0.03em;
  display: flex; align-items: center; gap: 5px;
}

/* activity colours */
.act-clean  .rb-card-val { color: var(--color-primary); }
.act-return .rb-card-val { color: #e6a817; }
.act-error  .rb-card-val { color: #cc1111; }

.rb-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.dot-on  { background: #22a855; }
.dot-off { background: var(--color-secondary); opacity: 0.35; }

/* battery */
.rb-card-bat { min-width: 200px; }
.rb-bat-row  { display: flex; align-items: center; gap: 2px; }
.rb-block       { display: inline-block; width: 6px; height: 13px; flex-shrink: 0; }
.rb-block-empty { background: var(--color-border); }
.rb-bat-pct     { font-size: 12px; font-weight: 700; margin-left: 7px; }

/* device */
.rb-card-dev .rb-card-val { font-size: 13px; }

/* controls */
.rb-controls {
  align-self: center;
  display: flex; align-items: center; gap: 10px;
}
.rb-btn {
  font-family: var(--font-mono); font-size: 10px; font-weight: 700; letter-spacing: 0.1em;
  padding: 5px 14px; border: 1px solid var(--color-border); border-radius: 12px;
  background: transparent; color: var(--color-secondary); cursor: pointer;
}
.rb-btn:hover:not(:disabled) { color: var(--color-primary); border-color: var(--color-primary); }
.rb-btn:disabled { opacity: 0.4; cursor: default; }
.rb-fetched {
  font-size: 10px; color: var(--color-secondary);
  letter-spacing: 0.04em; white-space: nowrap; opacity: 0.9;
}

/* ── skeleton ── */
@keyframes rb-pulse {
  from { opacity: 0.5; }
  to   { opacity: 0.18; }
}
.rb-sk-card { pointer-events: none; }
.sk-line {
  border-radius: 3px;
  background: var(--color-border);
  animation: rb-pulse 1.2s ease-in-out infinite alternate;
}
.sk-lbl { height: 8px;  width: 60px; }
.sk-val { height: 14px; width: 110px; }
.sk-sub { height: 8px;  width: 80px; }
.sk-tbl-head {
  height: 28px;
  background: rgba(0,0,0,0.03);
  animation: rb-pulse 1.2s ease-in-out infinite alternate;
}
/* skeleton data rows: use .rb-row for identical height; content replaced with bars */
.sk-data-row {
  pointer-events: none;
  animation: rb-pulse 1.2s ease-in-out infinite alternate;
}
.sk-bar {
  display: block;
  height: 9px;
  border-radius: 3px;
  background: var(--color-border);
  width: 70%;
}
.sk-bar-r { margin-left: auto; }
.sk-bar-c { margin: 0 auto; }
.sk-canvas {
  background: linear-gradient(135deg, #f5f5f3 0%, #eeeeec 100%);
  animation: rb-pulse 1.8s ease-in-out infinite alternate;
}

/* ── body ── */
.rb-body {
  display: grid;
  grid-template-columns: 500px 1fr;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* ── session table ── */
.rb-hist {
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.rb-hist-head {
  display: flex;
  align-items: center;
  padding: 6px 16px;
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
  gap: 8px;
}
.rb-hist-label {
  font-size: 9px; font-weight: 700; letter-spacing: 0.14em;
  color: var(--color-secondary); opacity: 0.45;
}
.rb-toggle {
  display: flex; align-items: center; gap: 6px; margin-left: auto;
  font-size: 10px; letter-spacing: 0.05em; color: var(--color-secondary);
  cursor: pointer; user-select: none;
}
.rb-chk {
  appearance: none; width: 11px; height: 11px;
  border: 1.5px solid var(--color-secondary); border-radius: 2px;
  background: transparent; cursor: pointer; position: relative; flex-shrink: 0;
}
.rb-chk:checked { background: var(--color-secondary); }
.rb-chk:checked::after {
  content: ''; position: absolute;
  left: 1px; top: -2px; width: 5px; height: 8px;
  border: 1.5px solid white; border-top: none; border-left: none;
  transform: rotate(45deg);
}
.rb-exp-badge {
  font-size: 9px; font-weight: 700; padding: 1px 5px;
  border-radius: 8px; background: var(--color-secondary); color: white;
}

.rb-tbl-head {
  display: grid;
  grid-template-columns: 1fr 88px 72px 82px 88px;
  padding: 5px 16px;
  font-size: 9px; font-weight: 700; letter-spacing: 0.12em;
  color: var(--color-secondary); opacity: 0.55;
  border-bottom: 1px solid var(--color-border);
  background: rgba(0,0,0,0.018);
  flex-shrink: 0;
}
.th-r { text-align: right; }
.th-c { text-align: center; }

.rb-row {
  display: grid;
  grid-template-columns: 1fr 88px 72px 82px 88px;
  padding: 5px 16px;
  cursor: pointer;
  border-left: 2px solid transparent;
  align-items: center;
  color: var(--color-secondary);
  font-size: 11px;
  line-height: 18px; /* explicit: pins row height for skeleton parity */
  transition: background 0.1s;
}
.rb-row:hover    { background: rgba(0,0,0,0.03); }
.rb-row.selected {
  background: rgba(0,0,0,0.04);
  border-left-color: var(--color-primary);
}
.rb-row.has-rt .rb-row-date { color: var(--color-primary); font-weight: 600; }

.rb-row-date { white-space: nowrap; overflow: hidden; }
.rb-row-dur  { text-align: right; font-size: 10px; }
.rb-row-area { text-align: right; font-size: 10px; }
.rb-row-ok   { text-align: center; font-size: 10px; }
.rb-row-rt   { text-align: right; font-size: 10px; }

.rc-saved   { color: var(--color-primary); font-weight: 700; }
.rc-exp     { opacity: 0.38; font-style: italic; }
.rc-pending { color: #e6a817; }
.rc-none    { opacity: 0.28; }

.rb-empty {
  padding: 14px 16px; font-size: 11px;
  color: var(--color-secondary); opacity: 0.5;
}

/* ── route canvas ── */
.rb-canvas {
  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #fafaf8;
}
.rb-canvas-empty {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 6px;
}
.rb-canvas-empty-title {
  font-weight: 700; font-size: 13px; letter-spacing: 0.06em;
  color: var(--color-secondary);
}
.rb-canvas-empty-note {
  font-size: 11px; color: var(--color-secondary); opacity: 0.45;
}
.rb-svg {
  flex: 1; width: 100%; height: 100%; display: block;
  cursor: crosshair; user-select: none;
}
.rb-route-info {
  position: absolute; top: 10px; left: 14px;
  display: flex; flex-direction: column; gap: 2px;
  pointer-events: none;
}
.rb-route-date {
  font-size: 11px; font-weight: 700; letter-spacing: 0.06em;
  color: var(--color-secondary); opacity: 0.6;
}
.rb-route-meta {
  font-size: 10px; color: var(--color-secondary); opacity: 0.70;
  letter-spacing: 0.03em;
}
.rb-zoom-overlay {
  position: absolute; bottom: 10px; right: 14px;
  display: flex; align-items: center; gap: 8px;
  pointer-events: none;
}
.rb-zoom-scale {
  font-size: 10px; font-weight: 700;
  color: var(--color-secondary); opacity: 0.45;
}
.rb-zoom-reset {
  pointer-events: all;
  font-family: var(--font-mono); font-size: 9px; font-weight: 700; letter-spacing: 0.08em;
  padding: 3px 10px; border: 1px solid var(--color-border); border-radius: 10px;
  background: rgba(250,250,248,0.9); color: var(--color-secondary); cursor: pointer;
}
.rb-zoom-reset:hover { color: var(--color-primary); }
.rb-zoom-hint {
  font-size: 9px; color: var(--color-secondary); opacity: 0.3; letter-spacing: 0.04em;
}

/* ── pre-fetch / idle ── */
.rb-prefetch {
  flex: 1; display: flex; align-items: center; justify-content: center;
  font-size: 11px; color: var(--color-secondary); opacity: 0.38; letter-spacing: 0.06em;
}

/* ── login gate ── */
.rb-login {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 340px;
  padding: 32px 16px;
}
.rb-login-card {
  width: 100%;
  max-width: 360px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 22px 22px 18px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}
.rb-login-title { font-weight: 600; font-size: 15px; margin-bottom: 2px; }
.rb-login-field {
  display: flex; flex-direction: column; gap: 5px;
  font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; color: #6b7280;
}
.rb-login-field input,
.rb-login-field select {
  font: inherit; font-size: 13px; text-transform: none; letter-spacing: 0;
  padding: 8px 10px; border: 1px solid var(--color-border); border-radius: 6px;
  background: #fafaf8; color: inherit;
}
.rb-login-field input:focus,
.rb-login-field select:focus {
  outline: none; border-color: var(--color-primary); background: #fff;
}
.rb-login-btn {
  margin-top: 6px; padding: 9px 12px;
  font: inherit; font-weight: 600; font-size: 13px;
  border: 1px solid var(--color-primary); border-radius: 6px;
  background: var(--color-primary); color: #fff; cursor: pointer;
}
.rb-login-btn:disabled { opacity: 0.5; cursor: default; }
.rb-login-err { font-size: 12px; color: #cc1111; margin: 0; }

/* ── initial loader (held until the first /dreame response) ── */
.rb-init { display: flex; align-items: center; justify-content: center; min-height: 340px; }
.rb-init-spinner {
  width: 22px; height: 22px; border-radius: 50%;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-primary);
  animation: rb-spin 0.7s linear infinite;
}
@keyframes rb-spin { to { transform: rotate(360deg); } }
</style>
