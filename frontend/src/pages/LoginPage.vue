<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, KeyRound, LoaderCircle, Sparkles } from 'lucide-vue-next'
import { ApiError } from '@/api/client'
import { useAuth } from '@/composables/useAuth'

const router = useRouter()
const route = useRoute()
const { login, authEnabled } = useAuth()

const username = ref('')
const password = ref('')
const pending = ref(false)
const error = ref('')

/** 本地演示用的四组账号，口令与 backend/.env 的 AUTH_ACCOUNTS 对应。 */
const demoAccounts = [
  { label: '教师', username: 'teacher', password: 'teacher2026', note: '可看全班、可切学生' },
  { label: '李金阳', username: 'demo_user', password: 'demo2026', note: '主学生账号' },
  { label: '林晓', username: 'stu_lin', password: 'lin2026', note: '基础偏弱' },
  { label: '赵一鸣', username: 'stu_zhao', password: 'zhao2026', note: '基础较好' },
]

const redirect = computed(() => {
  const value = route.query.redirect
  return typeof value === 'string' && value.startsWith('/') ? value : '/'
})

function fill(account: (typeof demoAccounts)[number]) {
  username.value = account.username
  password.value = account.password
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
      error.value = '账号或口令不对，检查一下再试'
    } else {
      error.value = exc instanceof Error ? exc.message : '登录失败，请稍后重试'
    }
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <div class="grid min-h-full place-items-center bg-shell px-6 py-10">
    <div class="w-full max-w-[860px] overflow-hidden rounded-[22px] border border-line bg-surface shadow-[0_24px_70px_-30px_rgba(16,24,40,0.35)]">
      <div class="grid md:grid-cols-[1.05fr_1fr]">
        <!-- 左侧：身份与用途说明 -->
        <div class="flex flex-col justify-between gap-8 bg-gradient-to-br from-brand-soft to-shell p-8">
          <div>
            <div class="flex items-center gap-2.5">
              <div
                class="grid h-8 w-8 place-items-center rounded-[10px] bg-gradient-to-br from-[#3d78ff] to-[#2251d6] text-white shadow-[0_5px_14px_-4px_rgba(47,107,255,0.55)]"
              >
                <Sparkles :size="16" />
              </div>
              <div class="leading-tight">
                <div class="text-[13px] font-semibold tracking-tight">CNRAG</div>
                <div class="text-[11px] text-muted">智能助教工作台</div>
              </div>
            </div>
            <h1 class="mt-8 text-[22px] font-semibold leading-snug tracking-tight text-ink">
              先确认身份，<br />再进入你的学习工作台
            </h1>
            <p class="mt-3 max-w-[300px] text-[12.5px] leading-relaxed text-subink">
              教师可以查看全班学情并切换学生；学生只看到自己的练习、错题与会话记录。
            </p>
          </div>
          <div class="text-[11px] leading-relaxed text-muted">
            账号由部署方在服务端配置，浏览器只保存登录票据，不保存口令。
          </div>
        </div>

        <!-- 右侧：登录表单 -->
        <form class="flex flex-col gap-4 p-8" @submit.prevent="submit">
          <div>
            <p class="text-[12px] font-medium text-subink">用户名</p>
            <input
              v-model="username"
              class="mt-1.5 h-10 w-full rounded-xl border border-line bg-surface px-3 text-[13px] outline-none transition focus:border-brand/60 focus:ring-2 focus:ring-brand/15"
              autocomplete="username"
              placeholder="teacher / demo_user"
              required
            />
          </div>
          <div>
            <p class="text-[12px] font-medium text-subink">口令</p>
            <div class="relative mt-1.5">
              <KeyRound :size="14" class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
              <input
                v-model="password"
                type="password"
                class="h-10 w-full rounded-xl border border-line bg-surface pl-9 pr-3 text-[13px] outline-none transition focus:border-brand/60 focus:ring-2 focus:ring-brand/15"
                autocomplete="current-password"
                placeholder="输入口令"
                required
              />
            </div>
          </div>

          <p v-if="error" class="rounded-lg bg-danger/10 px-3 py-2 text-[11.5px] text-danger">{{ error }}</p>
          <p v-if="!authEnabled" class="rounded-lg bg-tint px-3 py-2 text-[11.5px] text-muted">
            当前后端关闭了鉴权（AUTH_ENABLED=false），直接进入即可。
          </p>

          <button
            type="submit"
            class="mt-1 flex h-10 items-center justify-center gap-2 rounded-xl bg-brand text-[13px] font-medium text-white transition hover:bg-[#2251d6] disabled:opacity-60"
            :disabled="pending"
          >
            <LoaderCircle v-if="pending" :size="15" class="animate-spin" />
            <span>{{ pending ? '正在验证…' : '进入工作台' }}</span>
            <ArrowRight v-if="!pending" :size="15" />
          </button>

          <div class="mt-2 border-t border-line pt-3">
            <p class="text-[10.5px] tracking-[0.04em] text-muted">演示账号 · 点一下自动填入</p>
            <div class="mt-2 grid grid-cols-2 gap-1.5">
              <button
                v-for="account in demoAccounts"
                :key="account.username"
                type="button"
                class="rounded-lg border border-line px-2.5 py-2 text-left transition hover:border-brand/40 hover:bg-brand-soft"
                @click="fill(account)"
              >
                <p class="text-[11.5px] font-medium text-ink">{{ account.label }}</p>
                <p class="mt-0.5 text-[10px] text-muted">{{ account.note }}</p>
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
