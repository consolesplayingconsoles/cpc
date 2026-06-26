<script setup lang="ts">
// The one canonical close button: a ghost UiIconButton with the standard × glyph.
// Use everywhere a "dismiss/close" affordance is needed so they look identical.
// title / @click fall through to the underlying button.
//   <UiClose title="Hide for this session" @click="dismiss" />
import UiIconButton from './UiIconButton.vue'
</script>

<template>
  <UiIconButton variant="ghost">
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg>
  </UiIconButton>
</template>
