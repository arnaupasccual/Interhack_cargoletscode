import { createRouter, createWebHistory } from 'vue-router'
import AlertListView from '../views/AlertListView.vue'
import AlertDetailView from '../views/AlertDetailView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/alerts' },
    {
      path: '/alerts',
      name: 'alert-list',
      component: AlertListView,
    },
    {
      path: '/alerts/:id',
      name: 'alert-detail',
      component: AlertDetailView,
      props: true,
    },
  ],
})

export default router
