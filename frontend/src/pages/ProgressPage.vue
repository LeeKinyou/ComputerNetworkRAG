<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  ArrowRight,
  BookMarked,
  Brain,
  CheckCheck,
  Clock3,
  RefreshCw,
  Sparkles,
  Target,
  TrendingUp,
} from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { api } from '@/api/client'
import type {
  AnalyticsConcept,
  LearningPlan,
  PracticeAttemptRow,
  WrongBook,
} from '@/api/client'
import { useStudent } from '@/composables/useStudent'

const { currentKey } = useStudent()
const range = ref<'week' | 'month'>('week')
const plan = ref<LearningPlan | null>(null)
const wrongbook = ref<WrongBook | null>(null)
const attempts = ref<PracticeAttemptRow[]>([])
const concepts = ref<AnalyticsConcept[]>([])

async function load() {
  const key = currentKey.value
  try {
    const [p, w, a, c] = await Promise.all([
      api.get<LearningPlan>(`/learning/next?user_key=${key}&limit=3`),
      api.get<WrongBook>(`/practice/wrongbook?user_key=${key}`),
      api.get<{ items: PracticeAttemptRow[] }>(`/practice/attempts?user_key=${key}&limit=100`),
      api.get<{ items: AnalyticsConcept[] }>(`/analytics/concepts?user_key=${key}`),
    ])
    plan.value = p
    wrongbook.value = w
    attempts.value = a.items ?? []
    concepts.value = c.items ?? []
  } catch {
    plan.value = null
    wrongbook.value = null
    attempts.value = []
    concepts.value = []
  }
}

onMounted(load)
watch(currentKey, load)

const DAY = 86400000
const todayStart = (() => {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d
})()

const dayKey = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

const rangeDays = computed(() => (range.value === 'week' ? 7 : 30))
const rangeStart = computed(() => new Date(todayStart.getTime() - (rangeDays.value - 1) * DAY))

const scoped = computed(() =>
  attempts.value.filter((a) => new Date(a.created_at).getTime() >= rangeStart.value.getTime()),
)

const scopedCorrect = computed(() => scoped.value.filter((a) => a.correct).length)
const scopedRate = computed(() =>
  scoped.value.length ? Math.round((scopedCorrect.value / scoped.value.length) * 100) : 0,
)
const scopedLabel = computed(() => (range.value === 'week' ? '本周练习' : '本月练习'))

const counts = computed(() => {
  const c = { mastered: 0, weak: 0, new: 0 }
  for (const item of concepts.value) {
    if (item.state === 'mastered') c.mastered += 1
    else if (item.state === 'weak' || item.state === 'normal') c.weak += 1
    else c.new += 1
  }
  return c
})
const total = computed(() => counts.value.mastered + counts.value.weak + counts.value.new)
const pct = (n: number) => (total.value ? Math.round((n / total.value) * 100) : 0)

const masteryRate = computed(() =>
  total.value ? Math.round((counts.value.mastered / total.value) * 100) : 0,
)

const dailySeries = computed(() => {
  const map = new Map<string, number>()
  for (const a of attempts.value) {
    const d = new Date(a.created_at)
    const key = dayKey(d)
    map.set(key, (map.get(key) ?? 0) + 1)
  }
  if (range.value === 'week') {
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(todayStart.getTime() - (6 - i) * DAY)
      return { label: `${d.getMonth() + 1}/${d.getDate()}`, value: map.get(dayKey(d)) ?? 0 }
    })
  }
  return Array.from({ length: 4 }, (_, i) => {
    const end = new Date(todayStart.getTime() - (3 - i) * 7 * DAY + DAY - 1)
    const start = new Date(todayStart.getTime() - (4 - i) * 7 * DAY)
    const value = attempts.value.filter((a) => {
      const t = new Date(a.created_at).getTime()
      return t >= start.getTime() && t <= end.getTime()
    }).length
    return { label: `第 ${i + 1} 周`, value }
  })
})

const maxDaily = computed(() => Math.max(...dailySeries.value.map((d) => d.value), 1))
const totalInChart = computed(() => dailySeries.value.reduce((s, d) => s + d.value, 0))

const chapterRows = computed(() => plan.value?.chapters ?? [])

const wrongItems = computed(() => (wrongbook.value?.items ?? []).slice(0, 5))

const weakPoints = computed(() =>
  concepts.value
    .filter((item) => item.state === 'weak')
    .sort((a, b) => a.rate - b.rate)
    .slice(0, 4)
    .map((item) => ({
      id: item.concept_id,
      label: item.title,
      wrong: Math.max(item.attempts - item.correct, 0),
      hint: `${item.attempts} 次作答 · 正确率 ${item.rate}%`,
      rate: item.rate,
    })),
)

const activeDays = computed(() => {
  const set = new Set<string>()
  for (const a of attempts.value) set.add(dayKey(new Date(a.created_at)))
  return set.size
})

const summaryText = computed(() => {
  if (!attempts.value.length) {
    return '还没有练习记录。先做一组题，这里会自动生成你的学习小结。'
  }
  const weak = weakPoints.value.map((w) => `${w.label}（${w.rate}%）`).join('、')
  const head = `近 ${rangeDays.value} 天完成 ${scoped.value.length} 题，正确率 ${scopedRate.value}%；累计覆盖 ${plan.value?.summary.covered ?? 0}/${plan.value?.summary.total ?? 0} 个知识点。`
  return weak ? `${head} 当前最该补的是 ${weak}。` : `${head} 没有明显薄弱点，可以往没练过的概念推进。`
})

const firstWeak = computed(() => weakPoints.value[0] ?? null)

const askLink = computed(() => {
  if (!firstWeak.value) return { path: '/chat' }
  return { path: '/chat', query: { q: `帮我系统复习「${firstWeak.value.label}」，先讲原理，再出两道判断题。` } }
})

function retry(conceptId: string | null) {
  return { path: '/practice', query: conceptId ? { concept: conceptId } : {} }
}
</script>

<template>
  <div class="animate-fade-up px-9 py-8">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="text-[26px] font-semibold leading-tight tracking-[-0.025em]">学习报告</h1>
        <p class="mt-1.5 max-w-[600px] text-[12.5px] leading-relaxed text-muted">
          你自己的学习轨迹：学到哪、卡在哪、下一步做什么。这里不做班级排名。
        </p>
      </div>
      <div class="flex items-center gap-0.5 rounded-full bg-tint p-0.5">
        <button
          class="rounded-full px-2.5 py-1 text-[10.5px] transition-colors"
          :class="range === 'week' ? 'bg-surface text-ink shadow-sm' : 'text-muted'"
          @click="range = 'week'"
        >
          本周
        </button>
        <button
          class="rounded-full px-2.5 py-1 text-[10.5px] transition-colors"
          :class="range === 'month' ? 'bg-surface text-ink shadow-sm' : 'text-muted'"
          @click="range = 'month'"
        >
          本月
        </button>
      </div>
    </div>

    <section class="surface mt-5 grid grid-cols-2 divide-line md:grid-cols-4 md:divide-x">
      <div class="px-5 py-4">
        <div class="flex items-center gap-1.5 text-[10px] text-muted">
          <Clock3 :size="11" />
          {{ scopedLabel }}
        </div>
        <div class="mt-2 flex items-end gap-2">
          <span class="text-[24px] font-semibold leading-none tracking-[-0.02em]">{{ scoped.length }}</span>
          <span class="mb-0.5 flex items-center gap-0.5 text-[9.5px] text-success">
            <TrendingUp :size="10" />
            {{ scopedRate }}% 正确
          </span>
        </div>
      </div>
      <div class="px-5 py-4">
        <div class="flex items-center gap-1.5 text-[10px] text-muted">
          <CheckCheck :size="11" />
          累计正确率
        </div>
        <div class="mt-2 flex items-end gap-2">
          <span class="text-[24px] font-semibold leading-none tracking-[-0.02em]">
            {{ plan?.summary.accuracy ?? 0 }}%
          </span>
          <span class="mb-0.5 text-[9.5px] text-muted">共 {{ attempts.length }} 次作答</span>
        </div>
      </div>
      <div class="px-5 py-4">
        <div class="flex items-center gap-1.5 text-[10px] text-muted">
          <BookMarked :size="11" />
          知识点覆盖
        </div>
        <div class="mt-2 flex items-end gap-2">
          <span class="text-[24px] font-semibold leading-none tracking-[-0.02em]">
            {{ plan?.summary.covered ?? 0 }}
          </span>
          <span class="mb-0.5 text-[9.5px] text-muted">/ {{ plan?.summary.total ?? 0 }} 个</span>
        </div>
      </div>
      <div class="px-5 py-4">
        <div class="flex items-center gap-1.5 text-[10px] text-muted">
          <Target :size="11" />
          掌握度
        </div>
        <div class="mt-2 flex items-end gap-2">
          <span class="text-[24px] font-semibold leading-none tracking-[-0.02em]">{{ masteryRate }}%</span>
          <span class="mb-0.5 text-[9.5px] text-muted">{{ counts.mastered }} / {{ total }} 个</span>
        </div>
      </div>
    </section>

    <div class="mt-4 grid items-start gap-4 xl:grid-cols-[1fr_328px]">
      <div class="flex flex-col gap-4">
        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-5 py-3.5">
            <div class="flex items-center gap-2">
              <Brain :size="14" class="text-muted" />
              <h2 class="text-[12.5px] font-medium">掌握度</h2>
            </div>
            <RouterLink to="/graph" class="flex items-center gap-0.5 text-[10px] text-muted hover:text-ink">
              去图谱看
              <ArrowRight :size="10" />
            </RouterLink>
          </header>

          <div class="p-5">
            <div v-if="!total" class="rounded-xl border border-line bg-tint-soft px-4 py-6 text-center">
              <p class="text-[11px] text-muted">还没有可统计的作答记录</p>
              <RouterLink
                to="/practice"
                class="pill-btn mt-3 h-8 bg-ink px-3 text-[10.5px] text-canvas hover:opacity-90"
              >
                去练习中心
                <ArrowRight :size="11" />
              </RouterLink>
            </div>
            <template v-else>
              <div class="flex h-2.5 overflow-hidden rounded-full bg-tint">
                <div class="h-full bg-success/70" :style="{ width: pct(counts.mastered) + '%' }" />
                <div class="h-full bg-warn/75" :style="{ width: pct(counts.weak) + '%' }" />
                <div class="h-full bg-[#9AA6BE]/70" :style="{ width: pct(counts.new) + '%' }" />
              </div>
              <div class="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[10px]">
                <span class="flex items-center gap-1.5 text-subink">
                  <span class="h-2 w-2 rounded-full bg-success/70" />
                  已掌握 {{ counts.mastered }} · {{ pct(counts.mastered) }}%
                </span>
                <span class="flex items-center gap-1.5 text-subink">
                  <span class="h-2 w-2 rounded-full bg-warn/75" />
                  薄弱或一般 {{ counts.weak }} · {{ pct(counts.weak) }}%
                </span>
                <span class="flex items-center gap-1.5 text-subink">
                  <span class="h-2 w-2 rounded-full bg-[#9AA6BE]/70" />
                  未练 {{ counts.new }} · {{ pct(counts.new) }}%
                </span>
              </div>

              <div class="mt-5 flex flex-col gap-2.5">
                <div v-for="c in chapterRows" :key="c.chapter_id">
                  <div class="flex items-center justify-between text-[10px]">
                    <span class="text-subink">{{ c.title }}</span>
                    <span class="font-mono" :class="c.rate < 55 ? 'text-warn' : 'text-muted'">
                      {{ c.concepts ? `${c.covered}/${c.concepts} · ${c.rate}%` : '暂无知识点' }}
                    </span>
                  </div>
                  <div class="mt-1 h-1 overflow-hidden rounded-full bg-tint">
                    <div
                      class="h-full rounded-full"
                      :class="c.rate >= 80 ? 'bg-success/70' : c.rate >= 55 ? 'bg-brand/80' : 'bg-warn/75'"
                      :style="{ width: (c.concepts ? c.rate : 0) + '%' }"
                    />
                  </div>
                </div>
              </div>
            </template>
          </div>
        </section>

        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-5 py-3.5">
            <div class="flex items-center gap-2">
              <TrendingUp :size="14" class="text-muted" />
              <h2 class="text-[12.5px] font-medium">{{ range === 'week' ? '近 7 天练习' : '近 4 周练习' }}</h2>
            </div>
            <span class="text-[9.5px] text-muted">共 {{ totalInChart }} 次</span>
          </header>
          <div class="px-5 pb-4 pt-5">
            <div class="flex h-[96px] items-stretch gap-3">
              <div v-for="d in dailySeries" :key="d.label" class="flex h-full flex-1 flex-col items-center gap-1.5">
                <span class="font-mono text-[8.5px] text-muted">{{ d.value || '' }}</span>
                <div class="flex w-full flex-1 items-end">
                  <div
                    class="w-full rounded-[5px] transition-[height]"
                    :class="d.value === 0 ? 'bg-tint' : 'bg-brand/45'"
                    :style="{ height: Math.max((d.value / maxDaily) * 100, d.value ? 8 : 3) + '%' }"
                  />
                </div>
                <span class="text-[9px] text-muted">{{ d.label }}</span>
              </div>
            </div>
          </div>
        </section>

        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-5 py-3.5">
            <div class="flex items-center gap-2">
              <BookMarked :size="14" class="text-muted" />
              <h2 class="text-[12.5px] font-medium">错题本</h2>
              <span class="rounded-md bg-tint px-1.5 py-0.5 text-[9.5px] text-muted">
                {{ wrongbook?.unresolved ?? 0 }}
              </span>
            </div>
            <RouterLink to="/wrongbook" class="flex items-center gap-1 text-[10px] text-muted hover:text-ink">
              <RefreshCw :size="10" />
              全部复习
            </RouterLink>
          </header>
          <ul v-if="wrongItems.length" class="p-2">
            <li
              v-for="m in wrongItems"
              :key="m.question_id"
              class="flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors hover:bg-tint-soft"
            >
              <span class="w-14 shrink-0 truncate rounded-full bg-tint px-1.5 py-0.5 text-center text-[9px] text-subink">
                {{ m.concept_title }}
              </span>
              <div class="min-w-0 flex-1">
                <p class="truncate text-[11.5px] text-subink">{{ m.stem }}</p>
                <p class="mt-0.5 text-[9.5px] text-muted">
                  错 {{ m.wrong }} 次 / 共 {{ m.attempts }} 次 · {{ m.chapter_title }}
                </p>
              </div>
              <span class="shrink-0 rounded-full bg-warn/12 px-1.5 py-0.5 text-[9px] text-warn">待复习</span>
              <RouterLink :to="retry(m.concept_id)" class="shrink-0 text-[9.5px] text-brand hover:underline">
                重练
              </RouterLink>
            </li>
          </ul>
          <div v-else class="px-5 py-8 text-center text-[11px] text-muted">
            目前没有待复习错题。保持住。
          </div>
        </section>
      </div>

      <div class="flex flex-col gap-4">
        <section class="surface p-4">
          <div class="flex items-center gap-1.5 text-[10.5px] font-medium text-subink">
            <Sparkles :size="12" class="text-brand" />
            {{ range === 'week' ? '本周小结' : '本月小结' }}
          </div>
          <p class="mt-2 text-[10.5px] leading-[1.75] text-muted">{{ summaryText }}</p>
          <div class="mt-3 flex flex-col gap-1.5">
            <RouterLink
              :to="askLink"
              class="flex items-center justify-between rounded-xl border border-line bg-tint-soft px-3 py-2 text-[10px] text-subink transition-colors hover:border-line-strong"
            >
              {{ firstWeak ? `先复习 ${firstWeak.label}` : '找助教梳理薄弱点' }}
              <ArrowRight :size="10" />
            </RouterLink>
            <RouterLink
              to="/path"
              class="flex items-center justify-between rounded-xl border border-line bg-tint-soft px-3 py-2 text-[10px] text-subink transition-colors hover:border-line-strong"
            >
              调整下周计划
              <ArrowRight :size="10" />
            </RouterLink>
          </div>
        </section>

        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-4 py-3">
            <h2 class="text-[11.5px] font-medium">薄弱点</h2>
            <span class="text-[9px] text-muted">{{ weakPoints.length }} 个</span>
          </header>
          <div class="p-3">
            <div
              v-for="w in weakPoints"
              :key="w.id"
              class="mb-2 rounded-xl border border-line bg-tint-soft px-3 py-2.5 last:mb-0"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-[11px] text-subink">{{ w.label }}</span>
                <span class="shrink-0 text-[9px] text-warn">错 {{ w.wrong }} 次</span>
              </div>
              <p class="mt-0.5 text-[9px] text-muted">{{ w.hint }}</p>
            </div>
            <div v-if="!weakPoints.length" class="py-4 text-center text-[10.5px] text-muted">
              暂无低于 60% 的知识点
            </div>
            <RouterLink
              :to="askLink"
              class="pill-btn mt-1 h-8 w-full justify-center bg-ink text-[10.5px] text-canvas hover:opacity-90"
            >
              <Sparkles :size="12" />
              生成针对性复习
            </RouterLink>
          </div>
        </section>

        <section class="surface p-4">
          <h2 class="text-[11.5px] font-medium">我的记录</h2>
          <div class="mt-3 flex flex-col gap-2.5">
            <div class="flex items-center justify-between gap-2 border-b border-line pb-2.5">
              <span class="text-[10.5px] text-subink">累计作答</span>
              <span class="shrink-0 text-[9px] text-muted">{{ attempts.length }} 次</span>
            </div>
            <div class="flex items-center justify-between gap-2 border-b border-line pb-2.5">
              <span class="text-[10.5px] text-subink">练过的概念</span>
              <span class="shrink-0 text-[9px] text-muted">{{ plan?.summary.covered ?? 0 }} 个</span>
            </div>
            <div class="flex items-center justify-between gap-2 border-b border-line pb-2.5">
              <span class="text-[10.5px] text-subink">活跃天数</span>
              <span class="shrink-0 text-[9px] text-muted">{{ activeDays }} 天</span>
            </div>
            <div class="flex items-center justify-between gap-2">
              <span class="text-[10.5px] text-subink">待复习错题</span>
              <span class="shrink-0 text-[9px] text-muted">{{ wrongbook?.unresolved ?? 0 }} 题</span>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
