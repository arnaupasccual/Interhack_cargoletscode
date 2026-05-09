import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import './style.css'
import App from './App.vue'
import DashboardView from './views/DashboardView.vue'
import AlertsView from './views/AlertsView.vue'
import AlertDetailView from './views/AlertDetailView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/',          component: DashboardView },
    { path: '/alerts',    component: AlertsView },
    { path: '/alerts/:id', component: AlertDetailView, props: true },
  ],
})

createApp(App).use(router).mount('#app')
