<script setup lang="ts">
import { computed, ref } from 'vue'

interface ActivityMessage {
  id:     number
  sender: string
  text:   string
  ts?:    string
}

const props = withDefaults(
  defineProps<{ messages: ActivityMessage[]; max?: number }>(),
  { max: 6 },
)

const emit = defineEmits<{ expand: [] }>()

const collapsed = ref(false)
const recent = computed(() => props.messages.slice(-props.max))
</script>

<template>
  <div v-if="messages.length" class="activity" :class="{ 'activity--collapsed': collapsed }" @click.stop>
    <div class="activity__head">
      <span class="activity__label">Recent Activity</span>
      <span class="activity__btns">
        <button class="activity__btn" :title="collapsed ? 'Show' : 'Minimize'" @click="collapsed = !collapsed">
          <svg width="13" height="13" viewBox="0 0 16 16" aria-hidden="true" :style="{ transform: collapsed ? 'rotate(180deg)' : 'none' }">
            <path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
        <button class="activity__btn" title="Open Chat" @click="emit('expand')">
          <svg width="13" height="13" viewBox="0 0 16 16" aria-hidden="true">
            <path d="M2.5 3.5h11v7h-7l-3 2.5v-2.5h-1z"
                  fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>
          </svg>
        </button>
      </span>
    </div>
    <ul v-if="!collapsed" class="activity__list">
      <li v-for="m in recent" :key="m.id" class="activity__row">
        <span class="activity__sender">{{ m.sender }}:</span>
        <span class="activity__text">{{ m.text }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
/* recent-activity tail — quiet glass peek, bottom-left, mirrors .zoom-controls */
.activity {
  width: 360px;
  max-width: 360px;
  padding: 9px 11px 10px;
  background: rgba(238, 240, 243, 0.92);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid var(--line);
  border-radius: 10px;
  box-shadow: 0 6px 22px rgba(26, 34, 51, 0.10);
}
.activity__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.activity--collapsed .activity__head { margin-bottom: 0; }
.activity__label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-faint);
}
.activity__btns { display: flex; gap: 2px; }
.activity__btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  color: var(--text-muted);
  background: transparent;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
}
.activity__btn:hover         { color: var(--accent); background: rgba(26, 34, 51, 0.06); }
.activity__btn:focus         { outline: none; }
.activity__btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.activity__list {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.activity__row {
  display: flex;
  gap: 5px;
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.35;
  white-space: nowrap;
  overflow: hidden;
}
.activity__sender {
  flex: none;
  font-weight: 600;
  color: var(--text);
}
.activity__text {
  flex: 1 1 auto;
  min-width: 0;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
