import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './style.css'
import { setUnauthorizedHandler } from './api/client'
import { useAuth } from './composables/useAuth'

const { user } = useAuth()

// 会话过期或被顶掉：清掉本地身份，带当前路径回登录页
setUnauthorizedHandler(() => {
  user.value = null
  const current = router.currentRoute.value
  if (current.name !== 'login') {
    void router.replace({ path: '/login', query: { redirect: current.fullPath } })
  }
})

createApp(App).use(createPinia()).use(router).mount('#app')
