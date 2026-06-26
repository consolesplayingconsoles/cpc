import { ref } from 'vue'

// Reactive dark-mode flag. App.vue owns the toggle (it sets data-theme on <html>
// and persists it); this just OBSERVES that attribute, so any component can react
// to the theme without reaching into App's local state. Module-level singleton —
// one observer for the whole app.
const isDark = ref(
  typeof document !== 'undefined' &&
  document.documentElement.getAttribute('data-theme') === 'dark',
)
if (typeof MutationObserver !== 'undefined') {
  new MutationObserver(() => {
    isDark.value = document.documentElement.getAttribute('data-theme') === 'dark'
  }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
}

// ── colour legibility ────────────────────────────────────────────────────────
function srgbToLin(c: number) {
  const x = c / 255
  return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4
}
function relLuminance(r: number, g: number, b: number) {
  return 0.2126 * srgbToLin(r) + 0.7152 * srgbToLin(g) + 0.0722 * srgbToLin(b)
}
function toHex(r: number, g: number, b: number) {
  return '#' + [r, g, b].map(x => Math.round(x).toString(16).padStart(2, '0')).join('')
}

// A console's brand colour can be too dark to read as text on the dark surface —
// and saturated mid-tones (the crimson/navy/purple consoles) are the worst: vivid
// but low-luminance, so they sit around 3:1. In dark mode ONLY, lift anything below
// a legibility floor toward white until it clears it (~6:1 on the darkest chat
// surface). Bright brands (orange, light blue) and non-hex / light mode pass
// straight through. Reads isDark, so template bindings stay reactive to the toggle.
const MIN_LUM = 0.30
export function readableBrand(color: string): string {
  if (!isDark.value) return color
  const m = /^#?([0-9a-fA-F]{6})$/.exec(color.trim())
  if (!m) return color
  const r = parseInt(m[1].slice(0, 2), 16)
  const g = parseInt(m[1].slice(2, 4), 16)
  const b = parseInt(m[1].slice(4, 6), 16)
  if (relLuminance(r, g, b) >= MIN_LUM) return color
  for (let t = 0.08; t < 1; t += 0.08) {
    const nr = r + (255 - r) * t, ng = g + (255 - g) * t, nb = b + (255 - b) * t
    if (relLuminance(nr, ng, nb) >= MIN_LUM) return toHex(nr, ng, nb)
  }
  return '#e8eaed'
}

export function useTheme() {
  return { isDark, readableBrand }
}
