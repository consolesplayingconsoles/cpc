import { ref } from 'vue'

// The "ACHIEVEMENT UNLOCKED" toast — a shared, module-level signal so any feature
// can fire it (deploy success, ROM build, …) and App.vue renders the single toast.
// desc = the main line ("Successfully Deployed to Wii"); points = the right badge
// (a duration, a tick — whatever the moment earns).
const show   = ref(false)
const desc   = ref('')
const points = ref('')
let timer: ReturnType<typeof setTimeout> | undefined

export function useAchievement() {
  function unlock(d: string, p = '') {
    desc.value = d
    points.value = p
    show.value = true
    clearTimeout(timer)
    timer = setTimeout(() => { show.value = false }, 4000)
  }
  function dismiss() {
    show.value = false
    clearTimeout(timer)
  }
  return { show, desc, points, unlock, dismiss }
}
