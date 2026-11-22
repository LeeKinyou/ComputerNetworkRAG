/** 登录态：cookie 由后端下发，前端只缓存 /auth/me 的结果。 */

import { ref } from 'vue'
import { api } from '@/api/client'
import { lockStudent, setStudent, unlockStudent } from '@/composables/useStudent'

export interface AuthUser {
  username: string
  role: 'teacher' | 'student'
  user_key: string
}

interface MeResponse {
  authenticated: boolean
  auth_enabled: boolean
  user: AuthUser | null
}

interface LoginResponse {
  authenticated: boolean
  user: AuthUser
}

const user = ref<AuthUser | null>(null)
const authEnabled = ref(true)
const ready = ref(false)

/** 学生登录后把「当前学生」钉在自己身上；教师恢复自由切换（仅本次登录重置视角）。 */
function bindIdentity(account: AuthUser | null, resetTeacherView = false) {
  if (!account) return
  if (account.role === 'student') lockStudent(account.user_key)
  else {
    unlockStudent()
    if (resetTeacherView) setStudent('demo_user')
  }
}

async function refresh(): Promise<boolean> {
  try {
    const me = await api.get<MeResponse>('/auth/me')
    authEnabled.value = me.auth_enabled
    user.value = me.user
    bindIdentity(me.user)
    return me.authenticated
  } catch {
    user.value = null
    return false
  } finally {
    ready.value = true
  }
}

async function login(username: string, password: string): Promise<AuthUser> {
  const result = await api.post<LoginResponse>('/auth/login', { username, password })
  user.value = result.user
  bindIdentity(result.user, true)
  return result.user
}

async function logout(): Promise<void> {
  try {
    await api.post('/auth/logout')
  } finally {
    user.value = null
    unlockStudent()
  }
}

export function useAuth() {
  return { user, authEnabled, ready, refresh, login, logout }
}
