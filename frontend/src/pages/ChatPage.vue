<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  Activity,
  ArrowUp,
  AtSign,
  Check,
  ChevronDown,
  Circle,
  Copy,
  Eye,
  FileText,
  ListChecks,
  Package,
  Plus,
  Quote,
  Search,
  ShieldAlert,
  Sparkles,
  Square,
  StickyNote,
  Wrench,
  Zap,
} from 'lucide-vue-next'
import type { Task } from '@/mock/workbench'
import { artifactLabel, tasks as seedTasks } from '@/mock/workbench'

const route = useRoute()
const localTasks = ref<Task[]>(JSON.parse(JSON.stringify(seedTasks)))
const selectedId = ref<string>(seedTasks[0].id)
const draft = ref(false)
const input = ref(typeof route.query.q === 'string' ? route.query.q : '')
const tab = ref<'plan' | 'artifact' | 'source'>('plan')
const stepsOpen = ref(false)
const prefix = ref(27)
const toast = ref('')
const savedIds = ref<string[]>([])
const mode = ref<'rag' | 'agent'>(route.query.mode === 'rag' ? 'rag' : 'agent')
const tabs = [
  { key: 'plan' as const, label: '计划', icon: ListChecks },
  { key: 'artifact' as const, label: '产物', icon: Package },
  { key: 'source' as const, label: '来源', icon: Quote },
]

const groups = computed(() => {
  const map = new Map<string, Task[]>()
  for (const t of localTasks.value) {
    const list = map.get(t.group) ?? []
    list.push(t)
    map.set(t.group, list)
  }
  return [...map.entries()]
})

const activeTask = computed(() => localTasks.value.find((t) => t.id === selectedId.value) ?? null)
const totalMs = computed(() => activeTask.value?.steps.reduce((s, x) => s + (x.ms ?? 0), 0) ?? 0)
const toolCount = computed(
  () => activeTask.value?.steps.filter((s) => s.kind === 'action').length ?? 0,
)
const hasCalc = computed(() => activeTask.value?.artifacts.some((a) => a.kind === 'calc') ?? false)

function ipToInt(ip: string): number {
  return ip.split('.').reduce((acc, part) => ((acc << 8) + Number(part)) >>> 0, 0) >>> 0
}
function intToIp(n: number): string {
  return [24, 16, 8, 0].map((shift) => (n >>> shift) & 255).join('.')
}
const calc = computed(() => {
  const ip = ipToInt('192.168.10.137')
  const mask = prefix.value >= 32 ? 0xffffffff : ((0xffffffff << (32 - prefix.value)) >>> 0)
  const network = (ip & mask) >>> 0
  const broadcast = (network | (~mask >>> 0)) >>> 0
  const size = 2 ** (32 - prefix.value)
  const usable = prefix.value >= 31 ? 0 : Math.max(size - 2, 0)
  return {
    network: intToIp(network),
    broadcast: intToIp(broadcast),
    first: intToIp(network + 1),
    last: intToIp(broadcast - 1),
    usable,
    block: size,
    base: prefix.value,
  }
})

const blocks = computed(() => {
  const size = 2 ** (32 - prefix.value)
  const start = Math.floor(ipToInt('192.168.10.137') / size) * size
  return Array.from({ length: 6 }, (_, i) => {
    const addr = start - size * 2 + i * size
    return { label: intToIp(addr >>> 0).split('.').pop() ?? '0', active: addr === start }
  })
})

watch(selectedId, () => {
  stepsOpen.value = false
  prefix.value = 27
  mode.value = activeTask.value?.mode ?? 'agent'
  tab.value = 'plan'
})

function notify(text: string) {
  toast.value = text
  window.setTimeout(() => {
    if (toast.value === text) toast.value = ''
  }, 2200)
}

function newTask() {
  draft.value = true
  selectedId.value = ''
  input.value = ''
}

function saveNote() {
  if (!activeTask.value) return
  if (savedIds.value.includes(activeTask.value.id)) return
  savedIds.value.push(activeTask.value.id)
  activeTask.value.artifacts.push({
    id: `art_note_${Date.now()}`,
    kind: 'note',
    title: '子网划分速记（自动归档）',
    summary: `前缀 /${prefix.value} · 网络地址 ${calc.value.network} · 可用 ${calc.value.usable} 个`,
    meta: '来自本次任务',
    taskId: activeTask.value.id,
    createdAt: '刚刚',
  })
  tab.value = 'artifact'
  notify('已存为笔记，可在「我的」查看')
}

function makeQuiz() {
  if (!activeTask.value) return
  activeTask.value.artifacts.push({
    id: `art_quiz_${Date.now()}`,
    kind: 'quiz',
    title: '子网划分练习（3 题）',
    summary: '由本次任务生成，覆盖 /27 与 /28 的地址块计算',
    taskId: activeTask.value.id,
    createdAt: '刚刚',
  })
  tab.value = 'artifact'
  notify('已生成 3 道练习')
}

function copyAnswer() {
  const text = activeTask.value?.answer ?? ''
  if (!text) return
  navigator.clipboard?.writeText(text)
  notify('已复制回答')
}

function send() {
  const text = input.value.trim()
  if (!text) return
  const id = `task_new_${Date.now()}`
  localTasks.value.unshift({
    id,
    title: text.length > 26 ? `${text.slice(0, 26)}…` : text,
    question: text,
    course: '计算机网络',
    chapter: '第 3 章 · 网络层',
    mode: mode.value,
    status: 'done',
    createdAt: '刚刚',
    group: '今天',
    plan: [
      { id: 'p1', label: '理解问题与上下文', state: 'done' },
      { id: 'p2', label: mode.value === 'rag' ? '检索课程资料' : '规划并调用工具', state: 'done' },
      { id: 'p3', label: '组织回答与出处', state: 'done' },
    ],
    steps: [
      { id: 's1', kind: 'thought', title: '已理解问题', detail: text, ms: 110 },
      {
        id: 's2',
        kind: 'action',
        title: mode.value === 'rag' ? 'hybrid_retrieve' : 'search_course',
        detail: 'top_k=5 · 混合检索 · 索引 v3',
        ms: 324,
        status: 'ok',
      },
      { id: 's3', kind: 'observation', title: '命中 5 个课程片段', detail: '教材 §4.4、RFC 950', ms: 40 },
    ],
    artifacts: [],
    sources: seedTasks[0].sources,
    answer: '（演示骨架）这是一个新任务。接入后端后，这里会流式输出带引用的回答，并把检索片段列入右侧「来源」。',
  })
  selectedId.value = id
  draft.value = false
  input.value = ''
  notify('任务已创建')
}
</script>

<template>
  <div class="flex h-full min-h-0">
    <aside class="hidden w-[232px] shrink-0 flex-col border-r border-line bg-shell xl:flex">
      <div class="flex h-12 items-center justify-between px-3.5">
        <span class="text-[11.5px] font-medium text-muted">任务</span>
        <button class="icon-btn" aria-label="新建任务" @click="newTask"><Plus :size="15" /></button>
      </div>

      <div class="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        <div v-for="[group, list] in groups" :key="group" class="mb-3">
          <p class="px-2.5 pb-1 text-[9.5px] uppercase tracking-[0.08em] text-muted">{{ group }}</p>
          <button
            v-for="t in list"
            :key="t.id"
            class="mb-0.5 flex w-full flex-col gap-1 rounded-xl px-2.5 py-2 text-left transition-colors"
            :class="
              selectedId === t.id && !draft
                ? 'bg-surface shadow-[0_1px_2px_rgba(16,24,40,0.05)]'
                : 'hover:bg-surface/60'
            "
            @click="selectedId = t.id; draft = false"
          >
            <div class="flex items-center gap-1.5">
              <span
                class="h-1.5 w-1.5 shrink-0 rounded-full"
                :class="
                  t.status === 'done'
                    ? 'bg-success'
                    : t.status === 'waiting_approval'
                      ? 'bg-warn'
                      : 'bg-brand'
                "
              />
              <span
                class="line-clamp-2 flex-1 text-[12px] leading-[1.45]"
                :class="selectedId === t.id && !draft ? 'font-medium text-ink' : 'text-subink'"
              >
                {{ t.title }}
              </span>
            </div>
            <div class="flex items-center gap-1.5 pl-3">
              <span class="rounded-full bg-tint px-1.5 py-[1px] text-[9px] text-muted">
                {{ t.mode === 'rag' ? '快速' : '深度' }}
              </span>
              <span class="text-[9.5px] text-muted">{{ t.createdAt }}</span>
              <span
                v-if="t.status === 'waiting_approval'"
                class="rounded-full bg-warn/12 px-1.5 py-[1px] text-[9px] text-warn"
              >
                待审批
              </span>
            </div>
          </button>
        </div>
      </div>

      <div class="border-t border-line p-2.5">
        <button
          class="flex w-full items-center justify-center gap-1.5 rounded-xl border border-dashed border-line-strong py-2 text-[11px] text-muted transition-colors hover:border-brand/40 hover:text-brand"
          @click="newTask"
        >
          <Plus :size="13" />
          新建任务
        </button>
      </div>
    </aside>

    <section class="flex min-w-0 flex-1 flex-col bg-surface">
      <header class="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-line px-5">
        <div class="flex min-w-0 items-center gap-2">
          <span class="grid h-6 w-6 shrink-0 place-items-center rounded-[8px] bg-brand-soft text-brand">
            <Sparkles :size="13" />
          </span>
          <span class="truncate text-[12.5px] font-medium">
            {{ draft ? '新任务' : activeTask?.title ?? '新任务' }}
          </span>
          <span class="hidden shrink-0 rounded-full border border-line px-2 py-0.5 text-[10px] text-muted md:inline">
            {{ activeTask?.chapter ?? '第 3 章 · 网络层' }}
          </span>
          <span
            v-if="activeTask?.status === 'waiting_approval'"
            class="shrink-0 rounded-full bg-warn/12 px-2 py-0.5 text-[10px] text-warn"
          >
            待审批
          </span>
        </div>
        <div class="flex shrink-0 items-center gap-1 rounded-full bg-tint p-0.5">
          <button
            class="rounded-full px-2.5 py-1 text-[10.5px] transition-colors"
            :class="mode === 'rag' ? 'bg-surface text-ink shadow-sm' : 'text-muted hover:text-subink'"
            @click="mode = 'rag'"
          >
            快速检索
          </button>
          <button
            class="rounded-full px-2.5 py-1 text-[10.5px] transition-colors"
            :class="mode === 'agent' ? 'bg-surface text-ink shadow-sm' : 'text-muted hover:text-subink'"
            @click="mode = 'agent'"
          >
            深度智能体
          </button>
        </div>
      </header>

      <div class="min-h-0 flex-1 overflow-y-auto px-5 py-5">
        <div v-if="draft || !activeTask" class="mx-auto flex h-full w-full max-w-[720px] flex-col justify-center pb-10">
          <div class="grid h-11 w-11 place-items-center rounded-[13px] bg-brand-soft text-brand">
            <Sparkles :size="20" />
          </div>
          <h2 class="mt-4 text-[19px] font-semibold tracking-tight">要解决哪个问题？</h2>
          <p class="mt-1.5 max-w-[460px] text-[12px] leading-relaxed text-muted">
            提问会创建一个任务：右侧同步生成计划，过程可回放，结论可以存成笔记或练习。
          </p>
          <div class="mt-5 grid gap-2 sm:grid-cols-2">
            <button
              v-for="q in ['计算 192.168.10.137/27 的子网范围', 'TCP 为什么需要三次握手', '对比 CSMA/CD 与 CSMA/CA', 'CIDR 路由聚合怎么算']"
              :key="q"
              class="rounded-xl border border-line bg-tint-soft px-3.5 py-2.5 text-left text-[11.5px] text-subink transition-all hover:border-line-strong hover:bg-surface"
              @click="input = q"
            >
              {{ q }}
            </button>
          </div>
        </div>

        <div v-else class="mx-auto flex w-full max-w-[800px] flex-col gap-4">
          <div class="flex justify-end">
            <div class="max-w-[78%]">
              <div class="rounded-[16px] rounded-tr-[5px] bg-tint px-4 py-2.5 text-[12.5px] leading-relaxed text-subink">
                {{ activeTask.question }}
              </div>
              <div class="mt-1 text-right text-[10px] text-muted">{{ activeTask.createdAt }}</div>
            </div>
          </div>

          <div class="w-full">
            <div class="flex items-center gap-2 text-[10.5px] text-muted">
              <span class="grid h-5 w-5 place-items-center rounded-md bg-brand-soft text-brand">
                <Sparkles :size="12" />
              </span>
              智能助教 · {{ activeTask.mode === 'rag' ? '检索模式' : '智能体模式' }}
            </div>

            <div
              v-if="activeTask.steps.length"
              class="mt-2.5 overflow-hidden rounded-xl border border-line bg-tint-soft"
            >
              <button
                class="flex w-full items-center justify-between px-3.5 py-2.5 text-[11px] text-muted transition-colors hover:text-subink"
                @click="stepsOpen = !stepsOpen"
              >
                <span class="flex items-center gap-1.5">
                  <Activity :size="12" />
                  {{ activeTask.steps.length }} 步 · {{ totalMs }}ms · {{ toolCount }} 次工具调用
                </span>
                <ChevronDown :size="13" :class="['transition-transform', stepsOpen ? 'rotate-180' : '']" />
              </button>

              <ol v-if="stepsOpen" class="relative flex flex-col gap-3 border-t border-line px-3.5 py-3 pl-8">
                <span class="absolute bottom-4 left-[18px] top-4 w-px bg-line" />
                <li v-for="s in activeTask.steps" :key="s.id" class="relative">
                  <span
                    class="absolute -left-[20px] top-0.5 grid h-3 w-3 place-items-center rounded-full border border-line bg-surface"
                  >
                    <span
                      class="h-1 w-1 rounded-full"
                      :class="s.kind === 'action' ? 'bg-brand' : s.kind === 'observation' ? 'bg-success' : s.kind === 'approval' ? 'bg-warn' : 'bg-line-strong'"
                    />
                  </span>
                  <div class="flex items-start justify-between gap-2">
                    <span class="flex items-center gap-1.5 text-[11px] font-medium text-subink">
                      <Wrench v-if="s.kind === 'action'" :size="11" class="text-brand" />
                      <Eye v-else-if="s.kind === 'observation'" :size="11" class="text-success" />
                      <ShieldAlert v-else-if="s.kind === 'approval'" :size="11" class="text-warn" />
                      <Sparkles v-else :size="11" class="text-muted" />
                      {{ s.title }}
                    </span>
                    <span v-if="s.ms" class="shrink-0 font-mono text-[9.5px] text-muted">{{ s.ms }}ms</span>
                  </div>
                  <p v-if="s.detail" class="mt-0.5 break-words text-[10.5px] leading-relaxed text-muted">
                    {{ s.detail }}
                  </p>
                </li>
              </ol>
            </div>

            <div
              v-if="activeTask.status === 'waiting_approval'"
              class="mt-4 overflow-hidden rounded-xl border border-warn/35 bg-warn/8"
            >
              <div class="flex items-center gap-1.5 border-b border-warn/20 px-3.5 py-2.5 text-[11px] font-medium text-warn">
                <ShieldAlert :size="13" />
                这个动作需要你确认
              </div>
              <div class="px-3.5 py-3">
                <p class="text-[12px] font-medium text-ink">重建课程索引（v3 → v4）</p>
                <p class="mt-1 text-[10.5px] leading-relaxed text-muted">
                  将替换 98 个分块的向量与 BM25 索引，期间检索结果可能短暂不一致。
                </p>
                <div class="mt-3 flex gap-2">
                  <button class="pill-btn h-8 bg-ink px-3 text-[11px] text-canvas" @click="notify('已批准，索引重建中')">
                    <Check :size="12" />
                    批准
                  </button>
                  <button class="pill-btn h-8 border border-line bg-surface px-3 text-[11px] text-muted" @click="notify('已转为手动模式')">
                    修改
                  </button>
                  <button class="pill-btn h-8 border border-line bg-surface px-3 text-[11px] text-muted" @click="notify('已拒绝本次操作')">
                    拒绝
                  </button>
                </div>
              </div>
            </div>

            <template v-else>
              <p class="mt-3 text-[13px] leading-[1.85] text-subink">
                {{ activeTask.answer }}
              </p>

              <div v-if="hasCalc" class="mt-3.5 overflow-hidden rounded-xl border border-line bg-surface">
                <div class="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
                  <span class="text-[10.5px] font-medium text-subink">地址空间 · /{{ prefix }}</span>
                  <div class="flex items-center gap-1.5">
                    <button
                      class="grid h-6 w-6 place-items-center rounded-lg border border-line text-muted hover:border-line-strong"
                      :disabled="prefix <= 24"
                      @click="prefix = Math.max(24, prefix - 1)"
                    >
                      <span class="text-[13px] leading-none">−</span>
                    </button>
                    <span class="w-6 text-center font-mono text-[10.5px] text-subink">{{ prefix }}</span>
                    <button
                      class="grid h-6 w-6 place-items-center rounded-lg border border-line text-muted hover:border-line-strong"
                      :disabled="prefix >= 30"
                      @click="prefix = Math.min(30, prefix + 1)"
                    >
                      <span class="text-[13px] leading-none">+</span>
                    </button>
                  </div>
                </div>

                <div class="px-4 py-3">
                  <div class="flex items-center gap-1">
                    <div
                      v-for="(b, i) in blocks"
                      :key="i"
                      class="flex h-7 flex-1 items-center justify-center rounded-[5px] font-mono text-[9px]"
                      :class="b.active ? 'bg-brand text-canvas' : 'bg-tint text-muted'"
                    >
                      .{{ b.label }}
                    </div>
                  </div>
                  <div class="mt-3 grid grid-cols-3 gap-2">
                    <div>
                      <div class="text-[9.5px] text-muted">网络地址</div>
                      <div class="mt-0.5 font-mono text-[11px] text-ink">{{ calc.network }}</div>
                    </div>
                    <div>
                      <div class="text-[9.5px] text-muted">广播地址</div>
                      <div class="mt-0.5 font-mono text-[11px] text-ink">{{ calc.broadcast }}</div>
                    </div>
                    <div>
                      <div class="text-[9.5px] text-muted">可用主机</div>
                      <div class="mt-0.5 font-mono text-[11px] text-ink">{{ calc.usable }} 个</div>
                    </div>
                  </div>
                  <p class="mt-3 font-mono text-[10px] text-muted">
                    {{ calc.first }} – {{ calc.last }} · 块大小 {{ calc.block }}
                  </p>
                </div>
              </div>

              <div class="mt-3.5 flex flex-wrap items-center gap-1.5">
                <button
                  class="pill-btn h-7 border border-line bg-surface px-2.5 text-[10.5px] text-subink hover:border-line-strong"
                  @click="saveNote"
                >
                  <StickyNote :size="11" />
                  {{ savedIds.includes(activeTask.id) ? '已存为笔记' : '存为笔记' }}
                </button>
                <button
                  class="pill-btn h-7 border border-line bg-surface px-2.5 text-[10.5px] text-subink hover:border-line-strong"
                  @click="makeQuiz"
                >
                  <Zap :size="11" />
                  出 3 道题
                </button>
                <button
                  class="pill-btn h-7 border border-line bg-surface px-2.5 text-[10.5px] text-subink hover:border-line-strong"
                  @click="notify('已加入今日任务')"
                >
                  <ListChecks :size="11" />
                  加入今日任务
                </button>
                <button
                  class="pill-btn h-7 border border-line bg-surface px-2.5 text-[10.5px] text-muted hover:border-line-strong"
                  @click="copyAnswer"
                >
                  <Copy :size="11" />
                  复制
                </button>
              </div>
            </template>
          </div>
        </div>
      </div>

      <div class="shrink-0 border-t border-line bg-surface px-5 py-3">
        <div class="mx-auto w-full max-w-[800px]">
          <div class="flex items-end gap-2 rounded-[16px] border border-line bg-surface px-3 py-2.5 shadow-[0_2px_10px_-6px_rgba(16,24,40,0.12)] focus-within:border-brand/45 focus-within:ring-2 focus-within:ring-brand/10">
            <button class="icon-btn h-7 w-7" aria-label="引用文档或知识点" @click="notify('已打开引用选择器')">
              <AtSign :size="14" />
            </button>
            <input
              v-model="input"
              type="text"
              placeholder="继续追问，或换一个前缀试试，例如：换成 /28 呢？"
              class="h-7 min-w-0 flex-1 bg-transparent text-[12.5px] outline-none placeholder:text-muted"
              @keydown.enter="send"
            />
            <button
              class="grid h-[28px] w-[28px] shrink-0 place-items-center rounded-full bg-ink text-canvas transition-all hover:opacity-90 active:scale-95 disabled:opacity-30"
              :disabled="!input.trim()"
              @click="send"
            >
              <ArrowUp :size="13" />
            </button>
          </div>
          <div class="mt-1.5 flex items-center justify-between text-[9.5px] text-muted">
            <span>Enter 发送 · Shift+Enter 换行</span>
            <span class="flex items-center gap-1">
              <Square :size="9" />
              回答有引用，关键结论请对照原文
            </span>
          </div>
        </div>
      </div>
    </section>

    <aside class="hidden w-[320px] shrink-0 flex-col border-l border-line bg-shell xl:flex">
      <div class="flex h-12 shrink-0 items-center gap-0.5 border-b border-line px-2">
        <button
          v-for="t in tabs"
          :key="t.key"
          class="flex flex-1 items-center justify-center gap-1.5 rounded-lg py-1.5 text-[10.5px] transition-colors"
          :class="tab === t.key ? 'bg-surface text-ink shadow-sm' : 'text-muted hover:text-subink'"
          @click="tab = t.key"
        >
          <component :is="t.icon" :size="12" />
          {{ t.label }}
          <span v-if="t.key === 'artifact' && activeTask" class="text-[9px] text-muted">
            {{ activeTask.artifacts.length }}
          </span>
          <span v-if="t.key === 'source' && activeTask" class="text-[9px] text-muted">
            {{ activeTask.sources.length }}
          </span>
        </button>
      </div>

      <div class="min-h-0 flex-1 overflow-y-auto p-3">
        <div v-if="!activeTask" class="pt-16 text-center text-[11px] text-muted">
          创建任务后，这里会出现计划、产物与来源。
        </div>

        <template v-else>
          <div v-if="tab === 'plan'">
            <div class="mb-2 flex items-center justify-between px-1">
              <span class="text-[10px] text-muted">本次任务的执行计划</span>
              <span class="font-mono text-[9.5px] text-muted">{{ totalMs }}ms</span>
            </div>
            <ol class="flex flex-col gap-0.5">
              <li
                v-for="p in activeTask.plan"
                :key="p.id"
                class="flex items-start gap-2.5 rounded-lg px-1.5 py-2"
              >
                <span
                  class="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border"
                  :class="
                    p.state === 'done'
                      ? 'border-success/30 bg-success/12 text-success'
                      : p.state === 'active'
                        ? 'border-brand/40 bg-brand-soft text-brand'
                        : 'border-line text-muted'
                  "
                >
                  <Check v-if="p.state === 'done'" :size="10" />
                  <Circle v-else-if="p.state === 'active'" :size="7" class="animate-soft-pulse" />
                </span>
                <span
                  class="text-[11px] leading-[1.5]"
                  :class="p.state === 'todo' ? 'text-muted' : 'text-subink'"
                >
                  {{ p.label }}
                </span>
              </li>
            </ol>
            <div class="mt-2 rounded-xl border border-line bg-tint-soft px-3 py-2.5">
              <div class="flex items-center gap-1.5 text-[10px] text-muted">
                <Search :size="11" />
                检索命中 5 个片段 · 2 份文档 · 索引 v3
              </div>
            </div>
          </div>

          <div v-else-if="tab === 'artifact'" class="flex flex-col gap-2">
            <div v-if="!activeTask.artifacts.length" class="pt-14 text-center text-[11px] text-muted">
              还没有产物。回答下方的操作会生成产物。
            </div>
            <div
              v-for="a in activeTask.artifacts"
              :key="a.id"
              class="rounded-xl border border-line bg-surface px-3 py-2.5 transition-colors hover:border-line-strong"
            >
              <div class="flex items-start justify-between gap-2">
                <span class="text-[11.5px] font-medium text-ink">{{ a.title }}</span>
                <span class="shrink-0 rounded-full bg-tint px-1.5 py-0.5 text-[9px] text-muted">
                  {{ artifactLabel[a.kind] }}
                </span>
              </div>
              <p class="mt-1 text-[10px] leading-relaxed text-muted">{{ a.summary }}</p>
              <div class="mt-2 flex items-center gap-2">
                <button class="text-[9.5px] text-brand hover:underline" @click="notify('已打开产物')">打开</button>
                <button class="text-[9.5px] text-muted hover:text-subink" @click="notify('已导出')">导出</button>
                <span class="ml-auto text-[9px] text-muted">{{ a.createdAt }}</span>
              </div>
            </div>
          </div>

          <div v-else class="flex flex-col gap-2">
            <div class="mb-1 flex items-center justify-between px-1">
              <span class="text-[10px] text-muted">引用原文</span>
              <span class="text-[9px] text-muted">点击定位</span>
            </div>
            <button
              v-for="s in activeTask.sources"
              :key="s.id"
              class="rounded-xl border border-line bg-surface px-3 py-2.5 text-left transition-colors hover:border-brand/35"
              @click="notify(`已定位到 ${s.locator}`)"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="flex min-w-0 items-center gap-1.5 text-[10.5px] text-subink">
                  <FileText :size="11" class="shrink-0 text-muted" />
                  <span class="truncate">{{ s.doc }}</span>
                </span>
                <span class="shrink-0 font-mono text-[9px] text-muted">{{ s.score.toFixed(2) }}</span>
              </div>
              <p class="mt-0.5 text-[9px] text-muted">{{ s.locator }}</p>
              <p class="mt-1.5 line-clamp-3 text-[10px] leading-relaxed text-muted">{{ s.text }}</p>
              <div class="mt-1.5 h-1 overflow-hidden rounded-full bg-tint">
                <div class="h-full rounded-full bg-brand/60" :style="{ width: s.score * 100 + '%' }" />
              </div>
            </button>
          </div>
        </template>
      </div>

      <div class="shrink-0 border-t border-line p-2.5">
        <div class="flex items-center justify-between rounded-xl bg-tint-soft px-3 py-2">
          <span class="text-[9.5px] text-muted">任务 ID</span>
          <span class="font-mono text-[9px] text-subink">{{ activeTask?.id ?? '—' }}</span>
        </div>
      </div>
    </aside>

    <div
      v-if="toast"
      class="pointer-events-none fixed bottom-20 left-1/2 z-50 -translate-x-1/2 rounded-full bg-ink px-3.5 py-1.5 text-[11px] text-canvas shadow-lg"
    >
      {{ toast }}
    </div>
  </div>
</template>
