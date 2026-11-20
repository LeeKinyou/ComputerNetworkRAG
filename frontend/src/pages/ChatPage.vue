<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import MarkdownIt from 'markdown-it'
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
import type { Artifact, SourceRef, Task } from '@/mock/workbench'
import { artifactLabel, tasks as seedTasks } from '@/mock/workbench'
import {
  ApiError,
  api,
  streamRunEvents,
  type Card,
  type Evidence,
  type RunDetail,
  type RunEventPayload,
  type SessionSummary,
} from '@/api/client'

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
const sessions = ref<SessionSummary[]>([])
const streaming = ref(false)
const demoIds = new Set(seedTasks.map((item) => item.id))
const markdown = new MarkdownIt({ html: false, linkify: true, breaks: true })
const renderedAnswer = computed(() => markdown.render(activeTask.value?.answer ?? ''))
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
const hasCalc = computed(
  () =>
    Boolean(activeTask.value?.calc) ||
    (activeTask.value?.artifacts.some((a) => a.kind === 'calc') ?? false),
)
const docCount = computed(
  () => new Set((activeTask.value?.sources ?? []).map((item) => item.doc)).size,
)

function ipToInt(ip: string): number {
  return ip.split('.').reduce((acc, part) => ((acc << 8) + Number(part)) >>> 0, 0) >>> 0
}
function intToIp(n: number): string {
  return [24, 16, 8, 0].map((shift) => (n >>> shift) & 255).join('.')
}
const calc = computed(() => {
  const ip = ipToInt(activeTask.value?.calc?.ip ?? '192.168.10.137')
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
  const start = Math.floor(ipToInt(activeTask.value?.calc?.ip ?? '192.168.10.137') / size) * size
  return Array.from({ length: 4 }, (_, i) => {
    const addr = start + i * size
    return { label: intToIp(addr >>> 0).split('.').pop() ?? '0', active: i === 0 }
  })
})

watch(selectedId, () => {
  stepsOpen.value = false
  prefix.value = activeTask.value?.calc?.prefix ?? 27
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
  if (!text || streaming.value) return
  void ask(text)
}

onMounted(() => {
  void loadSessions()
})

function statusOf(raw: string): Task['status'] {
  if (raw === 'waiting_user') return 'waiting_approval'
  if (raw === 'queued' || raw === 'running') return 'running'
  if (raw === 'failed' || raw === 'cancelled') return raw === 'failed' ? 'failed' : 'done'
  return 'done'
}

function timeOf(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '刚刚'
  const now = new Date()
  if (date.toDateString() === now.toDateString()) {
    return `今天 ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
  }
  return `${date.getMonth() + 1}/${date.getDate()}`
}

function taskFromSession(item: SessionSummary): Task | null {
  const run = item.last_run
  if (!run) return null
  return {
    id: run.run_id,
    title: item.title || run.question.slice(0, 24),
    question: run.question,
    course: '计算机网络',
    chapter: '第 4 章 · 网络层',
    mode: run.mode === 'rag' ? 'rag' : 'agent',
    status: statusOf(run.status),
    createdAt: timeOf(run.created_at),
    group: '今天',
    plan: [],
    steps: [],
    artifacts: [],
    sources: [],
    answer: '',
  }
}

async function loadSessions() {
  try {
    const result = await api.get<{ items: SessionSummary[] }>(
      '/chat-sessions?course_id=course_cn',
    )
    sessions.value = result.items
    const real = result.items
      .map(taskFromSession)
      .filter((item): item is Task => item !== null)
    if (real.length) {
      localTasks.value = [...real, ...localTasks.value.filter((item) => demoIds.has(item.id))]
      if (!selectedId.value || localTasks.value.every((item) => item.id !== selectedId.value)) {
        selectedId.value = real[0].id
      }
      const current = localTasks.value.find((item) => item.id === selectedId.value)
      if (current && !demoIds.has(current.id)) void openTask(current)
    }
  } catch {
    // 后端未启动时保留演示任务，页面仍然可展示
  }
}

async function openTask(task: Task) {
  draft.value = false
  selectedId.value = task.id
  if (demoIds.has(task.id)) return
  try {
    const detail = await api.get<RunDetail>(`/runs/${task.id}`)
    task.answer = detail.answer_markdown || task.answer
    task.status = statusOf(detail.status)
    task.pending = detail.pending_input
    task.sources = (detail.citations ?? []).map(toSource)
    task.artifacts = (detail.cards ?? []).map((card, index) => toArtifact(card, index, task))
    const calcCard = (detail.cards ?? []).find((card) => card.type === 'calculation')
    if (calcCard?.data) {
      task.calc = calcCard.data as unknown as Task['calc']
      prefix.value = Number(calcCard.data.prefix ?? prefix.value)
    }
    const history = await api.get<{ items: { type: string; payload: RunEventPayload }[] }>(
      `/runs/${task.id}/steps`,
    )
    task.steps = []
    for (const entry of history.items) applyEvent(task, entry.type, entry.payload)
  } catch {
    notify('这次运行的历史没能加载')
  }
}

async function ask(text: string) {
  let sessionId = sessions.value[0]?.id
  try {
    if (!sessionId) {
      const created = await api.post<{ id: string }>('/chat-sessions', {
        course_id: 'course_cn',
        title: '课程问答',
      })
      sessionId = created.id
      sessions.value.unshift({
        id: sessionId,
        course_id: 'course_cn',
        title: '课程问答',
        last_run: null,
      })
    }
  } catch {
    notify('后端未连接，请先确认服务在运行')
    return
  }

  const task = reactive<Task>({
    id: `pending_${Date.now()}`,
    title: text.length > 26 ? `${text.slice(0, 26)}…` : text,
    question: text,
    course: '计算机网络',
    chapter: '第 4 章 · 网络层',
    mode: mode.value,
    status: 'running',
    createdAt: '刚刚',
    group: '今天',
    plan: [],
    steps: [],
    artifacts: [],
    sources: [],
    answer: '',
    streaming: '',
  })
  localTasks.value.unshift(task)
  selectedId.value = task.id
  draft.value = false
  input.value = ''
  streaming.value = true

  try {
    const accepted = await api.post<{ run_id: string }>(
      `/chat-sessions/${sessionId}/runs`,
      { message: text, mode: mode.value },
    )
    task.id = accepted.run_id
    selectedId.value = accepted.run_id
    await follow(task, accepted.run_id, 0)
  } catch (error) {
    task.status = 'failed'
    task.answer = error instanceof ApiError ? error.message : '提问失败，请稍后重试'
  } finally {
    streaming.value = false
  }
}

async function follow(task: Task, runId: string, afterSeq: number) {
  const controller = new AbortController()
  try {
    await streamRunEvents(
      runId,
      (type, payload) => {
        task.lastSeq = payload.seq
        applyEvent(task, type, payload)
        if (type === 'input.required') controller.abort()
      },
      { afterSeq, signal: controller.signal },
    )
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return
    throw error
  }
}

async function decide(approved: boolean) {
  const task = activeTask.value
  const pending = task?.pending
  if (!task || !pending || streaming.value) return
  streaming.value = true
  try {
    await api.post(`/runs/${task.id}/inputs`, {
      input_id: pending.input_id,
      approved,
    })
    task.pending = null
    task.status = 'running'
    await follow(task, task.id, task.lastSeq ?? 0)
  } catch (error) {
    notify(error instanceof ApiError ? error.message : '审批提交失败')
  } finally {
    streaming.value = false
  }
}

function toSource(item: Evidence): SourceRef {
  const locator = [
    ...(item.locator?.section_path ?? []),
    item.locator?.page ? `第 ${item.locator.page} 页` : '',
  ]
    .filter(Boolean)
    .join(' · ')
  return {
    id: item.chunk_id,
    chunkId: item.chunk_id,
    doc: item.title,
    locator: locator || '课程原文',
    score: Number(item.score ?? 0),
    text: item.excerpt ?? '',
  }
}

function toArtifact(card: Card, index: number, task: Task): Artifact {
  const isCalc = card.type === 'calculation'
  const data = card.data ?? {}
  return {
    id: `art_${task.id}_${index}`,
    kind: isCalc ? 'calc' : 'answer',
    title: card.title ?? (isCalc ? '子网计算结果' : '本次回答'),
    summary: isCalc
      ? `网络 ${data.network_address ?? ''} · 可用 ${data.usable_host_count ?? 0} 个主机`
      : '来自本次回答，可继续追问或存为笔记',
    meta: card.tool,
    taskId: task.id,
    createdAt: '刚刚',
  }
}

function applyEvent(task: Task, type: string, payload: RunEventPayload) {
  switch (type) {
    case 'step_start':
      task.steps.push({
        id: `s${payload.seq}`,
        kind: 'thought',
        title: String(payload.title ?? '理解问题'),
        detail: String(payload.detail ?? ''),
      })
      break
    case 'plan':
      task.plan = ((payload.items as { id: string; goal: string }[] | undefined) ?? []).map(
        (item, index) => ({
          id: item.id,
          label: item.goal,
          state: index === 0 ? 'active' : 'todo',
        }),
      )
      break
    case 'action':
      task.steps.push({
        id: `s${payload.seq}`,
        kind: 'action',
        title: String(payload.tool ?? 'tool'),
        detail: JSON.stringify(payload.input ?? {}).slice(0, 140),
        status: 'ok',
      })
      break
    case 'observation': {
      const summary = payload.summary
        ? String(payload.summary)
        : payload.error_code
          ? `返回 ${payload.error_code}`
          : '工具返回结果'
      const boost = Array.isArray(payload.profile_boost) ? payload.profile_boost.length : 0
      const detail: string[] = []
      if (payload.elapsed_ms) detail.push(`耗时 ${payload.elapsed_ms}ms`)
      if (boost) detail.push(`薄弱章节加权 ${boost} 个`)
      task.steps.push({
        id: `s${payload.seq}`,
        kind: 'observation',
        title: summary.length > 48 ? `${summary.slice(0, 48)}…` : summary,
        detail: detail.join(' · ') || String(payload.tool ?? ''),
        ms: Number(payload.elapsed_ms ?? 0),
        status: payload.status === 'error' ? 'failed' : 'ok',
      })
      break
    }
    case 'token':
      task.streaming = (task.streaming ?? '') + String(payload.text ?? '')
      break
    case 'final': {
      task.answer = String(payload.answer_markdown ?? '')
      task.streaming = ''
      task.status = statusOf(String(payload.status ?? 'completed'))
      task.sources = ((payload.citations as Evidence[] | undefined) ?? []).map(toSource)
      task.artifacts = ((payload.cards as Card[] | undefined) ?? []).map((card, index) =>
        toArtifact(card, index, task),
      )
      const calcCard = ((payload.cards as Card[] | undefined) ?? []).find(
        (card) => card.type === 'calculation',
      )
      if (calcCard?.data) {
        task.calc = calcCard.data as unknown as Task['calc']
        prefix.value = Number(calcCard.data.prefix ?? prefix.value)
      }
      task.plan = task.plan.map((item) => ({ ...item, state: 'done' as const }))
      break
    }
    case 'input.required':
      task.status = 'waiting_approval'
      task.pending = payload.pending_input as Task['pending']
      break
    case 'resumed':
      task.status = 'running'
      if ('approved' in payload) task.pending = null
      break
    case 'run.failed':
      task.status = 'failed'
      task.answer = String(payload.message ?? '运行失败，请重试')
      break
    case 'run.cancelled':
      task.status = 'done'
      task.answer = '已取消本次操作'
      break
  }
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
            @click="openTask(t)"
          >
            <div class="flex items-center gap-1.5">
              <span
                class="h-1.5 w-1.5 shrink-0 rounded-full"
                :class="
                  t.status === 'done'
                    ? 'bg-success'
                    : t.status === 'waiting_approval'
                      ? 'bg-warn'
                      : t.status === 'failed'
                        ? 'bg-[#E36A6A]'
                        : 'animate-soft-pulse bg-brand'
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
                <p class="text-[12px] font-medium text-ink">
                  {{
                    activeTask.pending?.tool_call_id === 'reindex_course'
                      ? '重建课程索引'
                      : '需要确认的操作'
                  }}
                </p>
                <p class="mt-1 text-[10.5px] leading-relaxed text-muted">
                  {{ activeTask.pending?.prompt ?? '该请求会修改课程索引，需要你确认后执行。' }}
                </p>
                <div class="mt-3 flex gap-2">
                  <button class="pill-btn h-8 bg-ink px-3 text-[11px] text-canvas" :disabled="streaming" @click="decide(true)">
                    <Check :size="12" />
                    批准
                  </button>
                  <button class="pill-btn h-8 border border-line bg-surface px-3 text-[11px] text-muted" :disabled="streaming" @click="decide(false)">
                    拒绝
                  </button>
                </div>
              </div>
            </div>

            <template v-else>
              <p v-if="activeTask.streaming" class="mt-3 whitespace-pre-wrap text-[13px] leading-[1.85] text-subink">
                {{ activeTask.streaming }}
              </p>
              <div v-else-if="activeTask.answer" class="answer-md mt-3 text-[13px] leading-[1.85] text-subink" v-html="renderedAnswer" />
              <p v-else class="mt-3 text-[13px] leading-[1.85] text-subink">正在读取课程资料…</p>
              <p v-if="activeTask.status === 'failed'" class="mt-2 text-[10.5px] text-[#E36A6A]">
                这次运行失败了，可以调整提问后重试。
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
                引用 {{ activeTask.sources.length }} 个片段 · {{ docCount }} 份文档
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
