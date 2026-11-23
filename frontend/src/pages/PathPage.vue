<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ListChecks, RefreshCw, Sparkles, Target, TrendingUp } from 'lucide-vue-next'
import { api } from '@/api/client'
import type { LearningPlan } from '@/api/client'
import PlanTaskItem from '@/components/PlanTaskItem.vue'
import { useStudent } from '@/composables/useStudent'

const { currentKey } = useStudent()
const plan = ref<LearningPlan | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    plan.value = await api.get<LearningPlan>(`/learning/next?user_key=${currentKey.value}`)
  } catch {
    plan.value = null
  } finally {
    loading.value = false
  }
}

const summary = computed(() => [
  {
    label: '待补概念',
    value: (plan.value?.summary.total ?? 0) - (plan.value?.summary.mastered ?? 0),
    hint: `薄弱 ${plan.value?.summary.weak ?? 0} · 未练 ${plan.value?.summary.untried ?? 0}`,
    icon: Target,
    tone: 'text-warn',
  },
  {
    label: '已掌握',
    value: plan.value?.summary.mastered ?? 0,
    hint: `覆盖 ${plan.value?.summary.covered ?? 0}/${plan.value?.summary.total ?? 0} · 正确率 ${plan.value?.summary.accuracy ?? 0}%`,
    icon: TrendingUp,
    tone: 'text-success',
  },
  {
    label: '近 7 天练习',
    value: plan.value?.recent_attempts ?? 0,
    hint: '按作答记录统计',
    icon: ListChecks,
    tone: 'text-subink',
  },
])

function chapterPct(covered: number, total: number) {
  return total ? Math.round((covered / total) * 100) : 0
}

onMounted(load)
watch(currentKey, load)
</script>

<template>
  <div class="animate-fade-up px-9 py-8">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="text-[26px] font-semibold leading-tight tracking-[-0.025em]">学习计划</h1>
      </div>
      <button
        class="pill-btn h-9 border border-line bg-surface text-subink hover:border-line-strong hover:text-ink"
        :disabled="loading"
        @click="load"
      >
        <RefreshCw :size="13" :class="loading ? 'animate-spin' : ''" />
        重新规划
      </button>
    </div>

    <div class="mt-6 grid grid-cols-3 gap-3">
      <section
        v-for="item in summary"
        :key="item.label"
        class="rounded-2xl border border-line bg-surface px-5 py-4"
      >
        <div class="flex items-center justify-between">
          <p class="text-[10.5px] text-muted">{{ item.label }}</p>
          <component :is="item.icon" :size="14" :class="item.tone" />
        </div>
        <p class="mt-1 flex items-baseline gap-1.5">
          <span class="text-[26px] font-semibold leading-none tracking-tight" :class="item.tone">{{ item.value }}</span>
        </p>
        <p class="mt-1.5 text-[10px] text-muted">{{ item.hint }}</p>
      </section>
    </div>

    <section class="mt-4 rounded-2xl border border-line bg-surface p-5">
      <div class="flex items-center justify-between">
        <h2 class="flex items-center gap-1.5 text-[13px] font-semibold">
          <Sparkles :size="13" class="text-brand" />
          今天先做这几件
        </h2>
        <span class="text-[10px] text-muted">按优先级排序 · 预计 {{ plan?.tasks.reduce((s, t) => s + t.minutes, 0) ?? 0 }} 分钟</span>
      </div>
      <p v-if="plan?.stages?.[0]?.goal" class="mt-1 text-[11px] text-muted">{{ plan.stages[0].goal }}</p>

      <div v-if="loading && !plan" class="py-10 text-center text-[12px] text-muted">正在按你的记录排计划…</div>
      <div v-else-if="!plan?.tasks.length" class="py-10 text-center">
        <p class="text-[13px] font-medium text-ink">暂时没有要补的概念</p>
        <p class="mt-1 text-[11px] text-muted">去练习中心做一组题，或先去知识库补齐课件，这里就会长出任务。</p>
      </div>

      <ol v-else class="mt-3 space-y-2">
        <li v-for="(task, index) in plan.tasks" :key="task.concept_id ?? task.assignment_id ?? index">
          <PlanTaskItem :task="task" :index="index" />
        </li>
      </ol>
    </section>

    <section v-if="plan?.stages?.[1]?.tasks?.length" class="mt-4 rounded-2xl border border-line bg-surface p-5">
      <div class="flex items-center justify-between">
        <h2 class="text-[13px] font-semibold">接下来</h2>
        <span class="text-[10px] text-muted">预计 {{ plan.stages?.[1]?.minutes ?? 0 }} 分钟</span>
      </div>
      <ul class="mt-3 space-y-2">
        <li v-for="(task, index) in plan.stages?.[1]?.tasks ?? []" :key="task.concept_id ?? task.assignment_id ?? index">
          <PlanTaskItem :task="task" />
        </li>
      </ul>
    </section>

    <section class="mt-4 rounded-2xl border border-line bg-surface p-5">
      <div class="flex items-center justify-between">
        <h2 class="text-[13px] font-semibold">章节进度</h2>
        <span class="text-[10px] text-muted">按知识点覆盖与正确率计算</span>
      </div>
      <ul class="mt-3 space-y-3">
        <li v-for="chapter in plan?.chapters ?? []" :key="chapter.chapter_id">
          <div class="flex items-center justify-between text-[11px]">
            <span class="text-subink">{{ chapter.title }}</span>
            <span class="font-mono text-[10px] text-muted">
              {{ chapter.concepts ? `${chapter.covered}/${chapter.concepts} 概念 · ${chapter.rate}%` : '暂无知识点' }}
            </span>
          </div>
          <div class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-tint">
            <div
              class="h-full rounded-full transition-all duration-500"
              :class="chapter.rate >= 80 ? 'bg-success/70' : chapter.rate >= 55 ? 'bg-brand/70' : 'bg-warn/75'"
              :style="{ width: chapterPct(chapter.covered, chapter.concepts) + '%' }"
            />
          </div>
        </li>
      </ul>
    </section>
  </div>
</template>
