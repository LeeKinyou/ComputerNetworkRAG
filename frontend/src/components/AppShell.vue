<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import {
  BarChart3,
  BookOpen,
  Bot,
  HelpCircle,
  LayoutDashboard,
  Moon,
  PenLine,
  Route,
  Search,
  Sparkles,
  Sun,
  TrendingUp,
  UserRound,
  Waypoints,
} from 'lucide-vue-next'
import { useTheme } from '@/composables/useTheme'

const route = useRoute()
const { isDark, toggle } = useTheme()

const navGroups = [
  {
    title: '',
    items: [
      { to: '/', label: '工作台', icon: LayoutDashboard },
      { to: '/chat', label: '智能问答', icon: Bot },
      { to: '/practice', label: '练习中心', icon: PenLine },
      { to: '/graph', label: '知识图谱', icon: Waypoints },
      { to: '/path', label: '学习计划', icon: Route },
      { to: '/documents', label: '知识库', icon: BookOpen },
      { to: '/progress', label: '学习报告', icon: TrendingUp },
      { to: '/profile', label: '我的', icon: UserRound },
    ],
  },
  {
    title: '教师视图',
    items: [{ to: '/insights', label: '学情分析', icon: BarChart3 }],
  },
]

const labels: Record<string, string> = {
  overview: '工作台',
  chat: '智能问答',
  practice: '练习中心',
  graph: '知识图谱',
  path: '学习计划',
  documents: '知识库',
  progress: '学习报告',
  insights: '学情分析',
  profile: '我的',
}

const currentLabel = computed(() => labels[String(route.name)] ?? '工作台')
const isActive = (to: string) => (to === '/' ? route.path === '/' : route.path.startsWith(to))
</script>

<template>
  <div class="flex h-full min-h-0">
    <aside class="hidden w-[236px] shrink-0 flex-col border-r border-line bg-shell lg:flex">
      <div class="flex h-14 items-center gap-2.5 px-4">
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

      <nav class="flex flex-col gap-0.5 p-2.5">
        <template v-for="(group, gi) in navGroups" :key="gi">
          <div v-if="group.title" class="mt-2 border-t border-line px-1 pb-1 pt-3">
            <p class="px-2 text-[9px] tracking-[0.08em] text-muted">{{ group.title }}</p>
          </div>
          <RouterLink
            v-for="item in group.items"
            :key="item.to"
            :to="item.to"
            class="flex items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] transition-all duration-200"
            :class="
              isActive(item.to)
                ? 'bg-surface font-medium text-ink shadow-[0_1px_2px_rgba(16,24,40,0.04)]'
                : 'text-subink/85 hover:bg-tint hover:text-ink'
            "
          >
            <component
              :is="item.icon"
              :size="16"
              :stroke-width="1.8"
              :class="isActive(item.to) ? 'text-brand' : ''"
            />
            {{ item.label }}
          </RouterLink>
        </template>
      </nav>

      <div class="mt-auto p-3">
        <div class="rounded-2xl border border-line bg-surface/70 p-3 backdrop-blur">
          <div class="flex items-center gap-1.5 text-[11px] font-medium text-subink">
            <span class="h-1.5 w-1.5 rounded-full bg-success" />
            lite 模式 · 单进程
          </div>
          <p class="mt-1.5 text-[11px] leading-relaxed text-muted">
            SQLite + 本地索引，无需外部中间件
          </p>
        </div>
      </div>
    </aside>

    <main class="flex min-w-0 flex-1 flex-col">
      <header
        class="flex h-14 shrink-0 items-center justify-between border-b border-line bg-surface/65 px-6 backdrop-blur-xl"
      >
        <div class="flex items-center gap-2 text-[12.5px] text-muted">
          <span>计算机网络</span>
          <span class="text-line-strong">/</span>
          <span class="font-medium text-ink">{{ currentLabel }}</span>
        </div>

        <div class="flex items-center gap-1.5">
          <button
            class="flex h-8 items-center gap-2 rounded-full bg-tint px-3 text-[12px] text-muted transition-colors hover:bg-tint-strong hover:text-subink"
          >
            <Search :size="13.5" />
            <span class="hidden sm:inline">搜索知识点</span>
            <kbd class="hidden rounded-md bg-surface px-1.5 py-0.5 text-[10px] text-muted sm:inline">Ctrl K</kbd>
          </button>
          <button class="icon-btn" :aria-label="isDark ? '切换到浅色模式' : '切换到深色模式'" @click="toggle">
            <Sun v-if="isDark" :size="16" />
            <Moon v-else :size="16" />
          </button>
          <button class="icon-btn"><HelpCircle :size="16" /></button>
          <RouterLink
            to="/profile"
            class="ml-1 grid h-7 w-7 place-items-center rounded-full bg-brand-soft text-[11px] font-semibold text-brand transition-transform hover:scale-105"
          >
            李
          </RouterLink>
        </div>
      </header>

      <div class="min-h-0 flex-1 overflow-y-auto">
        <slot />
      </div>
    </main>
  </div>
</template>
