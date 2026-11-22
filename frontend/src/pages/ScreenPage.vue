<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  ArrowLeft,
  Check,
  ChevronRight,
  Clock3,
  Eye,
  ShieldCheck,
  Sparkles,
  Waypoints,
  Wrench,
} from 'lucide-vue-next'
import GraphCanvas from '@/components/GraphCanvas.vue'
import { categories, graphLinks, graphNodes } from '@/mock/data'
import { tasks } from '@/mock/workbench'

const task = tasks[0]
const now = ref(new Date())
const stepIndex = ref(2)
let clockTimer: number | undefined
let stepTimer: number | undefined

onMounted(() => {
  clockTimer = window.setInterval(() => (now.value = new Date()), 1000)
  stepTimer = window.setInterval(() => {
    stepIndex.value = (stepIndex.value + 1) % (task.steps.length + 1)
  }, 2600)
})
onBeforeUnmount(() => {
  if (clockTimer) window.clearInterval(clockTimer)
  if (stepTimer) window.clearInterval(stepTimer)
})

const clock = computed(() =>
  now.value.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' }),
)
const seconds = computed(() => String(now.value.getSeconds()).padStart(2, '0'))
const dateText = computed(() =>
  now.value.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' }),
)
const elapsed = computed(() => task.steps.slice(0, Math.min(stepIndex.value, task.steps.length)).reduce((s, x) => s + (x.ms ?? 0), 0))
</script>

<template>
  <div class="dark flex h-screen w-screen flex-col overflow-hidden bg-canvas text-ink">
    <header class="flex h-[62px] shrink-0 items-center justify-between border-b border-line px-7">
      <div class="flex items-center gap-3">
        <div
          class="grid h-9 w-9 place-items-center rounded-[11px] bg-gradient-to-br from-[#3d78ff] to-[#2251d6] text-white shadow-[0_6px_16px_-6px_rgba(47,107,255,0.6)]"
        >
          <Sparkles :size="17" />
        </div>
        <div>
          <div class="text-[14px] font-semibold tracking-tight">智网系统</div>
          <div class="mt-0.5 text-[10px] text-muted">一次任务正在发生</div>
        </div>
        <span class="ml-3 flex items-center gap-1.5 rounded-full bg-success/12 px-2.5 py-1 text-[10px] text-success">
          <span class="h-1.5 w-1.5 rounded-full bg-success animate-soft-pulse" />
          实时运行
        </span>
      </div>

      <div class="flex items-center gap-6">
        <div class="text-right">
          <div class="font-mono text-[21px] leading-none tracking-tight">
            {{ clock }}<span class="text-[12px] text-muted">:{{ seconds }}</span>
          </div>
          <div class="mt-1 text-[9.5px] text-muted">{{ dateText }}</div>
        </div>
        <RouterLink
          to="/"
          class="flex h-8 items-center gap-1.5 rounded-full border border-line bg-tint px-3 text-[11px] text-subink transition-colors hover:border-line-strong hover:text-ink"
        >
          <ArrowLeft :size="12" />
          退出演示
        </RouterLink>
      </div>
    </header>

    <main class="grid min-h-0 flex-1 grid-cols-[300px_1fr_336px] gap-4 p-5">
      <div class="flex min-h-0 flex-col gap-4">
        <section class="surface flex min-h-0 flex-1 flex-col overflow-hidden">
          <div class="border-b border-line px-4 py-3.5">
            <div class="flex items-center gap-1.5 text-[9.5px] text-muted">
              当前任务
              <span class="rounded-full bg-brand-soft px-1.5 py-0.5 text-brand">深度智能体</span>
            </div>
            <p class="mt-1.5 text-[12.5px] font-medium leading-snug">{{ task.title }}</p>
            <p class="mt-1 text-[9.5px] text-muted">{{ task.chapter }} · {{ elapsed }}ms</p>
          </div>

          <div class="flex min-h-0 flex-1 flex-col justify-center gap-5 p-3">
            <div
              v-for="(s, i) in task.steps"
              :key="s.id"
              class="relative flex items-start gap-2.5 rounded-lg px-1.5 py-2"
              :class="i === stepIndex ? 'bg-brand-soft/50' : ''"
            >
              <span class="relative z-10 mt-1 grid h-4 w-4 shrink-0 place-items-center rounded-full border border-line bg-surface">
                <Check v-if="i < stepIndex" :size="9" class="text-success" />
                <span
                  v-else-if="i === stepIndex"
                  class="h-1.5 w-1.5 rounded-full bg-brand animate-soft-pulse"
                />
                <span v-else class="h-1 w-1 rounded-full bg-line-strong" />
              </span>
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-1.5 text-[10px]">
                  <Wrench v-if="s.kind === 'action'" :size="10" class="text-brand" />
                  <Eye v-else-if="s.kind === 'observation'" :size="10" class="text-success" />
                  <Sparkles v-else :size="10" class="text-muted" />
                  <span :class="i <= stepIndex ? 'text-subink' : 'text-muted'">{{ s.title }}</span>
                </div>
                <p v-if="s.detail" class="mt-0.5 line-clamp-2 text-[9px] leading-snug text-muted">
                  {{ s.detail }}
                </p>
              </div>
              <span v-if="s.ms" class="shrink-0 font-mono text-[8.5px] text-muted">{{ s.ms }}ms</span>
            </div>
          </div>
        </section>

        <section class="surface grid grid-cols-3 divide-x divide-line">
          <div class="px-3 py-3">
            <div class="text-[9px] text-muted">今日任务</div>
            <div class="mt-1 text-[20px] font-semibold leading-none">3</div>
          </div>
          <div class="px-3 py-3">
            <div class="text-[9px] text-muted">工具调用</div>
            <div class="mt-1 text-[20px] font-semibold leading-none">76</div>
          </div>
          <div class="px-3 py-3">
            <div class="text-[9px] text-muted">索引覆盖</div>
            <div class="mt-1 text-[20px] font-semibold leading-none">98%</div>
          </div>
        </section>

        <section class="surface shrink-0 px-3.5 py-3">
          <div class="flex items-center gap-1.5 text-[10px] text-success">
            <span class="h-1.5 w-1.5 rounded-full bg-success" />
            系统正常 · lite 单进程
          </div>
          <div class="mt-2 flex justify-between text-[9px] text-muted">
            <span>索引 v3</span>
            <span>BGE-M3</span>
            <span>P95 1.4s</span>
          </div>
        </section>
      </div>

      <section class="surface flex min-h-0 flex-col overflow-hidden">
        <header class="flex items-center justify-between border-b border-line px-4 py-3">
          <div class="flex items-center gap-2">
            <Waypoints :size="14" class="text-muted" />
            <h2 class="text-[11.5px] font-medium">命中知识点</h2>
          </div>
          <div class="flex items-center gap-1.5">
            <span class="rounded-full bg-brand-soft px-2 py-0.5 text-[9.5px] text-brand">IPv4</span>
            <span class="rounded-full bg-tint px-2 py-0.5 text-[9.5px] text-muted">子网掩码</span>
            <span class="text-[9px] text-muted">18 / 21</span>
          </div>
        </header>
        <div class="min-h-0 flex-1">
          <GraphCanvas
            :nodes="graphNodes"
            :links="graphLinks"
            :categories="categories"
            selected-id="ipv4"
            force-dark
          />
        </div>
        <div class="flex items-center justify-between border-t border-line px-4 py-2.5 text-[9.5px] text-muted">
          <span>检索 5 个片段 · 2 份文档 · RRF 融合</span>
          <span class="font-mono">score 0.94</span>
        </div>
      </section>

      <div class="flex min-h-0 flex-col gap-4">
        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-3.5 py-2.5">
            <div class="flex items-center gap-1.5">
              <Sparkles :size="12" class="text-brand" />
              <h2 class="text-[11px] font-medium">产物预览</h2>
            </div>
            <span class="rounded-full bg-tint px-1.5 py-0.5 text-[8.5px] text-muted">计算卡</span>
          </header>
          <div class="p-3.5">
            <p class="text-[9.5px] text-muted">192.168.10.137 / 27</p>
            <div class="mt-2 flex gap-1">
              <div v-for="i in 6" :key="i" class="h-5 flex-1 rounded-sm" :class="i === 5 ? 'bg-brand' : 'bg-tint'" />
            </div>
            <div class="mt-3 grid grid-cols-3 gap-2">
              <div>
                <div class="text-[8.5px] text-muted">网络地址</div>
                <div class="mt-0.5 font-mono text-[10px]">10.128</div>
              </div>
              <div>
                <div class="text-[8.5px] text-muted">广播</div>
                <div class="mt-0.5 font-mono text-[10px]">10.159</div>
              </div>
              <div>
                <div class="text-[8.5px] text-muted">可用</div>
                <div class="mt-0.5 font-mono text-[10px]">30</div>
              </div>
            </div>
          </div>
        </section>

        <section class="surface border-warn/30 px-3.5 py-3">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-1.5 text-[10px] text-warn">
              <ShieldCheck :size="12" />
              待人工审批
            </div>
            <span class="flex items-center gap-1 text-[8.5px] text-muted">
              <Clock3 :size="9" />
              2 分钟
            </span>
          </div>
          <p class="mt-1.5 text-[10px] leading-snug text-subink">重建第 4 章索引，影响 98 个分块</p>
          <div class="mt-2 flex items-center justify-between rounded-lg border border-line bg-tint-soft px-2 py-1.5 text-[9px] text-muted">
            <span>等待确认</span>
            <ChevronRight :size="10" />
          </div>
        </section>

        <section class="surface flex min-h-0 flex-1 flex-col overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-3.5 py-2.5">
            <h2 class="text-[11px] font-medium">最近问答</h2>
            <span class="text-[9px] text-muted">今日 23 次</span>
          </header>
          <ul class="min-h-0 flex-1 overflow-hidden p-2">
            <li
              v-for="t in [task, tasks[1], tasks[2], tasks[4], tasks[3]]"
              :key="t.id"
              class="rounded-lg px-2 py-2 transition-colors hover:bg-tint-soft"
            >
              <div class="flex items-start gap-2">
                <span class="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-success" />
                <div class="min-w-0">
                  <p class="line-clamp-2 text-[10px] leading-snug text-subink">{{ t.title }}</p>
                  <p class="mt-0.5 text-[8.5px] text-muted">{{ t.createdAt }} · {{ t.steps.length }} 步</p>
                </div>
              </div>
            </li>
          </ul>
        </section>
      </div>
    </main>
  </div>
</template>
