<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  ArrowRight,
  BookOpen,
  Check,
  Clock,
  FlaskConical,
  Gauge,
  Play,
  RefreshCw,
  Sparkles,
  Timer,
} from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { chapters } from '@/mock/data'
import { insights, todayTasks } from '@/mock/workbench'

const current = chapters.find((c) => c.status === 'active') ?? chapters[0]
const totalMinutes = chapters.reduce((sum, c) => sum + c.minutes, 0)
const doneMinutes = chapters.reduce((sum, c) => sum + Math.round((c.minutes * c.progress) / 100), 0)

const intensity = ref<'light' | 'standard' | 'deep'>('standard')
const includeLab = ref(false)
const replanned = ref(false)

const levels = [
  { key: 'light', label: '轻', hint: '15 分钟' },
  { key: 'standard', label: '标准', hint: '30 分钟' },
  { key: 'deep', label: '加强', hint: '45 分钟' },
] as const

const weekDone = computed(() => 2)
const weekTarget = computed(() => (intensity.value === 'light' ? 3 : intensity.value === 'standard' ? 5 : 7))

const taskIcon = { learn: BookOpen, review: RefreshCw, practice: FlaskConical }
const taskTone: Record<string, string> = {
  learn: 'bg-brand-soft text-brand',
  review: 'bg-warn/12 text-warn',
  practice: 'bg-success/12 text-success',
}

function replan() {
  replanned.value = true
  window.setTimeout(() => (replanned.value = false), 2200)
}
</script>

<template>
  <div class="animate-fade-up px-9 py-8">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="text-[26px] font-semibold leading-tight tracking-[-0.025em]">学习计划</h1>
        <p class="mt-1.5 max-w-[620px] text-[12.5px] leading-relaxed text-muted">
          计划随时会长：先按章节主线走，薄弱点和错题会自动变成今天的小任务。
        </p>
      </div>
      <button
        class="pill-btn h-9 border border-line bg-surface text-subink hover:border-line-strong hover:text-ink"
        @click="replan"
      >
        <Sparkles :size="15" />
        重新规划
      </button>
    </div>

    <div class="mt-6 grid items-start gap-4 xl:grid-cols-[1fr_320px]">
      <div class="flex flex-col gap-4">
        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-5 py-3.5">
            <div class="flex items-center gap-2">
              <Timer :size="14" class="text-muted" />
              <h2 class="text-[12.5px] font-medium">今天</h2>
            </div>
            <span class="text-[10.5px] text-muted">
              {{ todayTasks.length }} 项 ·
              {{ todayTasks.reduce((s, t) => s + t.minutes, 0) }} 分钟
            </span>
          </header>
          <div class="grid gap-2.5 p-3 md:grid-cols-3">
            <RouterLink
              v-for="t in todayTasks"
              :key="t.id"
              :to="t.target"
              class="group flex flex-col rounded-xl border px-3.5 py-3 transition-all"
              :class="
                t.highlight
                  ? 'border-brand/25 bg-brand-soft/50'
                  : 'border-line bg-tint-soft hover:border-line-strong hover:bg-surface'
              "
            >
              <div class="flex items-center justify-between">
                <span class="grid h-7 w-7 place-items-center rounded-[9px]" :class="taskTone[t.kind]">
                  <component :is="taskIcon[t.kind]" :size="13" />
                </span>
                <span class="flex items-center gap-1 text-[9.5px] text-muted">
                  <Clock :size="10" />
                  {{ t.minutes }} 分钟
                </span>
              </div>
              <p class="mt-2.5 line-clamp-2 text-[12px] font-medium leading-[1.5] text-ink">
                {{ t.title }}
              </p>
              <p class="mt-1 line-clamp-2 text-[10px] leading-relaxed text-muted">{{ t.reason }}</p>
              <span class="mt-2.5 flex items-center gap-1 text-[10px] text-brand opacity-0 transition-opacity group-hover:opacity-100">
                开始
                <ArrowRight :size="11" />
              </span>
            </RouterLink>
          </div>
        </section>

        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-5 py-3.5">
            <div class="flex items-center gap-2">
              <BookOpen :size="14" class="text-muted" />
              <h2 class="text-[12.5px] font-medium">课程主线</h2>
            </div>
            <span class="text-[10.5px] text-muted">
              {{ Math.round(doneMinutes / 60) }} / {{ Math.round(totalMinutes / 60) }} 小时
            </span>
          </header>

          <ol class="px-2.5 py-2.5">
            <li
              v-for="(ch, i) in chapters"
              :key="ch.id"
              class="rounded-xl px-2.5 py-2.5 transition-colors"
              :class="ch.status === 'active' ? 'bg-brand-soft/45' : 'hover:bg-tint-soft'"
            >
              <div class="flex items-start gap-3">
                <span
                  class="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full text-[10.5px] font-medium"
                  :class="
                    ch.status === 'done'
                      ? 'bg-success/12 text-success'
                      : ch.status === 'active'
                        ? 'bg-brand text-canvas'
                        : 'bg-tint text-muted'
                  "
                >
                  <Check v-if="ch.status === 'done'" :size="12" />
                  <template v-else>{{ ch.order }}</template>
                </span>

                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <p class="truncate text-[12.5px] font-medium text-ink">{{ ch.title }}</p>
                    <span
                      v-if="ch.status === 'active'"
                      class="shrink-0 rounded-full bg-brand/12 px-1.5 py-0.5 text-[9px] text-brand"
                    >
                      进行中
                    </span>
                    <span
                      v-else-if="ch.status === 'done'"
                      class="shrink-0 text-[9.5px] text-success"
                    >
                      已完成
                    </span>
                  </div>
                  <p class="mt-0.5 truncate text-[10.5px] text-muted">{{ ch.subtitle }}</p>

                  <div class="mt-1.5 flex items-center gap-2">
                    <div class="h-1 w-full max-w-[220px] overflow-hidden rounded-full bg-tint">
                      <div
                        class="h-full rounded-full"
                        :class="ch.status === 'done' ? 'bg-success/80' : 'bg-brand'"
                        :style="{ width: ch.progress + '%' }"
                      />
                    </div>
                    <span class="font-mono text-[9.5px] text-muted">{{ ch.progress }}%</span>
                    <span class="ml-auto flex items-center gap-1 text-[9.5px] text-muted">
                      <Clock :size="10" />
                      {{ ch.minutes }} min
                    </span>
                  </div>

                  <div v-if="ch.status === 'active'" class="mt-2 flex flex-wrap gap-1.5">
                    <span
                      v-for="(topic, ti) in ch.topics"
                      :key="topic"
                      class="flex items-center gap-1.5 rounded-full border border-line bg-surface px-2 py-0.5 text-[9.5px] text-subink"
                    >
                      <span
                        class="h-1.5 w-1.5 rounded-full"
                        :class="ti === 0 ? 'bg-success' : ti === 1 ? 'bg-warn' : 'bg-[#9AA6BE]'"
                      />
                      {{ topic }}
                    </span>
                  </div>
                </div>
              </div>
            </li>
          </ol>
        </section>
      </div>

      <div class="flex flex-col gap-4">
        <section class="surface p-4">
          <div class="flex items-center justify-between">
            <h2 class="text-[11.5px] font-medium">本周目标</h2>
            <span class="text-[9.5px] text-muted">还剩 3 天</span>
          </div>
          <div class="mt-3 flex items-end gap-2">
            <span class="text-[30px] font-semibold leading-none tracking-[-0.03em]">{{ weekDone }}</span>
            <span class="mb-0.5 text-[11px] text-muted">/ {{ weekTarget }} 个任务</span>
          </div>
          <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-tint">
            <div
              class="h-full rounded-full bg-brand transition-[width] duration-300"
              :style="{ width: (weekDone / weekTarget) * 100 + '%' }"
            />
          </div>
          <p class="mt-2 text-[10px] text-muted">完成第 3 章后，本周目标就达成了。</p>
        </section>

        <section class="surface overflow-hidden">
          <header class="flex items-center gap-2 border-b border-line px-4 py-3">
            <Gauge :size="13" class="text-muted" />
            <h2 class="text-[11.5px] font-medium">调整节奏</h2>
          </header>
          <div class="p-4">
            <div class="grid grid-cols-3 gap-1 rounded-xl bg-tint p-1">
              <button
                v-for="l in levels"
                :key="l.key"
                class="flex flex-col items-center rounded-lg py-1.5 transition-colors"
                :class="intensity === l.key ? 'bg-surface shadow-sm' : 'text-muted hover:text-subink'"
                @click="intensity = l.key"
              >
                <span class="text-[10.5px]" :class="intensity === l.key ? 'text-ink' : ''">{{ l.label }}</span>
                <span class="text-[8.5px] text-muted">{{ l.hint }}</span>
              </button>
            </div>

            <button
              class="mt-3 flex w-full items-center justify-between rounded-xl border border-line px-3 py-2.5"
              :class="includeLab ? 'border-brand/30 bg-brand-soft/40' : 'bg-tint-soft'"
              @click="includeLab = !includeLab"
            >
              <span class="flex items-center gap-2 text-[10.5px] text-subink">
                <FlaskConical :size="12" class="text-muted" />
                包含实验与抓包
              </span>
              <span
                class="h-3.5 w-6 rounded-full p-0.5 transition-colors"
                :class="includeLab ? 'bg-brand' : 'bg-line-strong'"
              >
                <span
                  class="block h-2.5 w-2.5 rounded-full bg-surface transition-transform"
                  :class="includeLab ? 'translate-x-2.5' : ''"
                />
              </span>
            </button>

            <p class="mt-3 text-[9.5px] leading-relaxed text-muted">
              调整只影响任务数量和时长，不会打乱章节顺序。
            </p>
          </div>
        </section>

        <section class="surface p-4">
          <h2 class="text-[11.5px] font-medium">章节掌握</h2>
          <div class="mt-3 flex flex-col gap-2.5">
            <div v-for="c in insights.chapterMastery" :key="c.label">
              <div class="flex items-center justify-between text-[9.5px]">
                <span class="text-subink">{{ c.label }}</span>
                <span class="font-mono text-muted">{{ c.value }}%</span>
              </div>
              <div class="mt-1 h-1 overflow-hidden rounded-full bg-tint">
                <div
                  class="h-full rounded-full"
                  :class="c.value >= 80 ? 'bg-success/70' : c.value >= 55 ? 'bg-brand' : 'bg-warn/80'"
                  :style="{ width: c.value + '%' }"
                />
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>

    <div
      v-if="replanned"
      class="pointer-events-none fixed bottom-8 left-1/2 z-50 -translate-x-1/2 rounded-full bg-ink px-3.5 py-1.5 text-[11px] text-canvas shadow-lg"
    >
      已按当前薄弱点重新排计划
    </div>
  </div>
</template>
