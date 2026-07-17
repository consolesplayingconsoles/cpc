<script setup lang="ts">
// Canonical pill switch (boolean). A sliding thumb, optionally followed by a state label.
// Extracted from the keyboard pad's Analog/D-Pad toggle so every mode switch looks the same.
//   <UiToggle v-model="on" />                                      -- bare pill
//   <UiToggle v-model="on" on-label="Zone" off-label="Movement" /> -- pill + state label
defineProps<{ modelValue: boolean; onLabel?: string; offLabel?: string; title?: string; disabled?: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()
</script>

<template>
  <span class="ui-toggle">
    <button type="button" class="ui-toggle-pill" :class="{ on: modelValue }" :disabled="disabled"
            role="switch" :aria-checked="modelValue" :title="title"
            @click="emit('update:modelValue', !modelValue)">
      <span class="ui-toggle-thumb" />
    </button>
    <span v-if="onLabel || offLabel" class="ui-toggle-tag" :class="{ active: modelValue }">
      {{ modelValue ? onLabel : offLabel }}
    </span>
  </span>
</template>

<style scoped>
.ui-toggle { display: inline-flex; align-items: center; gap: 8px; }
.ui-toggle-pill {
  position: relative; width: 32px; height: 18px;
  background: var(--line-strong); border: none; border-radius: 9px;
  cursor: pointer; padding: 0; transition: background 0.18s; flex-shrink: 0;
}
.ui-toggle-pill.on { background: var(--accent); }
.ui-toggle-pill:disabled { cursor: not-allowed; opacity: 0.5; }
.ui-toggle-thumb {
  position: absolute; top: 2px; left: 2px;
  width: 14px; height: 14px; border-radius: 50%;
  background: #fff; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3); transition: transform 0.18s;
  pointer-events: none;
}
.ui-toggle-pill.on .ui-toggle-thumb { transform: translateX(14px); }
.ui-toggle-tag {
  font-size: 10px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;
  color: var(--text-muted); transition: color 0.18s;
}
.ui-toggle-tag.active { color: var(--accent); }
</style>
