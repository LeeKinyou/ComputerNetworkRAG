<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  ArrowUpRight,
  BarChart3,
  Download,
  Flame,
  MessageSquareText,
  Sparkles,
  Target,
} from 'lucide-vue-next'
import { api } from '@/api/client'
import type { AnalyticsConcept, AnalyticsOverview } from '@/api/client'
import { insights } from '@/mock/workbench'

const range = ref<'week' | 'month'>('week')
const toast = ref('')
const stats = ref<AnalyticsOverview | null>(null)
const concepts = ref<AnalyticsConcept[]>([])
const conceptTotal = ref(0)
const conceptCovered = ref(0)

onMounted(async () => {
  try {
    stats.value = await api.get<AnalyticsOverview>('/analytics/overview')
  } catch {
    stats.value = null
  }
  try {
    const result = await api.get<{
      items: AnalyticsConcept[]
      total_concepts: number
      covered_concepts: number
    }>('/analytics/concepts')
    concepts.value = result.items
    conceptTotal.value = result.total_concepts
    conceptCovered.value = result.covered_concepts
  } catch {
    concepts.value = []
  }
})

function conceptTone(state: AnalyticsConcept['state']) {
  if (state === 'weak') return 'bg-[#E8A23C]/80'
  if (state === 'normal') return 'bg-brand/70'
  if (state === 'mastered') return 'bg-success/70'
  return 'bg-tint'
}

const weeklyQuestions = computed(() => stats.value?.questions_week ?? insights.weeklyQuestions)
const modeLine = computed(() => {
  const split = stats.value?.mode_split
  if (!split) return '较上周 +18%，网络层占 46%'
  return `智能体 ${split.agent} 次 · 快速检索 ${split.rag} 次 · 完成率 ${stats.value?.completion_rate ?? 0}%`
})
const hotQuestion = computed(() => stats.value?.hot_questions[0]?.question ?? insights.highFrequency[0].q)
const hotCount = computed(() => stats.value?.hot_questions[0]?.count ?? insights.highFrequency[0].count)
const chapterRows = computed(() =>
  stats.value?.chapter_focus?.length ? stats.value.chapter_focus : insights.chapterMastery,
)
const hotList = computed(() =>
  stats.value?.hot_questions?.length
    ? stats.value.hot_questions.map((item) => ({ q: item.question, count: item.count }))
    : insights.highFrequency,
)

function act(text: string) {
  toast.value = text
  window.setTimeout(() => (toast.value = ''), 2200)
}
</script>

<template>
  <div class="animate-fade-up px-9 py-8">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="text-[26px] font-semibold leading-tight tracking-[-0.025em]">学情分析</h1>
        <p class="mt-1.5 max-w-[600px] text-[12.5px] leading-relaxed text-muted">
          教师视角：这周学生卡在哪，哪些问题值得在课上讲，哪些知识点该补一份练习。
        </p>
      </div>
      <div class="flex items-center gap-2">
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
        <button class="pill-btn h-9 border border-line bg-surface text-[11.5px] text-subink hover:border-line-strong">
          <Download :size="13" />
          导出
        </button>
      </div>
    </div>

    <section class="surface mt-5 grid grid-cols-1 divide-line md:grid-cols-3 md:divide-x">
      <div class="px-5 py-4">
        <div class="flex items-center gap-1.5 text-[10px] text-muted">
          <BarChart3 :size="11" />
          {{ insights.className }}
        </div>
        <div class="mt-2 flex items-end gap-2">
          <span class="text-[28px] font-semibold leading-none tracking-[-0.03em]">
            {{ weeklyQuestions }}
          </span>
          <span class="mb-0.5 text-[11px] text-muted">次提问 · 本周</span>
        </div>
        <p class="mt-2 text-[9.5px] text-muted">{{ modeLine }}</p>
      </div>
      <div class="px-5 py-4">
        <div class="flex items-center gap-1.5 text-[10px] text-muted">
          <Flame :size="11" />
          最热问题
        </div>
        <p class="mt-2 line-clamp-1 text-[12.5px] font-medium text-ink">
          {{ hotQuestion }}
        </p>
        <p class="mt-2 text-[9.5px] text-muted">{{ hotCount }} 次被问到，建议课上统一讲</p>
      </div>
      <div class="px-5 py-4">
        <div class="flex items-center gap-1.5 text-[10px] text-muted">
          <Target :size="11" />
          最薄弱
        </div>
        <p class="mt-2 text-[12.5px] font-medium text-ink">{{ insights.weakPoints[0].label }}</p>
        <p class="mt-2 text-[9.5px] text-warn">正确率 {{ insights.weakPoints[0].rate }} · 建议补一份练习</p>
      </div>
    </section>

    <div class="mt-4 grid items-start gap-4 xl:grid-cols-[1fr_328px]">
      <div class="flex flex-col gap-4">
        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-5 py-3.5">
            <div class="flex items-center gap-2">
              <Target :size="14" class="text-muted" />
              <h2 class="text-[12.5px] font-medium">章节关注度</h2>
            </div>
            <span class="text-[9.5px] text-muted">按引用命中的章节统计</span>
          </header>
          <div class="flex flex-col gap-3.5 p-5">
            <div v-for="c in chapterRows" :key="c.label">
              <div class="flex items-center justify-between text-[11px]">
                <span class="text-subink">{{ c.label }}</span>
                <span class="font-mono text-[10px]" :class="c.value < 55 ? 'text-warn' : 'text-muted'">
                  {{ c.value }}%
                </span>
              </div>
              <div class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-tint">
                <div
                  class="h-full rounded-full"
                  :class="c.value >= 80 ? 'bg-success/75' : c.value >= 55 ? 'bg-brand' : 'bg-warn/80'"
                  :style="{ width: c.value + '%' }"
                />
              </div>
            </div>
          </div>
        </section>

        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-5 py-3.5">
            <div class="flex items-center gap-2">
              <BarChart3 :size="14" class="text-muted" />
              <h2 class="text-[12.5px] font-medium">概念掌握</h2>
            </div>
            <span class="text-[9.5px] text-muted">
              已覆盖 {{ conceptCovered }} / {{ conceptTotal }} 个知识点
            </span>
          </header>
          <div v-if="concepts.length" class="grid gap-x-7 gap-y-3 p-5 md:grid-cols-2">
            <div v-for="concept in concepts" :key="concept.concept_id">
              <div class="flex items-center justify-between text-[10.5px]">
                <span class="truncate text-subink">{{ concept.title }}</span>
                <span
                  class="ml-2 shrink-0 font-mono text-[9.5px]"
                  :class="
                    concept.state === 'weak'
                      ? 'text-[#B9761D]'
                      : concept.state === 'mastered'
                        ? 'text-success'
                        : 'text-muted'
                  "
                >
                  {{ concept.attempts ? concept.rate + '%' : '未练' }}
                </span>
              </div>
              <div class="mt-1.5 h-[3px] overflow-hidden rounded-full bg-tint">
                <div
                  class="h-full rounded-full"
                  :class="conceptTone(concept.state)"
                  :style="{ width: concept.attempts ? concept.rate + '%' : '0%' }"
                />
              </div>
              <p class="mt-1 text-[9px] text-muted">
                {{ concept.attempts }} 次作答 · {{ concept.students }} 人
                <span v-if="concept.weak_students" class="text-[#B9761D]">
                  · {{ concept.weak_students }} 人薄弱
                </span>
              </p>
            </div>
          </div>
          <p v-else class="px-5 py-8 text-center text-[11px] text-muted">
            还没有作答记录，学生练几题后这里会出现真实的概念掌握分布。
          </p>
        </section>

        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-5 py-3.5">
            <div class="flex items-center gap-2">
              <MessageSquareText :size="14" class="text-muted" />
              <h2 class="text-[12.5px] font-medium">高频问题</h2>
            </div>
            <span class="text-[9.5px] text-muted">按提问次数排序</span>
          </header>
          <ul class="p-2">
            <li
              v-for="(q, i) in hotList"
              :key="q.q"
              class="flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors hover:bg-tint-soft"
            >
              <span class="w-4 shrink-0 font-mono text-[10px] text-muted">{{ i + 1 }}</span>
              <p class="min-w-0 flex-1 truncate text-[11.5px] text-subink">{{ q.q }}</p>
              <span class="shrink-0 text-[9.5px] text-muted">{{ q.count }} 次</span>
              <button
                class="shrink-0 rounded-full border border-line px-2 py-0.5 text-[9px] text-muted transition-colors hover:border-brand/40 hover:text-brand"
                @click="act('已生成答疑卡')"
              >
                生成答疑卡
              </button>
            </li>
          </ul>
        </section>
      </div>

      <div class="flex flex-col gap-4">
        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-4 py-3">
            <div class="flex items-center gap-1.5">
              <Target :size="13" class="text-muted" />
              <h2 class="text-[11.5px] font-medium">薄弱点</h2>
            </div>
            <span class="text-[9px] text-muted">Top 3</span>
          </header>
          <div class="p-3">
            <div
              v-for="w in insights.weakPoints"
              :key="w.label"
              class="mb-2 rounded-xl border border-line bg-tint-soft px-3 py-2.5 last:mb-0"
            >
              <div class="flex items-center justify-between">
                <span class="text-[11px] text-subink">{{ w.label }}</span>
                <span class="font-mono text-[9.5px]" :class="w.level === 'high' ? 'text-warn' : 'text-muted'">
                  {{ w.rate }}
                </span>
              </div>
              <div class="mt-1.5 h-1 overflow-hidden rounded-full bg-tint">
                <div
                  class="h-full rounded-full"
                  :class="w.level === 'high' ? 'bg-warn/80' : 'bg-brand/70'"
                  :style="{ width: w.rate }"
                />
              </div>
            </div>
            <button
              class="pill-btn mt-1 h-8 w-full justify-center bg-ink text-[10.5px] text-canvas hover:opacity-90"
              @click="act('已为 3 个薄弱点生成练习')"
            >
              <Sparkles :size="12" />
              一键生成练习
            </button>
          </div>
        </section>

        <section class="surface overflow-hidden">
          <header class="flex items-center gap-1.5 border-b border-line px-4 py-3">
            <MessageSquareText :size="13" class="text-muted" />
            <h2 class="text-[11.5px] font-medium">错因分布</h2>
          </header>
          <div class="flex flex-col gap-2.5 p-4">
            <div v-for="e in insights.errorTypes" :key="e.label">
              <div class="flex items-center justify-between text-[9.5px]">
                <span class="text-subink">{{ e.label }}</span>
                <span class="font-mono text-muted">{{ e.value }}%</span>
              </div>
              <div class="mt-1 h-1 overflow-hidden rounded-full bg-tint">
                <div class="h-full rounded-full bg-brand/60" :style="{ width: e.value + '%' }" />
              </div>
            </div>
          </div>
        </section>

        <section class="surface p-4">
          <div class="flex items-center gap-1.5 text-[10.5px] font-medium text-subink">
            <Sparkles :size="12" class="text-brand" />
            本周建议
          </div>
          <p class="mt-2 text-[10px] leading-[1.7] text-muted">
            网络层的错误集中在「块对齐」这一步，不是概念不会。建议下节课用 10 分钟演示 /26–/29
            的地址块，再让学生做 3 道同类题。
          </p>
          <button
            class="mt-3 flex w-full items-center justify-between rounded-xl border border-line bg-tint-soft px-3 py-2 text-[10px] text-subink transition-colors hover:border-line-strong"
            @click="act('已推送学习任务给 42 人')"
          >
            推送到班级任务
            <ArrowUpRight :size="11" />
          </button>
        </section>
      </div>
    </div>

    <div
      v-if="toast"
      class="pointer-events-none fixed bottom-8 left-1/2 z-50 -translate-x-1/2 rounded-full bg-ink px-3.5 py-1.5 text-[11px] text-canvas shadow-lg"
    >
      {{ toast }}
    </div>
  </div>
</template>
