<script setup lang="ts">
// One editable line inside a scene box. Extracted from TranslationTable so that typing in a
// textarea only re-renders THIS row — the parent's render function no longer reads any block.ca,
// so the 76 scene headers and every other row stay put while you type. Presentational: it mutates
// the block object it's handed (same reference the parent holds) and emits when the edit commits.
import { type Block, caBytes } from '../lib/translation'

defineProps<{
  block: Block
  showLegend: boolean
  runStart: boolean          // first line of a speaker run (draws the name + top border)
  cum: number                // running box fill up to and including this line
  slack: number              // the box's budget
  dupCount: number           // how many lines share this exact Japanese (propagate target count)
  speakerColor: string
  speakerLabel: string
}>()
const emit = defineEmits<{ (e: 'commit'): void; (e: 'propagate'): void }>()
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
      <div class="bytes-cell">
        <span class="bytes-used">{{ caBytes(block.ca) }}</span>
        <span class="bytes-sep">/</span>
        <span class="bytes-budget">{{ block.jpBytes }}</span>
      </div>
      <div class="box-agg" :class="{ over: cum > slack }"
           :title="`box used to here: ${cum.toLocaleString()} / ${slack.toLocaleString()} B`">
        <span class="box-agg-label">Agg</span>
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
