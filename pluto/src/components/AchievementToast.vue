<script setup lang="ts">
defineProps<{ show: boolean; consoleName: string; duration: string }>()
defineEmits<{ dismiss: [] }>()
</script>

<template>
  <Transition name="achievement">
    <div v-if="show" class="achievement-toast" @click.stop="$emit('dismiss')">
      <div class="achievement-toast__badge">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/>
          <path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/>
          <path d="M4 22h16"/>
          <path d="M10 14.66V17c0 .55-.45 1-1 1H4v2h16v-2h-5c-.55 0-1-.45-1-1v-2.34"/>
          <path d="M12 2a4 4 0 0 1 4 4v6a4 4 0 0 1-4 4 4 4 0 0 1-4-4V6a4 4 0 0 1 4-4z"/>
        </svg>
      </div>
      <div class="achievement-toast__content">
        <div class="achievement-toast__title">ACHIEVEMENT UNLOCKED</div>
        <div class="achievement-toast__desc">Successfully Deployed to {{ consoleName }}</div>
      </div>
      <div class="achievement-toast__points">{{ duration }}</div>
    </div>
  </Transition>
</template>

<style scoped>
.achievement-toast {
  position: absolute;
  top: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 350px;
  padding: 10px 18px;
  background: #090d0a;
  border: 2px solid #3deb76;
  border-radius: 30px;
  box-shadow: 0 12px 36px rgba(0,0,0,0.65), 0 0 25px rgba(61,235,118,0.3);
  cursor: pointer;
  user-select: none;
}
.achievement-toast__badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: #122919;
  border-radius: 50%;
  color: #3deb76;
  filter: drop-shadow(0 0 4px rgba(61,235,118,0.6));
}
.achievement-toast__content { display: flex; flex-direction: column; flex-grow: 1; }
.achievement-toast__title {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.12em;
  color: #9fcfb0;
}
.achievement-toast__desc {
  font-family: sans-serif;
  font-size: 13px;
  font-weight: 500;
  color: #ffffff;
  margin-top: 1px;
}
.achievement-toast__points {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 700;
  color: #3deb76;
  padding-left: 10px;
  border-left: 1px solid #1c472a;
  white-space: nowrap;
}
.achievement-enter-active { animation: achievement-in 0.45s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
.achievement-leave-active { animation: achievement-in 0.28s ease-in reverse; }
@keyframes achievement-in {
  0%   { top: -65px; opacity: 0; transform: translateX(-50%) scale(0.88); }
  75%  { transform: translateX(-50%) scale(1.02); }
  100% { top: 24px;  opacity: 1; transform: translateX(-50%) scale(1); }
}
</style>
