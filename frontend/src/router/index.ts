import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/screener' },
    { path: '/market', name: 'market', component: () => import('@/views/Market.vue') },
    { path: '/screener', name: 'screener', component: () => import('@/views/Screener.vue') },
    { path: '/documents', name: 'documents', component: () => import('@/views/Documents.vue') },
    { path: '/system', name: 'system', component: () => import('@/views/System.vue') },
  ],
})

export default router
