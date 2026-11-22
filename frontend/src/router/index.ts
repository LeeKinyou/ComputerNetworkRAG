import { createRouter, createWebHistory } from 'vue-router'
import { useAuth } from '@/composables/useAuth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/pages/LoginPage.vue'),
      meta: { public: true, bare: true },
    },
    { path: '/', name: 'overview', component: () => import('@/pages/OverviewPage.vue') },
    { path: '/assignments', name: 'assignments', component: () => import('@/pages/AssignmentsPage.vue') },
    { path: '/graph', name: 'graph', component: () => import('@/pages/GraphPage.vue') },
    { path: '/path', name: 'path', component: () => import('@/pages/PathPage.vue') },
    { path: '/rag', redirect: { path: '/chat', query: { mode: 'rag' } } },
    { path: '/chat', name: 'chat', component: () => import('@/pages/ChatPage.vue') },
    { path: '/practice', name: 'practice', component: () => import('@/pages/PracticePage.vue') },
    { path: '/wrongbook', name: 'wrongbook', component: () => import('@/pages/WrongBookPage.vue') },
    { path: '/documents', name: 'documents', component: () => import('@/pages/DocumentsPage.vue') },
    { path: '/progress', name: 'progress', component: () => import('@/pages/ProgressPage.vue') },
    {
      path: '/insights',
      name: 'insights',
      component: () => import('@/pages/InsightsPage.vue'),
      meta: { teacherOnly: true },
    },
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

/**
 * 登录守卫：
 * - 后端关闭鉴权（AUTH_ENABLED=false）时直接放行；
 * - 未登录只能到 /login，其余路由带 redirect 回跳；
 * - 教师专属页面对学生重定向到工作台。
 */
router.beforeEach(async (to) => {
  const { user, authEnabled, ready, refresh } = useAuth()
  if (!ready.value) await refresh()

  if (!authEnabled.value) return true

  if (to.meta.public) {
    return user.value ? { path: '/' } : true
  }
  if (!user.value) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.meta.teacherOnly && user.value.role !== 'teacher') {
    return { path: '/' }
  }
  return true
})

export default router
