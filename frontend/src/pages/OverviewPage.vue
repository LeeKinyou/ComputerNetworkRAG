<script setup lang="ts">
import { computed } from 'vue'
import {
  ArrowRight,
  BookOpen,
  Calculator,
  Clock3,
  Flame,
  PenLine,
  PlayCircle,
  RefreshCw,
  ShieldCheck,
  StickyNote,
  Table2,
} from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { chapters } from '@/mock/data'
import { artifactLabel, recentArtifacts, todayTasks } from '@/mock/workbench'

const hour = new Date().getHours()
const greeting = computed(() => (hour < 6 ? '夜深了' : hour < 12 ? '早上好' : hour < 18 ? '下午好' : '晚上好'))

const current = chapters.find((c) => c.status === 'active') ?? chapters[0]
const totalMinutes = todayTasks.reduce((sum, t) => sum + t.minutes, 0)

const taskIcon = { learn: BookOpen, review: RefreshCw, practice: PenLine }
const taskTone: Record<string, string> = {
  learn: 'bg-brand-soft text-brand',
  review: 'bg-warn/12 text-warn',
  practice: 'bg-success/12 text-success',
}

const artifactIcon: Record<string, unknown> = {
  calc: Calculator,
  note: StickyNote,
  table: Table2,
}

const rhythm = [
  { day: '一', value: 42 },
  { day: '二', value: 68 },
  { day: '三', value: 35 },
  { day: '四', value: 80 },
  { day: '五', value: 54 },
  { day: '六', value: 22 },
  { day: '日', value: 61 },
]
</script>

<template>
  <div class="animate-fade-up px-9 py-8">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p class="text-[11.5px] text-muted">{{ greeting }}，李金阳 · {{ current.title }}</p>
        <h1 class="mt-1 text-[26px] font-semibold leading-tight tracking-[-0.025em]">
          今天先把网络层收个尾
        </h1>
        <p class="mt-1.5 text-[12.5px] text-muted">
          3 项任务，约 {{ totalMinutes }} 分钟。按顺序做完，第 3 章就完成了。
        </p>
      </div>
      <div class="flex items-center gap-2">
        <RouterLink
          to="/path"
          class="pill-btn h-9 border border-line bg-surface text-subink hover:border-line-strong hover:text-ink"
        >
          调整计划
        </RouterLink>
        <RouterLink
          to="/chat"
          class="pill-btn h-9 bg-ink pl-3.5 text-canvas shadow-[0_6px_16px_-8px_rgba(17,19,24,0.55)] hover:opacity-90"
        >
          <PlayCircle :size="15" />
          开始今天的学习
        </RouterLink>
      </div>
    </div>

    <div class="mt-6 grid items-start gap-4 xl:grid-cols-[1fr_320px]">
      <div class="flex flex-col gap-4">
        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-5 py-3.5">
            <h2 class="text-[12.5px] font-medium">今日任务</h2>
            <span class="text-[10.5px] text-muted">3 项 · {{ totalMinutes }} 分钟</span>
          </header>
          <ul class="p-2">
            <li v-for="(t, i) in todayTasks" :key="t.id">
              <RouterLink
                :to="t.target"
                class="group flex items-center gap-3.5 rounded-xl px-3 py-3 transition-colors"
                :class="t.highlight ? 'bg-brand-soft/60' : 'hover:bg-tint-soft'"
              >
                <span
                  class="grid h-9 w-9 shrink-0 place-items-center rounded-[11px]"
                  :class="taskTone[t.kind]"
                >
                  <component :is="taskIcon[t.kind]" :size="16" />
                </span>
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <p class="truncate text-[13px] font-medium text-ink">{{ t.title }}</p>
                    <span
                      v-if="t.highlight"
                      class="shrink-0 rounded-full bg-surface px-2 py-0.5 text-[9.5px] text-brand"
                    >
                      当前
                    </span>
                  </div>
                  <p class="mt-0.5 truncate text-[10.5px] text-muted">{{ t.reason }}</p>
                </div>
                <span class="flex shrink-0 items-center gap-1 text-[10.5px] text-muted">
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
        </section>

        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-5 py-3.5">
            <div class="flex items-center gap-2">
              <BookOpen :size="14" class="text-muted" />
              <h2 class="text-[12.5px] font-medium">继续学习</h2>
            </div>
            <span class="rounded-full bg-tint px-2 py-0.5 text-[10px] text-muted">
              第 {{ current.order }} 章
            </span>
          </header>
          <div class="p-5">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 class="text-[17px] font-semibold tracking-tight">{{ current.title }}</h3>
                <p class="mt-1 text-[11.5px] text-muted">{{ current.subtitle }}</p>
              </div>
              <span class="font-mono text-[11px] text-muted">{{ current.progress }}%</span>
            </div>

            <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-tint">
              <div class="h-full rounded-full bg-brand" :style="{ width: current.progress + '%' }" />
            </div>

            <p class="mt-3 text-[11px] text-muted">
              上次停在
              <span class="text-subink">3.2 子网掩码与地址块</span>
              ，下一步是「CIDR 与路由聚合」。
            </p>

            <div class="mt-3 flex flex-wrap gap-1.5">
              <span
                class="rounded-full border border-line bg-tint-soft px-2.5 py-1 text-[10.5px] text-subink"
              >
                子网掩码 · 已掌握
              </span>
              <span class="rounded-full border border-warn/30 bg-warn/12 px-2.5 py-1 text-[10.5px] text-warn">
                CIDR · 薄弱
              </span>
              <span class="rounded-full border border-line bg-tint-soft px-2.5 py-1 text-[10.5px] text-subink">
                路由聚合 · 未学
              </span>
            </div>

            <RouterLink
              to="/chat"
              class="pill-btn mt-4 h-9 bg-ink px-4 text-canvas hover:opacity-90"
            >
              继续第 3 章
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
            <span class="text-[10.5px] text-muted">3h 20m · 连续 9 天</span>
          </div>
          <div class="mt-4 flex items-end gap-2">
            <div v-for="d in rhythm" :key="d.day" class="flex flex-1 flex-col items-center gap-1.5">
              <div class="flex h-14 w-full items-end">
                <div
                  class="w-full rounded-[5px] bg-brand/25"
                  :style="{ height: d.value + '%' }"
                />
              </div>
              <span class="text-[9.5px] text-muted">{{ d.day }}</span>
            </div>
          </div>
        </section>
      </div>

      <div class="flex flex-col gap-4">
        <section class="surface border-warn/35 overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-4 py-3">
            <div class="flex items-center gap-1.5 text-[11.5px] text-warn">
              <ShieldCheck :size="13" />
              待你确认
            </div>
            <span class="text-[9.5px] text-muted">2 分钟前</span>
          </header>
          <div class="p-4">
            <p class="text-[12.5px] font-medium text-ink">重建第 4 章索引</p>
            <p class="mt-1 text-[10.5px] leading-relaxed text-muted">
              将替换索引 v3，影响 98 个分块的检索结果。批准后约需 40 秒。
            </p>
            <div class="mt-3 flex gap-2">
              <RouterLink
                to="/chat"
                class="pill-btn h-8 flex-1 justify-center bg-ink text-[11px] text-canvas hover:opacity-90"
              >
                去处理
              </RouterLink>
              <button
                class="pill-btn h-8 border border-line bg-surface text-[11px] text-muted hover:border-line-strong"
              >
                稍后
              </button>
            </div>
          </div>
        </section>

        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-4 py-3">
            <h2 class="text-[11.5px] font-medium">最近产物</h2>
            <RouterLink to="/profile" class="text-[10px] text-muted hover:text-ink">全部</RouterLink>
          </header>
          <ul class="p-2">
            <li v-for="a in recentArtifacts" :key="a.id">
              <RouterLink
                to="/profile"
                class="flex items-start gap-2.5 rounded-xl px-2.5 py-2.5 transition-colors hover:bg-tint-soft"
              >
                <span class="grid h-7 w-7 shrink-0 place-items-center rounded-[9px] bg-tint text-muted">
                  <component :is="artifactIcon[a.kind] ?? StickyNote" :size="13" />
                </span>
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-1.5">
                    <p class="truncate text-[11.5px] text-subink">{{ a.title }}</p>
                    <span class="shrink-0 rounded-full bg-tint px-1.5 py-0.5 text-[9px] text-muted">
                      {{ artifactLabel[a.kind] }}
                    </span>
                  </div>
                  <p class="mt-0.5 line-clamp-1 text-[10px] text-muted">{{ a.summary }}</p>
                </div>
                <span class="shrink-0 font-mono text-[9px] text-muted">{{ a.createdAt }}</span>
              </RouterLink>
            </li>
          </ul>
        </section>

        <section class="surface px-4 py-4">
          <h2 class="text-[11.5px] font-medium">班级</h2>
          <p class="mt-1 text-[10px] leading-relaxed text-muted">
            计科 2301 · 42 人。本周 3 个高频问题集中在网络层。
          </p>
          <RouterLink
            to="/insights"
            class="mt-3 flex items-center justify-between rounded-xl border border-line bg-tint-soft px-3 py-2 text-[10.5px] text-subink transition-colors hover:border-line-strong"
          >
            查看学情分析
            <ArrowRight :size="12" />
          </RouterLink>
        </section>
      </div>
    </div>
  </div>
</template>
