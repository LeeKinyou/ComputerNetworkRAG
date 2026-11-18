<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  Activity,
  ArrowUpRight,
  Check,
  Download,
  FileText,
  Keyboard,
  Moon,
  Pencil,
  Settings2,
  Sun,
  UserRound,
} from 'lucide-vue-next'
import { activities, profile } from '@/mock/data'
import { artifactLabel, profileAssets, recentArtifacts } from '@/mock/workbench'
import { useTheme } from '@/composables/useTheme'

const { isDark, toggle } = useTheme()
const themeLabel = computed(() => (isDark.value ? '深色' : '浅色'))

const filter = ref<'all' | 'note' | 'quiz' | 'calc'>('all')
const filters = [
  { key: 'all' as const, label: '全部' },
  { key: 'calc' as const, label: '计算卡' },
  { key: 'note' as const, label: '笔记' },
  { key: 'quiz' as const, label: '练习' },
]

const assets = [
  ...recentArtifacts,
  {
    id: 'art_05',
    kind: 'quiz' as const,
    title: '子网划分练习（5 题）',
    summary: '含答案与解析，覆盖 /26–/29 与路由聚合',
    taskId: 'task_05',
    createdAt: '昨天',
  },
  {
    id: 'art_06',
    kind: 'note' as const,
    title: '三次握手与四次挥手对比',
    summary: '按状态迁移整理的课堂笔记',
    taskId: 'task_02',
    createdAt: '11-16',
  },
]

const visible = computed(() =>
  filter.value === 'all' ? assets : assets.filter((a) => a.kind === filter.value),
)
</script>

<template>
  <div class="animate-fade-up px-9 py-8">
    <div>
      <h1 class="text-[26px] font-semibold leading-tight tracking-[-0.025em]">我的</h1>
      <p class="mt-1.5 text-[12.5px] text-muted">你的产物、笔记和练习都存在这里，可以随时带走。</p>
    </div>

    <div class="mt-6 grid items-start gap-4 xl:grid-cols-[296px_1fr]">
      <section class="surface p-5">
        <div class="flex items-center gap-3">
          <div
            class="grid h-14 w-14 shrink-0 place-items-center rounded-full bg-gradient-to-br from-[#3d78ff] to-[#2251d6] text-[18px] font-semibold text-white shadow-[0_8px_18px_-8px_rgba(47,107,255,0.6)]"
          >
            {{ profile.initials }}
          </div>
          <div class="min-w-0">
            <p class="text-[16px] font-semibold tracking-tight">{{ profile.name }}</p>
            <p class="mt-0.5 text-[11px] text-muted">{{ profile.role }}</p>
          </div>
        </div>

        <div class="mt-5 flex flex-col gap-2.5 border-t border-line pt-4">
          <div class="flex items-start justify-between gap-3 text-[11.5px]">
            <span class="shrink-0 text-muted">学校</span>
            <span class="text-right text-subink">{{ profile.school }}</span>
          </div>
          <div class="flex items-start justify-between gap-3 text-[11.5px]">
            <span class="shrink-0 text-muted">专业</span>
            <span class="text-right text-subink">{{ profile.major }}</span>
          </div>
          <div class="flex items-start justify-between gap-3 text-[11.5px]">
            <span class="shrink-0 text-muted">加入</span>
            <span class="text-right font-mono text-subink">{{ profile.joined }}</span>
          </div>
        </div>

        <div class="mt-4 grid grid-cols-2 gap-2">
          <div v-for="a in profileAssets" :key="a.label" class="rounded-xl bg-tint-soft px-3 py-2.5">
            <div class="text-[9.5px] text-muted">{{ a.label }}</div>
            <div class="mt-1 text-[18px] font-semibold leading-none">{{ a.value }}</div>
          </div>
        </div>

        <button
          class="pill-btn mt-4 h-9 w-full justify-center border border-line bg-surface text-subink hover:border-line-strong hover:text-ink"
        >
          <Pencil :size="13" />
          编辑资料
        </button>
      </section>

      <div class="flex flex-col gap-4">
        <section class="surface overflow-hidden">
          <header class="flex flex-wrap items-center justify-between gap-2 border-b border-line px-5 py-3.5">
            <div class="flex items-center gap-2">
              <FileText :size="14" class="text-muted" />
              <h2 class="text-[12.5px] font-medium">我的产物</h2>
              <span class="rounded-md bg-tint px-1.5 py-0.5 text-[10px] text-muted">{{ assets.length }}</span>
            </div>
            <div class="flex items-center gap-0.5 rounded-full bg-tint p-0.5">
              <button
                v-for="f in filters"
                :key="f.key"
                class="rounded-full px-2 py-1 text-[9.5px] transition-colors"
                :class="filter === f.key ? 'bg-surface text-ink shadow-sm' : 'text-muted'"
                @click="filter = f.key"
              >
                {{ f.label }}
              </button>
            </div>
          </header>

          <div class="hidden grid-cols-[1fr_88px_96px_72px_40px] gap-3 border-b border-line px-5 py-2 text-[9.5px] text-muted md:grid">
            <span>产物</span>
            <span>类型</span>
            <span>来源任务</span>
            <span>时间</span>
            <span />
          </div>

          <ul>
            <li
              v-for="a in visible"
              :key="a.id"
              class="grid grid-cols-1 items-center gap-2 border-b border-line px-5 py-3 transition-colors last:border-b-0 hover:bg-tint-soft md:grid-cols-[1fr_88px_96px_72px_40px] md:gap-3"
            >
              <div class="min-w-0">
                <p class="truncate text-[12px] text-subink">{{ a.title }}</p>
                <p class="mt-0.5 line-clamp-1 text-[9.5px] text-muted">{{ a.summary }}</p>
              </div>
              <span class="hidden text-[10px] text-muted md:block">{{ artifactLabel[a.kind] }}</span>
              <span class="hidden truncate font-mono text-[9.5px] text-muted md:block">{{ a.taskId }}</span>
              <span class="hidden font-mono text-[9.5px] text-muted md:block">{{ a.createdAt }}</span>
              <button class="icon-btn hidden md:inline-flex" aria-label="导出" :disabled="a.kind === 'quiz'">
                <Download :size="13" />
              </button>
            </li>
          </ul>
        </section>

        <div class="grid gap-4 lg:grid-cols-2">
          <section class="surface overflow-hidden">
            <header class="flex items-center justify-between border-b border-line px-4 py-3">
              <div class="flex items-center gap-2">
                <Activity :size="13" class="text-muted" />
                <h2 class="text-[11.5px] font-medium">最近活动</h2>
              </div>
              <span class="text-[9.5px] text-muted">近 7 天</span>
            </header>
            <ul class="p-2">
              <li
                v-for="a in activities"
                :key="a.title"
                class="flex items-start gap-2.5 rounded-lg px-2.5 py-2 transition-colors hover:bg-tint-soft"
              >
                <span class="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-brand/70" />
                <div class="min-w-0 flex-1">
                  <p class="truncate text-[11px] text-subink">{{ a.title }}</p>
                  <p class="mt-0.5 text-[9.5px] text-muted">{{ a.detail }}</p>
                </div>
                <span class="shrink-0 font-mono text-[9px] text-muted">{{ a.time }}</span>
              </li>
            </ul>
          </section>

          <section class="surface p-4">
            <div class="flex items-center gap-2">
              <Settings2 :size="13" class="text-muted" />
              <h2 class="text-[11.5px] font-medium">偏好</h2>
            </div>

            <div class="mt-3 flex flex-col divide-y divide-line">
              <div class="flex items-center justify-between py-2.5">
                <div>
                  <p class="text-[11px] text-subink">主题</p>
                  <p class="mt-0.5 text-[9.5px] text-muted">当前{{ themeLabel }}模式</p>
                </div>
                <button
                  class="pill-btn h-8 border border-line bg-surface px-2.5 text-[10px] text-subink hover:border-line-strong"
                  @click="toggle"
                >
                  <Sun v-if="isDark" :size="12" />
                  <Moon v-else :size="12" />
                  切换
                </button>
              </div>

              <div class="flex items-center justify-between py-2.5">
                <div>
                  <p class="text-[11px] text-subink">检索条数</p>
                  <p class="mt-0.5 text-[9.5px] text-muted">影响问答的召回窗口</p>
                </div>
                <span class="rounded-full bg-tint px-2 py-0.5 font-mono text-[10px] text-subink">Top-5</span>
              </div>

              <div class="flex items-center justify-between py-2.5">
                <div>
                  <p class="flex items-center gap-1.5 text-[11px] text-subink">
                    <Keyboard :size="11" class="text-muted" />
                    搜索快捷键
                  </p>
                  <p class="mt-0.5 text-[9.5px] text-muted">Windows 使用 Ctrl</p>
                </div>
                <kbd class="rounded-md border border-line bg-tint px-1.5 py-0.5 font-mono text-[9.5px] text-subink">
                  Ctrl K
                </kbd>
              </div>

              <div class="flex items-center justify-between py-2.5">
                <div>
                  <p class="text-[11px] text-subink">回答自动关联原文</p>
                  <p class="mt-0.5 text-[9.5px] text-muted">在回答下方展示引用</p>
                </div>
                <span class="flex items-center gap-1 rounded-full bg-success/12 px-2 py-0.5 text-[9px] text-success">
                  <Check :size="9" />
                  已开启
                </span>
              </div>
            </div>
          </section>
        </div>

        <div class="flex items-center justify-between text-[9.5px] text-muted">
          <span class="flex items-center gap-1.5">
            <UserRound :size="11" />
            本地演示账号，未接入统一身份认证
          </span>
          <button class="flex items-center gap-1 text-brand hover:underline">
            导出全部产物
            <ArrowUpRight :size="10" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
