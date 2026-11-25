<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { LoaderCircle, Sparkles } from 'lucide-vue-next'
import { ApiError } from '@/api/client'
import { useAuth } from '@/composables/useAuth'

const router = useRouter()
const route = useRoute()
const { login, authEnabled } = useAuth()

const username = ref('')
const password = ref('')
const pending = ref(false)
const error = ref('')
const demoOpen = ref(false)

/** 演示账号：只保留名字，说明性文案全部去掉。 */
const demoAccounts = [
  { label: '教师', username: 'teacher', password: 'teacher2026' },
  { label: '李金洋', username: 'demo_user', password: 'demo2026' },
  { label: '林晓', username: 'stu_lin', password: 'lin2026' },
  { label: '赵一鸣', username: 'stu_zhao', password: 'zhao2026' },
]

const redirect = computed(() => {
  const value = route.query.redirect
  return typeof value === 'string' && value.startsWith('/') ? value : '/'
})

function fill(account: (typeof demoAccounts)[number]) {
  username.value = account.username
  password.value = account.password
  demoOpen.value = false
  error.value = ''
}

async function submit() {
  if (pending.value) return
  error.value = ''
  pending.value = true
  try {
    await login(username.value.trim(), password.value)
    await router.replace(redirect.value)
  } catch (exc) {
    if (exc instanceof ApiError && exc.code === 'INVALID_CREDENTIALS') {
      error.value = '用户名或口令不正确'
    } else {
      error.value = exc instanceof Error ? exc.message : '登录失败'
    }
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <div class="grid min-h-full place-items-center bg-shell px-6 py-12">
    <div class="w-full max-w-[352px]">
      <div class="mb-7 flex items-center justify-center gap-2.5">
        <div
          class="grid h-8 w-8 place-items-center rounded-[10px] bg-gradient-to-br from-[#3d78ff] to-[#2251d6] text-white shadow-[0_5px_14px_-4px_rgba(47,107,255,0.55)]"
        >
          <Sparkles :size="16" />
        </div>
        <span class="text-[14px] font-semibold tracking-tight">智网系统</span>
      </div>

      <form
        class="rounded-[18px] border border-line bg-surface p-6 shadow-[0_18px_50px_-30px_rgba(16,24,40,0.35)]"
        @submit.prevent="submit"
      >
        <h1 class="text-[17px] font-semibold tracking-tight">登录</h1>

        <p v-if="error" class="mt-3 text-[11.5px] text-danger">{{ error }}</p>
        <p v-if="!authEnabled" class="mt-3 text-[11.5px] text-muted">未启用登录校验，任意账号可进入</p>

        <label class="mt-5 block text-[11.5px] font-medium text-subink" for="login-username">用户名</label>
        <input
          id="login-username"
          v-model="username"
          class="mt-1.5 h-10 w-full rounded-lg border border-line bg-surface px-3 text-[13px] outline-none transition focus:border-brand/60 focus:ring-2 focus:ring-brand/15"
          autocomplete="username"
          required
        />

        <label class="mt-4 block text-[11.5px] font-medium text-subink" for="login-password">口令</label>
        <input
          id="login-password"
          v-model="password"
          type="password"
          class="mt-1.5 h-10 w-full rounded-lg border border-line bg-surface px-3 text-[13px] outline-none transition focus:border-brand/60 focus:ring-2 focus:ring-brand/15"
          autocomplete="current-password"
          required
        />

        <button
          type="submit"
          class="mt-6 flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-brand text-[13px] font-medium text-white transition hover:bg-[#2251d6] disabled:opacity-60"
          :disabled="pending"
        >
          <LoaderCircle v-if="pending" :size="15" class="animate-spin" />
          {{ pending ? '登录中' : '登录' }}
        </button>
      </form>

      <button
        class="mt-4 w-full text-center text-[11px] text-muted transition hover:text-subink"
        @click="demoOpen = !demoOpen"
      >
        演示账号
      </button>
      <div v-if="demoOpen" class="mt-2 flex flex-wrap justify-center gap-1.5">
        <button
          v-for="account in demoAccounts"
          :key="account.username"
          class="rounded-full border border-line px-2.5 py-1 text-[11px] text-subink transition hover:border-brand/40 hover:text-brand"
          @click="fill(account)"
        >
          {{ account.label }}
        </button>
      </div>
    </div>
  </div>
</template>
