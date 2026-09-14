import { ref } from 'vue'

// The "ACHIEVEMENT UNLOCKED" toast — a shared, module-level signal so any feature
// can fire it (deploy success, ROM build, …) and App.vue renders the single toast.
// desc = the main line ("Successfully Deployed to Wii"); points = the right badge
// (a duration, a tick — whatever the moment earns). action = an optional button on the
// toast (e.g. "Boot" after a ROM build); the toast then stays up longer to be pressed.
export interface AchievementAction { label: string; run: () => void }
const show   = ref(false)
const desc   = ref('')
const points = ref('')
const action = ref<AchievementAction | null>(null)
let timer: ReturnType<typeof setTimeout> | undefined

export function useAchievement() {
  function unlock(d: string, p = '', a: AchievementAction | null = null) {
    desc.value = d
    points.value = p
    action.value = a
    show.value = true
    clearTimeout(timer)
    timer = setTimeout(() => { show.value = false }, a ? 15000 : 4000)
  }
  function dismiss() {
    show.value = false
    clearTimeout(timer)
  }
  return { show, desc, points, action, unlock, dismiss }
}
