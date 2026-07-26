<script setup lang="ts">
// One editable line inside a scene box. Extracted from TranslationTable so that typing in a
// textarea only re-renders THIS row — the parent's render function no longer reads any block.ca,
// so the 76 scene headers and every other row stay put while you type. Presentational: it mutates
// the block object it's handed (same reference the parent holds) and emits when the edit commits.
import { type Block, caBytes } from '../../lib/translation'
import { computed } from 'vue'

const props = defineProps<{
  block: Block
  showLegend: boolean
  runStart: boolean          // first line of a speaker run (draws the name + top border)
  cum: number                // running box fill up to and including this line
  slack: number              // the box's budget
  dupCount: number           // how many lines share this exact Japanese (propagate target count)
  speakerColor: string
  speakerLabel: string
  kind: string               // source kind (dialogue/menu/items/ui) — items shows glyph-width, others show bytes
}>()
const emit = defineEmits<{ (e: 'commit'): void; (e: 'propagate'): void }>()

// Color signal. Items: gadget NAMES color by the SHARED item-area aggregate (cum vs slack) — a
// name isn't over on its own, the 156 of them share one budget; DESCRIPTIONS (slack 0) have their
// own big sector, so they're fine once written. Dialogue: color by cumulative box fill.
const lineStatus = computed<'pending' | 'ok' | 'warn' | 'over'>(() => {
  if (props.kind === 'items') {
    if (props.block.ca === '') return props.block.done ? 'ok' : 'pending'
    if (props.slack <= 0) return 'ok'                    // a description: own sector, effectively unbounded
    return props.cum <= props.slack ? 'ok' : 'over'      // hard limit (no spill): it fits or it doesn't
  }
  // Dialogue/menu/ui: color based on cumulative box fill at THIS line (not the line's own bytes)
  if (props.slack <= 0) return 'pending'
  if (props.cum <= props.slack) return 'ok'
  if (props.cum <= props.slack * 1.3) return 'warn'
  return 'over'
})
</script>

<template>
  <tr class="tt-row scene-body" :class="{ 'run-start': runStart, 'run-cont': !runStart }">
    <td class="col-order"></td>
    <td class="col-offset mono">{{ block.offset }}</td>

    <td v-if="showLegend" class="col-speaker">
      <div v-if="runStart" class="speaker-cell">
        <span class="speaker-dot" :style="{ background: speakerColor }" />
        <span class="speaker-name">{{ speakerLabel }}</span>
      </div>
      <div v-else class="speaker-cont">
        <span class="speaker-cont-line" :style="{ background: speakerColor }" />
      </div>
    </td>

    <td class="col-jp">
      <span class="jp-text">{{ block.jp }}</span>
      <span v-if="block.note" class="block-note" :title="block.note">⚠</span>
    </td>

    <td class="col-ca">
      <div class="ca-cell">
        <textarea class="ca-input" v-model="block.ca" rows="2" @blur="emit('commit')" />
        <button v-if="dupCount > 1" class="ca-prop" type="button"
                :title="`Copy this Catalan into all ${dupCount} identical lines`"
                @click="emit('propagate')">propagate to {{ dupCount }}</button>
      </div>
    </td>

    <td class="col-bytes">
      <div class="bytes-cell" :class="lineStatus">
        <template v-if="kind === 'items'">
          <!-- Items: this record's own bytes (the shared budget lives in the aggregate below) -->
          <span class="bytes-used">{{ caBytes(block.ca) }}</span>
          <span class="bytes-sep">B</span>
        </template>
        <template v-else>
          <!-- Dialogue/menu/ui: show bytes vs jp bytes -->
          <span class="bytes-used">{{ caBytes(block.ca) }}</span>
          <span class="bytes-sep">/</span>
          <span class="bytes-budget">{{ block.jpBytes }}</span>
        </template>
      </div>
      <!-- Aggregate on EVERY line, like a STORY box: names run cumulative vs the shared item area;
           each description meters its own bytes vs its own sector. -->
      <div v-if="kind !== 'items' || slack > 0" class="box-agg" :class="{ over: cum > slack }"
           :title="kind !== 'items'
             ? `box used to here: ${cum.toLocaleString()} / ${slack.toLocaleString()} B`
             : block.desc
               ? `description: ${cum.toLocaleString()} / ${slack.toLocaleString()} B of its sector`
               : `gadget names use ${cum.toLocaleString()} / ${slack.toLocaleString()} B of the shared item area`">
        <span class="box-agg-label">{{ kind !== 'items' ? 'Agg' : (block.desc ? 'Sector' : 'Item area') }}</span>
        <span class="box-progress">
          <span class="box-progress-fill"
                :style="{ width: Math.min(100, slack ? cum / slack * 100 : 0) + '%' }"></span>
        </span>
      </div>
    </td>

    <td class="col-done">
      <input type="checkbox" v-model="block.done" @change="emit('commit')"
             title="Done — keep original Japanese" />
    </td>
  </tr>
</template>
