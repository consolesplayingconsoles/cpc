<script setup lang="ts">
import { ref, computed } from 'vue'
import UiButton from './ui/UiButton.vue'

// Generates a small, AGENTIC prompt: Claude fetches the source JSON from the
// workbench API, translates it (respecting per-line byte budgets), and PUTs the
// result back — json in, json out. No line list embedded, no manual parsing.
interface PBlock { jp: string; jpBytes: number; speakerId: number }
const props = defineProps<{
  title: string
  target: string
  file: string                  // on-disc filename (display)
  safe: string                  // sanitized source key in state.json.sources
  kindLabel: string
  ns: string                    // project namespace (dir name)
  apiBase: string               // absolute API base, e.g. http://host:7700
  blocks: PBlock[]
  speakerNames: Record<number, string>
  modelValue: string            // reference links / tone notes, one per line
}>()
const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const refLines = computed(() =>
  props.modelValue.split('\n').map(s => s.trim()).filter(Boolean),
)
const speakerLine = computed(() => {
  const ids = [...new Set(props.blocks.map(b => b.speakerId))].filter(id => props.speakerNames[id])
  if (!ids.length) return ''
  return 'Speakers in this source: ' + ids.map(id => `${id} = ${props.speakerNames[id]}`).join(', ') + '.\n\n'
})
// Name the ONE source this prompt targets (matches the tab label), so it's clear
// this translates a single tab, not the whole disc.
const tabName = computed(() => `${props.file.replace(/\.[^.]+$/, '')} (${props.kindLabel.toUpperCase()})`)

const prompt = computed(() => {
  const n = props.blocks.length
  const refSection = refLines.value.length
    ? 'Reference material for tone, terminology and canonical names:\n'
      + refLines.value.map(r => '- ' + r).join('\n') + '\n\n'
    : ''
  return `You are localizing the SEGA Dreamcast game "${props.title}" from Japanese into ${props.target}.

Source: "${props.file}" — ${props.kindLabel.toLowerCase()}, ${n} lines.

${speakerLine.value}${refSection}Use the repo helper ./scripts/cpc (set CPC_API=${props.apiBase} if it can't reach the workbench):

1. FETCH:  ./scripts/cpc get "${props.ns}" "${props.safe}"
   Prints a JSON array of ${n} elements; each has "jp" (the Japanese), "jpBytes" (its byte budget) and "ca" (current translation, usually empty).

2. TRANSLATE into ${props.target}, IN ORDER, in contiguous BATCHES of ~200 lines (model output limits make one shot of ${n} impossible). Start at the first line whose "ca" is empty. For each batch, output a JSON array of just that batch's translation strings, in order — do NOT deduplicate, reorder, merge or skip within the batch; identical "jp" get the same translation but stay at their positions.
   HARD CONSTRAINT: the game renders a FULL-WIDTH font (2 bytes per character) with NO accents, so a translation must be at most floor("jpBytes" / 2) CHARACTERS — roughly the Japanese line's own character count. Write without accents (à→a, ç→c); they're dropped anyway. Be terse: rephrase shorter or abbreviate rather than exceed the limit. Keep character names and tone consistent with the reference material above.

3. SUBMIT each batch the MOMENT it's done — don't wait for the end, that risks losing it all:
   ./scripts/cpc put "${props.ns}" "${props.safe}" <start> < batch.json
   <start> = the 0-based index of the batch's first line (0, then 200, 400, …). cpc writes the batch at that position and rejects out-of-bounds. Repeat until every line has a "ca"; a fresh cpc get shows what is still empty.

Call cpc directly — do not print the translations for me to copy.`
})

const copied = ref(false)
let t = 0
function copyPrompt() {
  navigator.clipboard?.writeText(prompt.value).then(() => {
    copied.value = true
    if (t) clearTimeout(t)
    t = window.setTimeout(() => { copied.value = false }, 1400)
  }).catch(() => { /* clipboard unavailable */ })
}
</script>

<template>
  <div class="pc">
    <h3 class="pc__title">Let Claude Translate <span class="pc__title-src">{{ tabName }}</span></h3>

    <div class="pc__field">
      <label class="pc__label">Reference links / tone notes</label>
      <textarea
        class="pc__refs"
        :value="modelValue"
        rows="3"
        spellcheck="false"
        placeholder="One per line — dubbed episode, character wiki, fan script, glossary…"
        @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
      />
      <span class="pc__hint">Saved with the project and reused in every prompt for consistent tone.</span>
    </div>

    <div class="pc__prompthead">
      <span class="pc__label">Prompt</span>
      <span class="pc__count">{{ blocks.length.toLocaleString() }} lines</span>
    </div>
    <pre class="pc__prompt">{{ prompt }}</pre>

    <div class="pc__copyrow">
      <UiButton variant="primary" class="pc__copy" @click="copyPrompt">
        {{ copied ? 'Copied ✓' : 'Copy prompt' }}
      </UiButton>
      <span class="pc__copyhint">The Pluto API is accessible by the agent. Paste this prompt to Claude Code and keep chatting for better results. Changes will show on this page immediately.</span>
    </div>
  </div>
</template>

<style scoped>
.pc { display: flex; flex-direction: column; gap: var(--sp-3); min-height: 0; }
.pc__title { margin: 0; font-size: 15px; font-weight: 600; color: var(--text); line-height: 1.35; }
.pc__title-src { color: var(--accent); font-family: var(--font-mono); font-size: 13px; margin-left: 4px }
.pc__field { display: flex; flex-direction: column; gap: 4px; }
.pc__label {
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-faint);
}
.pc__hint { font-size: 11px; color: var(--text-faint); }
.pc__refs {
  width: 100%; resize: vertical; box-sizing: border-box;
  border: 1px solid var(--line); border-radius: var(--r-sm); background: var(--surface);
  padding: 6px 8px; font-size: 12px; color: var(--text); font-family: inherit;
}
.pc__refs:focus { outline: none; border-color: var(--accent); }
.pc__prompthead { display: flex; align-items: baseline; justify-content: space-between; }
.pc__count { font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); }
.pc__prompt {
  flex: 1; min-height: 120px; max-height: 38vh; overflow: auto; margin: 0;
  border: 1px solid var(--line); border-radius: var(--r-sm); background: var(--surface-2);
  padding: 8px 10px; font-family: var(--font-mono); font-size: 11px; line-height: 1.5;
  color: var(--text); white-space: pre-wrap; word-break: break-word;
}
.pc__copyrow { display: flex; align-items: center; gap: 10px; }
.pc__copy { align-self: flex-start; }
.pc__copyhint { font-size: 12px; color: var(--text-muted); }
</style>
