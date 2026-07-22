import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import './style.css'
import App from './App.vue'

// App.vue renders the panels itself (v-show keyed on the route name), so the routes
// only carry path + name. A no-op COMPONENT OBJECT (not `() => null`, which router
// treats as a lazy import and chokes on) satisfies the matcher without rendering.
const Blank = { render: () => null }

// Each surface carries its own channel hashtag in route meta — the global second
// header (App.vue) just renders route.meta.hashtag, so the per-page string lives with
// the route definition, not an ad-hoc map in the parent.
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'network', component: Blank, meta: { hashtag: '#consoles-connected-to-consoles' } },
    { path: '/command', name: 'command', component: Blank, meta: { hashtag: '#consoles-chatting-consoles' } },
    { path: '/chat', redirect: '/command' },   // back-compat: Chat -> Command (C2)
    // Control surface: host (which machine) / source (event producer) / target (output
    // sink) / mapping (control scheme). All four ride the URL so a reload restores the
    // whole selection instead of dropping to a default (the old reload-to-Disabled trap).
    { path: '/control/:host?/:source?/:target?/:mapping?', name: 'control', component: Blank, meta: { hashtag: '#anything-playing-anything' } },
    // :ns is the project namespace (game + language) — rides the URL so a reload /
    // HMR / bookmark restores the open table instead of dropping to the picker.
    { path: '/translation/:ns?', name: 'translation', component: Blank, meta: { hashtag: '#consolas-traduciendo-consolas' } },
    { path: '/dreame', redirect: '/control/dreame' },   // back-compat
    // Anything else falls back to the network view.
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

createApp(App).use(router).mount('#app')
