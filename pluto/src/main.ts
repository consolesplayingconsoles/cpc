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
    { path: '/chat', name: 'chat', component: Blank },
    { path: '/dreame', name: 'dreame', component: Blank },
    // Anything else falls back to the network view.
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

createApp(App).use(router).mount('#app')
