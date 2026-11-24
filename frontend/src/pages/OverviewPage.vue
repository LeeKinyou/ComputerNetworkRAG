<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  ArrowRight,
  BookMarked,
  BookOpen,
  CheckCircle2,
  ClipboardList,
  Clock3,
  Flame,
  PenLine,
  PlayCircle,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  XCircle,
} from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { api } from '@/api/client'
import type {
  AnalyticsConcept,
  AnalyticsOverview,
  LearningPlan,
  LearningTask,
  PendingRun,
  PracticeAttemptRow,
  WrongBook,
} from '@/api/client'
import { useStudent } from '@/composables/useStudent'
import { useAuth } from '@/composables/useAuth'

const { currentKey, current } = useStudent()
const { user } = useAuth()
const isTeacher = computed(() => user.value?.role === 'teacher')

const plan = ref<LearningPlan | null>(null)
const concepts = ref<AnalyticsConcept[]>([])
const attempts = ref<PracticeAttemptRow[]>([])
const overview = ref<AnalyticsOverview | null>(null)
const wrongbook = ref<WrongBook | null>(null)
const classCovered = ref(0)
const classTotal = ref(0)
const pendingRuns = ref<PendingRun[]>([])
const deciding = ref('')
const decisionError = ref('')

async function load() {
  const key = currentKey.value
  try {
    const [p, c, a, o, w, cc, pr] = await Promise.all([
      api.get<LearningPlan>(`/learning/next?user_key=${key}&limit=3`),
      api.get<{ items: AnalyticsConcept[] }>(`/analytics/concepts?user_key=${key}`),
      api.get<{ items: PracticeAttemptRow[] }>(`/practice/attempts?user_key=${key}&limit=20`),
      api.get<AnalyticsOverview>('/analytics/overview'),
      api.get<WrongBook>(`/practice/wrongbook?user_key=${key}`),
      api.get<{ covered_concepts: number; total_concepts: number }>('/analytics/concepts'),
      api.get<{ items: PendingRun[] }>(`/runs/pending?user_key=${key}`),
    ])
    plan.value = p
    concepts.value = c.items ?? []
    attempts.value = a.items ?? []
    overview.value = o
    wrongbook.value = w
    classCovered.value = cc.covered_concepts ?? 0
    classTotal.value = cc.total_concepts ?? 0
    pendingRuns.value = pr.items ?? []
  } catch {
    plan.value = null
    concepts.value = []
    attempts.value = []
    overview.value = null
    wrongbook.value = null
    pendingRuns.value = []
  }
}

onMounted(load)
watch(currentKey, load)

const hour = new Date().getHours()
const greeting = computed(() => (hour < 6 ? '夜深了' : hour < 12 ? '早上好' : hour < 18 ? '下午好' : '晚上好'))

const tasks = computed(() => plan.value?.tasks ?? [])
const mainTask = computed(() => tasks.value[0] ?? null)
const totalMinutes = computed(() => tasks.value.reduce((sum, task) => sum + task.minutes, 0))

const headline = computed(() =>
  mainTask.value ? `今天先把「${mainTask.value.title}」补上` : '今天没有待补的知识点',
)
const subline = computed(() => {
  if (!tasks.value.length) {
    return `当前覆盖 ${plan.value?.summary.covered ?? 0}/${plan.value?.summary.total ?? 0} 个知识点`
    }
  return `${tasks.value.length} 项任务，约 ${totalMinutes.value} 分钟`
})

const taskIcon = { learn: BookOpen, review: RefreshCw, practice: PenLine, submit: ClipboardList }
const taskTone: Record<string, string> = {
  learn: 'bg-brand-soft text-brand',
  review: 'bg-warn/12 text-warn',
  practice: 'bg-success/12 text-success',
  submit: 'bg-brand-soft text-brand',
}
const taskPath = (task: LearningTask) =>
  task.kind === 'assignment'
    ? { path: '/assignments', query: task.assignment_id ? { focus: task.assignment_id } : {} }
    : { path: '/practice', query: task.concept_id ? { concept: task.concept_id } : {} }

/** 当前最需要收尾的一章：有知识点且正确率最低 */
const focusChapter = computed(() => {
  const rows = (plan.value?.chapters ?? []).filter((row) => row.concepts > 0)
  if (!rows.length) return null
  return [...rows].sort((a, b) => a.rate - b.rate)[0]
})

const focusConcepts = computed(() => {
  if (!focusChapter.value) return []
  const order: Record<string, number> = { weak: 0, normal: 1, no_data: 2, mastered: 3 }
  return concepts.value
    .filter((item) => item.chapter_id === focusChapter.value?.chapter_id)
    .sort((a, b) => (order[a.state] ?? 4) - (order[b.state] ?? 4) || a.rate - b.rate)
    .slice(0, 3)
})

const stateLabel: Record<string, string> = {
  weak: '薄弱',
  normal: '一般',
  no_data: '未练',
  mastered: '已掌握',
}

const rhythm = computed(() => {
  const DAY = 86400000
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const counts = new Map<string, number>()
  for (const attempt of attempts.value) {
    const d = new Date(attempt.created_at)
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }
  const labels = ['日', '一', '二', '三', '四', '五', '六']
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(today.getTime() - (6 - i) * DAY)
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
    return { day: labels[d.getDay()], value: counts.get(key) ?? 0 }
  })
})

const rhythmMax = computed(() => Math.max(...rhythm.value.map((item) => item.value), 1))
const rhythmTotal = computed(() => rhythm.value.reduce((sum, item) => sum + item.value, 0))

const mainPending = computed(() => pendingRuns.value[0] ?? null)
const pendingCount = computed(() => pendingRuns.value.length)

async function decide(run: PendingRun, approved: boolean) {
  const input = run.pending_input
  if (!input) return
  deciding.value = run.run_id
  decisionError.value = ''
  try {
    await api.post(`/runs/${run.run_id}/inputs?user_key=${currentKey.value}`, {
      input_id: input.input_id,
      approved,
    })
    await load()
  } catch {
    decisionError.value = '提交失败：可能已被处理，去问答页看一下运行状态。'
  } finally {
    deciding.value = ''
  }
}
const wrongCount = computed(() => wrongbook.value?.unresolved ?? 0)
const wrongConcepts = computed(() => {
  const ids = new Set<string>()
  for (const item of wrongbook.value?.items ?? []) {
    if (item.concept_id) ids.add(item.concept_id)
  }
  return Array.from(ids).slice(0, 4)
})

const recentAttempts = computed(() => attempts.value.slice(0, 5))

const hotQuestion = computed(() => overview.value?.hot_questions?.[0] ?? null)

function timeLabel(value: string) {
  const d = new Date(value)
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(
    d.getHours(),
  ).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
</script>

<template>
  <div class="animate-fade-up page">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p class="text-[11.5px] text-muted">
          {{ greeting }}，{{ current.name }} · 计算机网络
        </p>
        <h1 class="mt-1 text-[22px] font-semibold leading-tight tracking-[-0.025em] sm:text-[26px]">
          {{ headline }}
        </h1>
        <p class="mt-1.5 text-[12.5px] text-muted">{{ subline }}</p>
      </div>
      <div class="flex w-full flex-wrap items-center gap-2 sm:w-auto">
        <RouterLink
          to="/path"
          class="pill-btn h-9 flex-1 justify-center border border-line bg-surface text-subink hover:border-line-strong hover:text-ink sm:flex-none"
        >
          调整计划
        </RouterLink>
        <RouterLink
          :to="mainTask ? taskPath(mainTask) : '/assignments'"
          class="pill-btn h-9 flex-1 justify-center bg-ink pl-3.5 text-canvas shadow-[0_6px_16px_-8px_rgba(17,19,24,0.55)] hover:opacity-90 sm:flex-none"
        >
          <PlayCircle :size="15" />
          开始今天的学习
        </RouterLink>
      </div>
    </div>

    <div class="mt-6 grid grid-cols-[minmax(0,1fr)] items-start gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
      <div class="flex flex-col gap-4">
        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-4 py-3 sm:px-5 sm:py-3.5">
            <h2 class="text-[12.5px] font-medium">今日任务</h2>
            <span class="text-[10.5px] text-muted">{{ tasks.length }} 项 · {{ totalMinutes }} 分钟</span>
          </header>
          <ul v-if="tasks.length" class="p-2">
            <li v-for="(t, i) in tasks" :key="`${t.concept_id ?? t.assignment_id ?? 'task'}-${i}`">
              <RouterLink
                :to="taskPath(t)"
                class="group flex items-center gap-3.5 rounded-xl px-3 py-3 transition-colors"
                :class="i === 0 ? 'bg-brand-soft/60' : 'hover:bg-tint-soft'"
              >
                <span
                  class="grid h-9 w-9 shrink-0 place-items-center rounded-[11px]"
                  :class="taskTone[t.action]"
                >
                  <component :is="taskIcon[t.action]" :size="16" />
                </span>
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <p class="truncate text-[13px] font-medium text-ink">{{ t.title }}</p>
                    <span
                      v-if="i === 0"
                      class="shrink-0 rounded-full bg-surface px-2 py-0.5 text-[9.5px] text-brand"
                    >
                      当前
                    </span>
                  </div>
                  <p class="mt-0.5 truncate text-[10.5px] text-muted">{{ t.reason }}</p>
                </div>
                <span class="hidden shrink-0 items-center gap-1 text-[10.5px] text-muted sm:flex">
                  <Clock3 :size="11" />
                  {{ t.minutes }} 分钟
                </span>
                <ArrowRight
                  :size="14"
                  class="shrink-0 text-muted transition-transform group-hover:translate-x-0.5"
                />
              </RouterLink>
            </li>
          </ul>
          <div v-else class="px-5 py-8 text-center">
            <p class="text-[11.5px] text-muted">没有待补的知识点，去练习中心继续往后推。</p>
            <RouterLink
              to="/practice"
              class="pill-btn mt-3 h-8 bg-ink px-3 text-[10.5px] text-canvas hover:opacity-90"
            >
              去练习
              <ArrowRight :size="11" />
            </RouterLink>
          </div>
        </section>

        <section v-if="focusChapter" class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-4 py-3 sm:px-5 sm:py-3.5">
            <div class="flex items-center gap-2">
              <BookOpen :size="14" class="text-muted" />
              <h2 class="text-[12.5px] font-medium">继续学习</h2>
            </div>
            <span class="rounded-full bg-tint px-2 py-0.5 text-[10px] text-muted">
              {{ focusChapter.covered }}/{{ focusChapter.concepts }} 概念已练
            </span>
          </header>
          <div class="p-5">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 class="text-[17px] font-semibold tracking-tight">{{ focusChapter.title }}</h3>
              </div>
              <span class="font-mono text-[11px]" :class="focusChapter.rate < 60 ? 'text-warn' : 'text-muted'">
                {{ focusChapter.rate }}%
              </span>
            </div>

            <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-tint">
              <div
                class="h-full rounded-full"
                :class="focusChapter.rate >= 80 ? 'bg-success' : focusChapter.rate >= 60 ? 'bg-brand' : 'bg-warn'"
                :style="{ width: focusChapter.rate + '%' }"
              />
            </div>

            <div class="mt-3 flex flex-wrap gap-1.5">
              <span
                v-for="c in focusConcepts"
                :key="c.concept_id"
                class="rounded-full border px-2.5 py-1 text-[10.5px]"
                :class="
                  c.state === 'weak'
                    ? 'border-warn/30 bg-warn/12 text-warn'
                    : c.state === 'mastered'
                      ? 'border-line bg-tint-soft text-subink'
                      : 'border-line bg-tint-soft text-muted'
                "
              >
                {{ c.title }} · {{ stateLabel[c.state] }}
              </span>
            </div>

            <RouterLink
              :to="{ path: '/practice', query: { chapter: focusChapter.chapter_id } }"
              class="pill-btn mt-4 h-9 bg-ink px-4 text-canvas hover:opacity-90"
            >
              继续这一章
              <ArrowRight :size="14" />
            </RouterLink>
          </div>
        </section>

        <section class="surface px-5 py-4">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <Flame :size="14" class="text-muted" />
              <h2 class="text-[12.5px] font-medium">本周节奏</h2>
            </div>
            <span class="text-[10.5px] text-muted">{{ rhythmTotal }} 次练习 · 近 7 天</span>
          </div>
          <div class="mt-4 flex items-end gap-2">
            <div v-for="(d, i) in rhythm" :key="i" class="flex flex-1 flex-col items-center gap-1.5">
              <span class="font-mono text-[8.5px] text-muted">{{ d.value || '' }}</span>
              <div class="flex h-14 w-full items-end">
                <div
                  class="w-full rounded-[5px]"
                  :class="d.value ? 'bg-brand/35' : 'bg-tint'"
                  :style="{ height: Math.max((d.value / rhythmMax) * 100, d.value ? 10 : 3) + '%' }"
                />
              </div>
              <span class="text-[9.5px] text-muted">{{ d.day }}</span>
            </div>
          </div>
        </section>
      </div>

      <div class="flex flex-col gap-4">
        <section v-if="mainPending" class="surface border-warn/35 overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-4 py-3">
            <div class="flex items-center gap-1.5 text-[11.5px] text-warn">
              <ShieldCheck :size="13" />
              待你确认
            </div>
            <span class="text-[9.5px] text-muted">{{ pendingCount }} 条</span>
          </header>
          <div class="p-4">
            <p class="line-clamp-2 text-[12.5px] font-medium text-ink">{{ mainPending.question }}</p>
            <p class="mt-1 text-[10.5px] leading-relaxed text-muted">
              {{ mainPending.pending_input?.prompt ?? '该操作会修改课程内容，需要你确认。' }}
            </p>
            <p class="mt-1.5 text-[9.5px] text-muted">
              {{ mainPending.session_title || '未命名会话' }} · {{ timeLabel(mainPending.created_at) }}
            </p>
            <div class="mt-3 flex gap-2">
              <button
                class="pill-btn h-8 flex-1 justify-center bg-ink text-[11px] text-canvas hover:opacity-90 disabled:opacity-50"
                :disabled="deciding === mainPending.run_id"
                @click="decide(mainPending, true)"
              >
                {{ deciding === mainPending.run_id ? '提交中…' : '批准并继续' }}
              </button>
              <button
                class="pill-btn h-8 border border-line bg-surface text-[11px] text-muted hover:border-line-strong disabled:opacity-50"
                :disabled="deciding === mainPending.run_id"
                @click="decide(mainPending, false)"
              >
                取消操作
              </button>
            </div>
            <p v-if="decisionError" class="mt-2 text-[9.5px] leading-relaxed text-warn">{{ decisionError }}</p>
            <RouterLink
              v-if="pendingCount > 1"
              to="/chat"
              class="mt-2 flex items-center justify-between text-[9.5px] text-muted hover:text-ink"
            >
              还有 {{ pendingCount - 1 }} 条在问答页
              <ArrowRight :size="10" />
            </RouterLink>
          </div>
        </section>

        <section v-else class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-4 py-3">
            <div class="flex items-center gap-1.5 text-[11.5px] text-subink">
              <BookMarked :size="13" />
              待复习错题
            </div>
            <span class="text-[9.5px] text-muted">{{ wrongCount }} 题</span>
          </header>
          <div class="p-4">
            <p class="text-[12.5px] font-medium text-ink">
              {{ wrongCount ? `还有 ${wrongCount} 道错题没纠正` : '错题已经全部纠正' }}
            </p>
            <p class="mt-1 text-[10.5px] leading-relaxed text-muted">
              {{ wrongCount ? '重做一遍就会从待复习里移出。' : '保持住，继续往后推进新章节。' }}
            </p>
            <div class="mt-3 flex gap-2">
              <RouterLink
                :to="wrongConcepts.length ? { path: '/practice', query: { concepts: wrongConcepts.join(',') } } : '/wrongbook'"
                class="pill-btn h-8 flex-1 justify-center bg-ink text-[11px] text-canvas hover:opacity-90"
              >
                全部重练
              </RouterLink>
              <RouterLink
                to="/wrongbook"
                class="pill-btn h-8 border border-line bg-surface text-[11px] text-muted hover:border-line-strong"
              >
                错题本
              </RouterLink>
            </div>
          </div>
        </section>

        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-4 py-3">
            <h2 class="text-[11.5px] font-medium">最近练习</h2>
            <RouterLink to="/progress" class="text-[10px] text-muted hover:text-ink">学习报告</RouterLink>
          </header>
          <ul v-if="recentAttempts.length" class="p-2">
            <li
              v-for="a in recentAttempts"
              :key="a.attempt_id"
              class="flex items-start gap-2.5 rounded-xl px-2.5 py-2.5"
            >
              <component
                :is="a.correct ? CheckCircle2 : XCircle"
                :size="13"
                class="mt-0.5 shrink-0"
                :class="a.correct ? 'text-success' : 'text-warn'"
              />
              <div class="min-w-0 flex-1">
                <p class="truncate text-[11.5px] text-subink">{{ a.stem }}</p>
                <p class="mt-0.5 text-[9px] text-muted">{{ a.correct ? '答对' : '答错' }} · {{ timeLabel(a.created_at) }}</p>
              </div>
            </li>
          </ul>
          <div v-else class="px-4 py-6 text-center text-[10.5px] text-muted">还没有练习记录</div>
        </section>

        <section v-if="isTeacher" class="surface px-4 py-4">
          <h2 class="text-[11.5px] font-medium">班级</h2>
          <p class="mt-1 text-[10px] leading-relaxed text-muted">
            全班已覆盖 {{ classCovered }}/{{ classTotal }} 个知识点。
            <template v-if="hotQuestion">高频问题：{{ hotQuestion.question }}（{{ hotQuestion.count }} 次）。</template>
          </p>
          <RouterLink
            to="/insights"
            class="mt-3 flex items-center justify-between rounded-xl border border-line bg-tint-soft px-3 py-2 text-[10.5px] text-subink transition-colors hover:border-line-strong"
          >
            查看学情分析
            <ArrowRight :size="12" />
          </RouterLink>
        </section>

        <section class="surface px-4 py-3">
          <div class="flex items-center gap-1.5 text-[10px] text-muted">
            <Sparkles :size="11" class="text-brand" />
            覆盖 {{ plan?.summary.covered ?? 0 }}/{{ plan?.summary.total ?? 0 }} · 正确率
            {{ plan?.summary.accuracy ?? 0 }}%
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
