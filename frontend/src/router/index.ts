import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: () => import('@/views/Dashboard.vue') },
    { path: '/research', name: 'research', component: () => import('@/views/ResearchList.vue') },
    { path: '/research/quick', name: 'research-quick', component: () => import('@/views/ResearchQuick.vue') },
    { path: '/research/timeline', name: 'research-timeline', component: () => import('@/views/ResearchTimeline.vue') },
    { path: '/research/:id', name: 'research-detail', component: () => import('@/views/ResearchDetail.vue') },
    { path: '/companies', name: 'companies', component: () => import('@/views/Companies.vue') },
    { path: '/companies/:id', name: 'company-detail', component: () => import('@/views/CompanyDetail.vue') },
    { path: '/market', name: 'market', component: () => import('@/views/Market.vue') },
    { path: '/screener', name: 'screener', component: () => import('@/views/Screener.vue') },
    { path: '/documents', name: 'documents', component: () => import('@/views/Documents.vue') },
    { path: '/knowledge', name: 'knowledge', component: () => import('@/views/Knowledge.vue') },
    { path: '/ai', name: 'ai', component: () => import('@/views/AICenter.vue') },
    { path: '/portfolio', name: 'portfolio', component: () => import('@/views/Portfolio.vue') },
    { path: '/system', name: 'system', component: () => import('@/views/System.vue') },
  ],
})

export default router
