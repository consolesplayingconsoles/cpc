<script setup lang="ts">
// Shared pet (dog paw) glyph -- the single source for the "pet detected" marker,
// used in the Robutek session table and (later) on the network map, so the two
// always match. Inherits size from font-size/width and colour from currentColor.
</script>

<template>
  <svg class="pet-icon" viewBox="0 0 24 24" fill="currentColor"
       role="img" aria-label="pet detected">
    <ellipse cx="12" cy="16.5" rx="5.2" ry="4.3" />
    <ellipse cx="5.6" cy="11"   rx="2.1" ry="2.7" />
    <ellipse cx="18.4" cy="11"  rx="2.1" ry="2.7" />
    <ellipse cx="9.4" cy="6.8"  rx="2"   ry="2.6" />
    <ellipse cx="14.6" cy="6.8" rx="2"   ry="2.6" />
  </svg>
</template>

<style scoped>
.pet-icon { width: 1em; height: 1em; display: inline-block; vertical-align: -0.15em; }
</style>
