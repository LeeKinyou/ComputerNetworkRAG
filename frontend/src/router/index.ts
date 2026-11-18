import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: () => import('@/pages/OverviewPage.vue') },
    { path: '/graph', name: 'graph', component: () => import('@/pages/GraphPage.vue') },
    { path: '/path', name: 'path', component: () => import('@/pages/PathPage.vue') },
    { path: '/rag', redirect: { path: '/chat', query: { mode: 'rag' } } },
    { path: '/chat', name: 'chat', component: () => import('@/pages/ChatPage.vue') },
    { path: '/practice', name: 'practice', component: () => import('@/pages/PracticePage.vue') },
    { path: '/documents', name: 'documents', component: () => import('@/pages/DocumentsPage.vue') },
    { path: '/progress', name: 'progress', component: () => import('@/pages/ProgressPage.vue') },
    { path: '/insights', name: 'insights', component: () => import('@/pages/InsightsPage.vue') },
    { path: '/profile', name: 'profile', component: () => import('@/pages/ProfilePage.vue') },
    {
      path: '/screen',
      name: 'screen',
      component: () => import('@/pages/ScreenPage.vue'),
      meta: { fullscreen: true },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

export default router
