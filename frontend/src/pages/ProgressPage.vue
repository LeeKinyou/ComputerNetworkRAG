<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  ArrowRight,
  BookOpen,
  Brain,
  CheckCheck,
  Clock3,
  Flame,
  RefreshCw,
  Sparkles,
  Target,
  TrendingUp,
} from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { masteryMap } from '@/mock/workbench'
import { studentReport } from '@/mock/workbench'

const range = ref<'week' | 'month'>('week')

const counts = computed(() => {
  const c = { mastered: 0, weak: 0, new: 0 }
  for (const m of Object.values(masteryMap)) c[m] += 1
  return c
})
const total = computed(() => counts.value.mastered + counts.value.weak + counts.value.new)

const pct = (n: number) => Math.round((n / total.value) * 100)

const maxDaily = computed(() => Math.max(...studentReport.daily.map((d) => d.minutes), 1))

const totalMinutes = computed(() => studentReport.daily.reduce((s, d) => s + d.minutes, 0))
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
          学习时长
        </div>
        <div class="mt-2 flex items-end gap-2">
          <span class="text-[24px] font-semibold leading-none tracking-[-0.02em]">2h 45m</span>
          <span class="mb-0.5 flex items-center gap-0.5 text-[9.5px] text-success">
            <TrendingUp :size="10" />
            {{ studentReport.weeklyDelta }}
          </span>
        </div>
      </div>
      <div class="px-5 py-4">
        <div class="flex items-center gap-1.5 text-[10px] text-muted">
          <CheckCheck :size="11" />
          完成任务
        </div>
        <div class="mt-2 flex items-end gap-2">
          <span class="text-[24px] font-semibold leading-none tracking-[-0.02em]">{{ studentReport.tasksDone }}</span>
          <span class="mb-0.5 text-[9.5px] text-muted">本周</span>
        </div>
      </div>
      <div class="px-5 py-4">
        <div class="flex items-center gap-1.5 text-[10px] text-muted">
          <Flame :size="11" />
          连续学习
        </div>
        <div class="mt-2 flex items-end gap-2">
          <span class="text-[24px] font-semibold leading-none tracking-[-0.02em]">{{ studentReport.streak }}</span>
          <span class="mb-0.5 text-[9.5px] text-muted">天 · 最长 12 天</span>
        </div>
      </div>
      <div class="px-5 py-4">
        <div class="flex items-center gap-1.5 text-[10px] text-muted">
          <Target :size="11" />
          知识点掌握
        </div>
        <div class="mt-2 flex items-end gap-2">
          <span class="text-[24px] font-semibold leading-none tracking-[-0.02em]">{{ studentReport.masteryRate }}%</span>
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
                薄弱 {{ counts.weak }} · {{ pct(counts.weak) }}%
              </span>
              <span class="flex items-center gap-1.5 text-subink">
                <span class="h-2 w-2 rounded-full bg-[#9AA6BE]/70" />
                未学 {{ counts.new }} · {{ pct(counts.new) }}%
              </span>
            </div>

            <div class="mt-5 flex flex-col gap-2.5">
              <div v-for="c in studentReport.chapterMastery" :key="c.label">
                <div class="flex items-center justify-between text-[10px]">
                  <span class="text-subink">{{ c.label }}</span>
                  <span class="font-mono" :class="c.value < 55 ? 'text-warn' : 'text-muted'">{{ c.value }}%</span>
                </div>
                <div class="mt-1 h-1 overflow-hidden rounded-full bg-tint">
                  <div
                    class="h-full rounded-full"
                    :class="c.value >= 80 ? 'bg-success/70' : c.value >= 55 ? 'bg-brand/80' : 'bg-warn/75'"
                    :style="{ width: c.value + '%' }"
                  />
                </div>
              </div>
            </div>
          </div>
        </section>

        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-5 py-3.5">
            <div class="flex items-center gap-2">
              <TrendingUp :size="14" class="text-muted" />
              <h2 class="text-[12.5px] font-medium">近 7 天</h2>
            </div>
            <span class="text-[9.5px] text-muted">共 {{ totalMinutes }} 分钟</span>
          </header>
          <div class="px-5 pb-4 pt-5">
            <div class="flex h-[96px] items-stretch gap-3">
              <div v-for="d in studentReport.daily" :key="d.day" class="flex h-full flex-1 flex-col items-center gap-1.5">
                <span class="font-mono text-[8.5px] text-muted">{{ d.minutes || '' }}</span>
                <div class="flex w-full flex-1 items-end">
                  <div
                    class="w-full rounded-[5px] transition-[height]"
                    :class="d.minutes === 0 ? 'bg-tint' : 'bg-brand/45'"
                    :style="{ height: Math.max((d.minutes / maxDaily) * 100, d.minutes ? 8 : 3) + '%' }"
                  />
                </div>
                <span class="text-[9px] text-muted">{{ d.day }}</span>
              </div>
            </div>
          </div>
        </section>

        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-5 py-3.5">
            <div class="flex items-center gap-2">
              <BookOpen :size="14" class="text-muted" />
              <h2 class="text-[12.5px] font-medium">错题本</h2>
              <span class="rounded-md bg-tint px-1.5 py-0.5 text-[9.5px] text-muted">
                {{ studentReport.mistakes.length }}
              </span>
            </div>
            <button class="flex items-center gap-1 text-[10px] text-muted hover:text-ink">
              <RefreshCw :size="10" />
              全部复习
            </button>
          </header>
          <ul class="p-2">
            <li
              v-for="m in studentReport.mistakes"
              :key="m.id"
              class="flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors hover:bg-tint-soft"
            >
              <span class="w-14 shrink-0 rounded-full bg-tint px-1.5 py-0.5 text-center text-[9px] text-subink">
                {{ m.topic }}
              </span>
              <div class="min-w-0 flex-1">
                <p class="truncate text-[11.5px] text-subink">{{ m.title }}</p>
                <p class="mt-0.5 text-[9.5px] text-muted">{{ m.reason }} · {{ m.time }}</p>
              </div>
              <span
                class="shrink-0 rounded-full px-1.5 py-0.5 text-[9px]"
                :class="m.state === '待复习' ? 'bg-warn/12 text-warn' : 'bg-success/12 text-success'"
              >
                {{ m.state }}
              </span>
              <RouterLink
                :to="{ path: '/chat', query: { q: `帮我复习 ${m.topic}：${m.title}` } }"
                class="shrink-0 text-[9.5px] text-brand hover:underline"
              >
                复习
              </RouterLink>
            </li>
          </ul>
        </section>
      </div>

      <div class="flex flex-col gap-4">
        <section class="surface p-4">
          <div class="flex items-center gap-1.5 text-[10.5px] font-medium text-subink">
            <Sparkles :size="12" class="text-brand" />
            本周小结
          </div>
          <p class="mt-2 text-[10.5px] leading-[1.75] text-muted">{{ studentReport.summary }}</p>
          <div class="mt-3 flex flex-col gap-1.5">
            <RouterLink
              to="/chat"
              class="flex items-center justify-between rounded-xl border border-line bg-tint-soft px-3 py-2 text-[10px] text-subink transition-colors hover:border-line-strong"
            >
              先复习 CIDR 的块对齐
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
            <span class="text-[9px] text-muted">{{ studentReport.weakPoints.length }} 个</span>
          </header>
          <div class="p-3">
            <div
              v-for="w in studentReport.weakPoints"
              :key="w.id"
              class="mb-2 rounded-xl border border-line bg-tint-soft px-3 py-2.5 last:mb-0"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-[11px] text-subink">{{ w.label }}</span>
                <span class="shrink-0 text-[9px] text-warn">错 {{ w.wrong }} 次</span>
              </div>
              <p class="mt-0.5 text-[9px] text-muted">{{ w.hint }}</p>
            </div>
            <RouterLink
              to="/chat"
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
            <div
              v-for="a in studentReport.achievements"
              :key="a.label"
              class="flex items-center justify-between gap-2 border-b border-line pb-2.5 last:border-b-0 last:pb-0"
            >
              <span class="text-[10.5px] text-subink">{{ a.label }}</span>
              <span class="shrink-0 text-[9px] text-muted">{{ a.hint }}</span>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
