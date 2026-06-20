import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import './style.css'
import App from './App.vue'

// App.vue renders the panels itself (v-show keyed on the route name), so the routes
// only carry path + name. A no-op COMPONENT OBJECT (not `() => null`, which router
// treats as a lazy import and chokes on) satisfies the matcher without rendering.
const Blank = { render: () => null }

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'network', component: Blank },
    { path: '/command', name: 'command', component: Blank },
    { path: '/chat', redirect: '/command' },   // back-compat: Chat -> Command (C2)
    // Control surface: source (event producer) / target (output sink) / mapping
    // (control scheme). All three ride the URL so a reload restores the selection
    // instead of dropping to a default (the old reload-to-Disabled trap).
    { path: '/control/:source?/:target?/:mapping?', name: 'control', component: Blank },
    { path: '/dreame', redirect: '/control/dreame' },   // back-compat
    // Anything else falls back to the network view.
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

createApp(App).use(router).mount('#app')
