<script setup lang="ts">
// Persistent strip above the table: one chip per distinct speaker in the active
// source, with the colour that matches the table's speaker column and an editable
// name. Only rendered when the source actually has speaker tags. Presentational:
// the parent owns the names map and persists on rename.
defineProps<{
  speakers: { id: number; color: string; count: number }[]
  names: Record<number, string>
  pct?: Record<number, number>
}>()
const emit = defineEmits<{ (e: 'rename', id: number, name: string): void }>()

// Faint completion tint behind each chip: red < 50%, yellow < 100%, green = 100%.
function pctTint(p: number | undefined): string {
  const v = p ?? 0
  if (v >= 100) return 'rgba(70, 170, 90, 0.16)'    // green
  if (v >= 50)  return 'rgba(210, 170, 50, 0.16)'   // yellow
  return 'rgba(210, 80, 80, 0.13)'                  // red
}
</script>

<template>
  <div class="sl">
    <span class="sl__label">Speakers</span>
    <div v-for="s in speakers" :key="s.id" class="sl__chip"
         :style="{ background: pctTint(pct?.[s.id]) }"
         :title="`${pct?.[s.id] ?? 0}% done`">
      <span class="sl__dot" :style="{ background: s.color }"></span>
      <span class="sl__id">{{ s.id }}</span>
      <input
        class="sl__name"
        :value="names[s.id] || ''"
        :size="Math.max((names[s.id] || 'Unknown').length, 4)"
        placeholder="Unknown"
        spellcheck="false"
        @input="emit('rename', s.id, ($event.target as HTMLInputElement).value)"
      />
      <span class="sl__count" :title="`${s.count} lines`">{{ s.count }}</span>
    </div>
  </div>
</template>

<style scoped>
.sl {
  display: flex; align-items: center; flex-wrap: wrap; gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--line); border-radius: var(--r-sm);
  background: var(--surface-2); margin: 0 var(--sp-3) var(--sp-2);
}
.sl__label {
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--text-faint); margin-right: var(--sp-1);
}
.sl__chip {
  display: inline-flex; align-items: center; gap: 6px;
  background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--r-sm); padding: 2px 6px 2px 8px;
}
.sl__dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.sl__id { font-family: var(--font-mono); font-size: 11px; color: var(--text-faint); }
.sl__name {
  border: none; border-bottom: 1px dashed var(--line); background: none; outline: none;
  padding: 1px 1px; font-size: 12px; color: var(--text);
  min-width: 4ch; cursor: text; field-sizing: content;   /* fit the full name, no trailing gap */
  transition: border-color .12s, background .12s;
}
.sl__name:hover  { border-bottom-color: var(--accent); background: var(--surface-2); }
.sl__name:focus  { border-bottom: 1px solid var(--accent); background: var(--surface-2); }
.sl__name::placeholder { color: var(--text-faint); font-style: italic; }
.sl__count {
  font-family: var(--font-mono); font-size: 10px; color: var(--text-faint);
  background: var(--surface-2); border-radius: 999px; padding: 0 5px;
}
</style>
