<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  Activity,
  ArrowUpRight,
  Check,
  CheckCircle2,
  FileText,
  Keyboard,
  Moon,
  Settings2,
  Sun,
  UserRound,
  XCircle,
} from 'lucide-vue-next'
import { api } from '@/api/client'
import type { LearningPlan, PracticeAttemptRow, WrongBook } from '@/api/client'
import { useTheme } from '@/composables/useTheme'
import { useStudent } from '@/composables/useStudent'

const { current, currentKey } = useStudent()
const { isDark, toggle } = useTheme()
const themeLabel = computed(() => (isDark.value ? '深色' : '浅色'))

const plan = ref<LearningPlan | null>(null)
const attempts = ref<PracticeAttemptRow[]>([])
const wrongbook = ref<WrongBook | null>(null)
const sessions = ref<
  { id: string; title: string; last_run?: { question: string; status: string; created_at: string } | null }[]
>([])

async function load() {
  const key = currentKey.value
  try {
    const [p, a, w, s] = await Promise.all([
      api.get<LearningPlan>(`/learning/next?user_key=${key}&limit=3`),
      api.get<{ items: PracticeAttemptRow[] }>(`/practice/attempts?user_key=${key}&limit=30`),
      api.get<WrongBook>(`/practice/wrongbook?user_key=${key}`),
      api.get<{ items: typeof sessions.value }>(`/chat-sessions?user_key=${key}`),
    ])
    plan.value = p
    attempts.value = a.items ?? []
    wrongbook.value = w
    sessions.value = s.items ?? []
  } catch {
    plan.value = null
    attempts.value = []
    wrongbook.value = null
    sessions.value = []
  }
}

onMounted(load)
watch(currentKey, load)

const filter = ref<'all' | 'correct' | 'wrong'>('all')
const filters = [
  { key: 'all' as const, label: '全部' },
  { key: 'correct' as const, label: '答对' },
  { key: 'wrong' as const, label: '答错' },
]

const chapterTitles = computed(() => {
  const map: Record<string, string> = {}
  for (const chapter of plan.value?.chapters ?? []) map[chapter.chapter_id] = chapter.title
  return map
})

const filtered = computed(() => {
  if (filter.value === 'correct') return attempts.value.filter((a) => a.correct)
  if (filter.value === 'wrong') return attempts.value.filter((a) => !a.correct)
  return attempts.value
})

const visible = computed(() => filtered.value.slice(0, 12))

const stats = computed(() => [
  { label: '累计作答', value: attempts.value.length },
  { label: '覆盖概念', value: plan.value?.summary.covered ?? 0 },
  { label: '薄弱概念', value: plan.value?.summary.weak ?? 0 },
  { label: '待复习', value: wrongbook.value?.unresolved ?? 0 },
])

const recentSessions = computed(() => sessions.value.filter((item) => item.last_run).slice(0, 4))

function timeLabel(value: string) {
  const d = new Date(value)
  const today = new Date()
  if (d.toDateString() === today.toDateString()) {
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  }
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function exportAttempts() {
  if (!attempts.value.length) return
  const header = ['题目', '结果', '章节', '我的答案', '正确答案', '时间']
  const rows = attempts.value.map((a) => [
    a.stem,
    a.correct ? '答对' : '答错',
    chapterTitles.value[a.chapter_id] ?? a.chapter_id,
    a.answer,
    a.expected,
    a.created_at,
  ])
  const csv = [header, ...rows]
    .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    .join('\r\n')
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `${current.value.name}-练习记录.csv`
  link.click()
  URL.revokeObjectURL(link.href)
}
</script>

<template>
  <div class="animate-fade-up px-9 py-8">
    <div>
      <h1 class="text-[26px] font-semibold leading-tight tracking-[-0.025em]">我的</h1>
      <p class="mt-1.5 text-[12.5px] text-muted">
        当前身份下的练习记录与问答历史；切换学生后这里会跟着变。
      </p>
    </div>

    <div class="mt-6 grid items-start gap-4 xl:grid-cols-[296px_1fr]">
      <section class="surface p-5">
        <div class="flex items-center gap-3">
          <div
            class="grid h-14 w-14 shrink-0 place-items-center rounded-full bg-gradient-to-br from-[#3d78ff] to-[#2251d6] text-[18px] font-semibold text-white shadow-[0_8px_18px_-8px_rgba(47,107,255,0.6)]"
          >
            {{ current.initial }}
          </div>
          <div class="min-w-0">
            <p class="text-[16px] font-semibold tracking-tight">{{ current.name }}</p>
            <p class="mt-0.5 text-[11px] text-muted">{{ current.note }}</p>
          </div>
        </div>

        <div class="mt-5 flex flex-col gap-2.5 border-t border-line pt-4">
          <div class="flex items-start justify-between gap-3 text-[11.5px]">
            <span class="shrink-0 text-muted">课程</span>
            <span class="text-right text-subink">计算机网络</span>
          </div>
          <div class="flex items-start justify-between gap-3 text-[11.5px]">
            <span class="shrink-0 text-muted">正确率</span>
            <span class="text-right text-subink">{{ plan?.summary.accuracy ?? 0 }}%</span>
          </div>
          <div class="flex items-start justify-between gap-3 text-[11.5px]">
            <span class="shrink-0 text-muted">身份</span>
            <span class="text-right font-mono text-subink">{{ currentKey }}</span>
          </div>
        </div>

        <div class="mt-4 grid grid-cols-2 gap-2">
          <div v-for="a in stats" :key="a.label" class="rounded-xl bg-tint-soft px-3 py-2.5">
            <div class="text-[9.5px] text-muted">{{ a.label }}</div>
            <div class="mt-1 text-[18px] font-semibold leading-none">{{ a.value }}</div>
          </div>
        </div>

        <p class="mt-4 text-[10px] leading-relaxed text-muted">
          演示用本地身份，未接入统一认证；身份在顶栏切换。
        </p>
      </section>

      <div class="flex flex-col gap-4">
        <section class="surface overflow-hidden">
          <header class="flex flex-wrap items-center justify-between gap-2 border-b border-line px-5 py-3.5">
            <div class="flex items-center gap-2">
              <FileText :size="14" class="text-muted" />
              <h2 class="text-[12.5px] font-medium">练习记录</h2>
              <span class="rounded-md bg-tint px-1.5 py-0.5 text-[10px] text-muted">{{ attempts.length }}</span>
              <span v-if="filtered.length > visible.length" class="text-[9.5px] text-muted">
                显示前 {{ visible.length }} 条
              </span>
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

          <div class="hidden grid-cols-[1fr_64px_88px_72px] gap-3 border-b border-line px-5 py-2 text-[9.5px] text-muted md:grid">
            <span>题目</span>
            <span>结果</span>
            <span>章节</span>
            <span>时间</span>
          </div>

          <ul v-if="visible.length">
            <li
              v-for="a in visible"
              :key="a.attempt_id"
              class="grid grid-cols-1 items-center gap-2 border-b border-line px-5 py-3 transition-colors last:border-b-0 hover:bg-tint-soft md:grid-cols-[1fr_64px_88px_72px] md:gap-3"
            >
              <div class="min-w-0">
                <p class="truncate text-[12px] text-subink">{{ a.stem }}</p>
                <p class="mt-0.5 text-[9.5px] text-muted">我的答案 {{ a.answer }} · 正确答案 {{ a.expected }}</p>
              </div>
              <span class="flex items-center gap-1 text-[10px]" :class="a.correct ? 'text-success' : 'text-warn'">
                <CheckCircle2 v-if="a.correct" :size="11" />
                <XCircle v-else :size="11" />
                {{ a.correct ? '答对' : '答错' }}
              </span>
              <span class="truncate text-[10px] text-muted">{{ chapterTitles[a.chapter_id] ?? a.chapter_id }}</span>
              <span class="font-mono text-[9.5px] text-muted">{{ timeLabel(a.created_at) }}</span>
            </li>
          </ul>
          <div v-else class="px-5 py-8 text-center text-[11px] text-muted">
            当前筛选下没有记录
          </div>
        </section>

        <div class="grid gap-4 lg:grid-cols-2">
          <section class="surface overflow-hidden">
            <header class="flex items-center justify-between border-b border-line px-4 py-3">
              <div class="flex items-center gap-2">
                <Activity :size="13" class="text-muted" />
                <h2 class="text-[11.5px] font-medium">最近问答</h2>
              </div>
              <span class="text-[9.5px] text-muted">{{ recentSessions.length }} 个会话</span>
            </header>
            <ul v-if="recentSessions.length" class="p-2">
              <li
                v-for="s in recentSessions"
                :key="s.id"
                class="flex items-start gap-2.5 rounded-lg px-2.5 py-2 transition-colors hover:bg-tint-soft"
              >
                <span class="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-brand/70" />
                <div class="min-w-0 flex-1">
                  <p class="truncate text-[11px] text-subink">{{ s.title }}</p>
                  <p class="mt-0.5 truncate text-[9.5px] text-muted">{{ s.last_run?.question }}</p>
                </div>
                <span class="shrink-0 font-mono text-[9px] text-muted">
                  {{ s.last_run ? timeLabel(s.last_run.created_at) : '' }}
                </span>
              </li>
            </ul>
            <div v-else class="px-4 py-6 text-center text-[10.5px] text-muted">还没有问答记录</div>
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
          <button class="flex items-center gap-1 text-brand hover:underline" @click="exportAttempts">
            导出练习记录
            <ArrowUpRight :size="10" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
