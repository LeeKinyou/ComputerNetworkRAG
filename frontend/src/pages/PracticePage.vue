<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import {
  ArrowRight,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ListChecks,
  Loader2,
  RotateCcw,
  Sparkles,
  XCircle,
} from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { ApiError, api } from '@/api/client'
import type { AttemptResult, PracticeQuestion } from '@/api/client'

const COURSE_ID = 'course_cn'

const chapters = ref<{ id: string; title: string }[]>([])
const chapterId = ref('')
const questions = ref<PracticeQuestion[]>([])
const index = ref(0)
const answers = reactive<Record<string, string>>({})
const results = reactive<Record<string, AttemptResult>>({})
const loading = ref(false)
const submitting = ref(false)
const finished = ref(false)
const toast = ref('')
const cumulative = ref<{ total: number; correct: number; rate: number } | null>(null)

const current = computed(() => questions.value[index.value])
const currentResult = computed(() => (current.value ? results[current.value.id] : undefined))
const selected = computed(() => (current.value ? answers[current.value.id] ?? '' : ''))
const answeredCount = computed(() => Object.keys(results).length)
const correctCount = computed(() => Object.values(results).filter((item) => item.correct).length)
const accuracy = computed(() =>
  answeredCount.value ? Math.round((correctCount.value / answeredCount.value) * 100) : 0,
)
const wrongList = computed(() =>
  questions.value.filter((question) => results[question.id] && !results[question.id].correct),
)
const progress = computed(() =>
  questions.value.length ? Math.round((answeredCount.value / questions.value.length) * 100) : 0,
)
const isLast = computed(() => index.value === questions.value.length - 1)

const difficultyLabel: Record<string, string> = { easy: '基础', medium: '进阶', hard: '挑战' }

function notify(text: string) {
  toast.value = text
  window.setTimeout(() => (toast.value = ''), 2200)
}

async function loadChapters() {
  try {
    const result = await api.get<{ items: { id: string; title: string }[] }>(
      `/courses/${COURSE_ID}/chapters`,
    )
    chapters.value = result.items
  } catch {
    chapters.value = []
  }
}

async function start() {
  loading.value = true
  finished.value = false
  index.value = 0
  for (const key of Object.keys(answers)) delete answers[key]
  for (const key of Object.keys(results)) delete results[key]
  try {
    const query = chapterId.value ? `&chapter_id=${chapterId.value}` : ''
    const result = await api.get<{ items: PracticeQuestion[] }>(
      `/questions?limit=10&shuffle=true${query}`,
    )
    questions.value = result.items
    if (!result.items.length) notify('这个章节暂时没有题目')
  } catch (error) {
    notify(error instanceof ApiError ? error.message : '组卷失败，请稍后再试')
  } finally {
    loading.value = false
  }
}

function choose(key: string) {
  if (!current.value || currentResult.value) return
  answers[current.value.id] = key
}

async function submit() {
  const question = current.value
  if (!question || !selected.value || submitting.value || results[question.id]) return
  submitting.value = true
  try {
    const result = await api.post<AttemptResult>('/practice/attempts', {
      question_id: question.id,
      answer: selected.value,
    })
    results[question.id] = result
    cumulative.value = result.stats
    if (result.correct) notify('答对了')
    else notify('记下来，稍后复习')
  } catch (error) {
    notify(error instanceof ApiError ? error.message : '提交失败')
  } finally {
    submitting.value = false
  }
}

function next() {
  if (index.value < questions.value.length - 1) index.value += 1
  else finished.value = true
}

function prev() {
  if (index.value > 0) index.value -= 1
}

function restart() {
  void start()
}

function optionClass(key: string): string {
  const result = currentResult.value
  const base =
    'flex w-full items-start gap-3 rounded-[14px] border px-4 py-3 text-left text-[12.5px] leading-relaxed transition-colors disabled:cursor-default'
  if (result) {
    if (key === result.expected) return `${base} border-success/55 bg-success/10 text-subink`
    if (key === result.given) return `${base} border-[#E36A6A]/55 bg-[#E36A6A]/10 text-subink`
    return `${base} border-line text-muted opacity-65`
  }
  if (key === selected.value) return `${base} border-brand bg-brand-soft/45 text-ink`
  return `${base} border-line text-subink hover:border-brand/40 hover:bg-tint-soft`
}

function onKeydown(event: KeyboardEvent) {
  if (finished.value || loading.value || !current.value) return
  const options = current.value.options
  const digit = Number(event.key)
  if (digit >= 1 && digit <= options.length) {
    choose(options[digit - 1].key)
    return
  }
  if (event.key === 'Enter') {
    if (currentResult.value) next()
    else void submit()
  }
}

onMounted(() => {
  void loadChapters().then(() => start())
  window.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="animate-fade-up px-9 py-8">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="text-[26px] font-semibold leading-tight tracking-[-0.025em]">练习中心</h1>
        <p class="mt-1.5 max-w-[600px] text-[12.5px] leading-relaxed text-muted">
          按章节组卷，答完即时批改并给出解析；错题会记进学习报告，攒够几题再回问答里问透。
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-1.5">
        <button
          class="rounded-full px-2.5 py-1 text-[10.5px] transition-colors"
          :class="chapterId === '' ? 'bg-surface text-ink shadow-sm' : 'text-muted hover:text-subink'"
          @click="chapterId = ''; start()"
        >
          全部章节
        </button>
        <button
          v-for="chapter in chapters"
          :key="chapter.id"
          class="rounded-full px-2.5 py-1 text-[10.5px] transition-colors"
          :class="chapterId === chapter.id ? 'bg-surface text-ink shadow-sm' : 'text-muted hover:text-subink'"
          @click="chapterId = chapter.id; start()"
        >
          {{ chapter.title }}
        </button>
      </div>
    </div>

    <section class="surface mt-5 grid grid-cols-2 divide-line md:grid-cols-4 md:divide-x">
      <div class="px-5 py-3.5">
        <div class="text-[10px] text-muted">本组题目</div>
        <div class="mt-1 text-[19px] font-semibold leading-none">{{ questions.length }}</div>
      </div>
      <div class="px-5 py-3.5">
        <div class="text-[10px] text-muted">已作答</div>
        <div class="mt-1 text-[19px] font-semibold leading-none">{{ answeredCount }}</div>
      </div>
      <div class="px-5 py-3.5">
        <div class="text-[10px] text-muted">本组正确率</div>
        <div class="mt-1 text-[19px] font-semibold leading-none" :class="accuracy >= 60 ? 'text-success' : 'text-warn'">
          {{ answeredCount ? accuracy + '%' : '—' }}
        </div>
      </div>
      <div class="flex items-center justify-between px-5 py-3.5">
        <div>
          <div class="text-[10px] text-muted">累计作答</div>
          <div class="mt-1 flex items-center gap-2 text-[12px]">
            <span class="font-medium">{{ cumulative?.total ?? 0 }} 题</span>
            <span class="text-muted">正确率 {{ cumulative?.rate ?? 0 }}%</span>
          </div>
        </div>
        <button class="icon-btn" aria-label="重新组卷" @click="restart">
          <RotateCcw :size="13" />
        </button>
      </div>
    </section>

    <div class="mt-4 grid items-start gap-4 xl:grid-cols-[1fr_320px]">
      <section class="surface flex min-h-[420px] flex-col overflow-hidden">
        <header class="flex items-center justify-between border-b border-line px-5 py-3.5">
          <div class="flex items-center gap-2">
            <ListChecks :size="14" class="text-muted" />
            <h2 class="text-[12.5px] font-medium">
              {{ finished ? '本组结果' : `第 ${index + 1} / ${questions.length || 0} 题` }}
            </h2>
            <span
              v-if="current && !finished"
              class="rounded-md bg-tint px-1.5 py-0.5 text-[9.5px] text-muted"
            >
              {{ current.chapter_title }}
            </span>
            <span
              v-if="current && !finished"
              class="rounded-md bg-brand-soft px-1.5 py-0.5 text-[9.5px] text-brand"
            >
              {{ difficultyLabel[current.difficulty] ?? '进阶' }}
            </span>
          </div>
          <span class="text-[9.5px] text-muted">数字键选择 · Enter 提交</span>
        </header>

        <div v-if="loading" class="flex flex-1 items-center justify-center gap-2 text-[12px] text-muted">
          <Loader2 :size="14" class="animate-spin" />
          正在组卷…
        </div>

        <div v-else-if="!questions.length" class="flex flex-1 flex-col items-center justify-center gap-2 text-[12px] text-muted">
          这个章节还没有题目，先做「全部章节」试试。
        </div>

        <div v-else-if="finished" class="flex flex-1 flex-col p-5">
          <div class="flex flex-wrap items-center gap-4">
            <div class="flex h-16 w-16 items-center justify-center rounded-full border border-line bg-tint-soft">
              <span class="text-[24px] font-semibold leading-none">{{ accuracy }}%</span>
            </div>
            <div>
              <p class="text-[14px] font-medium text-ink">
                本组答对 {{ correctCount }} / {{ answeredCount }} 题
              </p>
              <p class="mt-1 text-[10.5px] text-muted">
                {{ accuracy >= 80 ? '掌握得不错，可以换更难的章节了。' : accuracy >= 60 ? '基础题基本稳了，错题再练一轮。' : '建议先回看错题解析，再去问答里追问。' }}
              </p>
            </div>
          </div>

          <div v-if="wrongList.length" class="mt-5">
            <p class="text-[10.5px] font-medium text-subink">本组错题</p>
            <ul class="mt-2 flex flex-col gap-2">
              <li
                v-for="question in wrongList"
                :key="question.id"
                class="flex items-center gap-3 rounded-xl border border-line bg-tint-soft px-3 py-2.5"
              >
                <XCircle :size="13" class="shrink-0 text-[#E36A6A]" />
                <p class="min-w-0 flex-1 truncate text-[11.5px] text-subink">{{ question.stem }}</p>
                <RouterLink
                  :to="{ path: '/chat', query: { q: `请解释这道题：${question.stem}` } }"
                  class="shrink-0 text-[9.5px] text-brand hover:underline"
                >
                  问助教
                </RouterLink>
              </li>
            </ul>
          </div>

          <div class="mt-auto flex flex-wrap items-center gap-2 pt-5">
            <button class="pill-btn h-9 bg-ink text-canvas hover:opacity-90" @click="restart">
              <RotateCcw :size="13" />
              再练一组
            </button>
            <RouterLink
              to="/progress"
              class="pill-btn h-9 border border-line bg-surface text-subink hover:border-line-strong"
            >
              看学习报告
              <ArrowRight :size="12" />
            </RouterLink>
            <RouterLink
              to="/chat"
              class="pill-btn h-9 border border-line bg-surface text-subink hover:border-line-strong"
            >
              去问答追问
              <ArrowRight :size="12" />
            </RouterLink>
          </div>
        </div>

        <div v-else class="flex flex-1 flex-col p-5">
          <p class="text-[15px] font-medium leading-[1.75] tracking-[-0.01em] text-ink">
            {{ current?.stem }}
          </p>

          <div class="mt-4 flex flex-col gap-2">
            <button
              v-for="option in current?.options"
              :key="option.key"
              :class="optionClass(option.key)"
              :disabled="Boolean(currentResult)"
              @click="choose(option.key)"
            >
              <span
                class="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border border-line bg-surface text-[9.5px] font-medium"
                :class="currentResult && option.key === currentResult.expected ? 'border-success/50 text-success' : ''"
              >
                {{ option.key }}
              </span>
              <span class="flex-1">{{ option.text }}</span>
              <CheckCircle2
                v-if="currentResult && option.key === currentResult.expected"
                :size="14"
                class="mt-0.5 shrink-0 text-success"
              />
              <XCircle
                v-else-if="currentResult && option.key === currentResult.given"
                :size="14"
                class="mt-0.5 shrink-0 text-[#E36A6A]"
              />
            </button>
          </div>

          <div v-if="currentResult" class="mt-4 rounded-[14px] border border-line bg-tint-soft px-4 py-3">
            <div class="flex items-center gap-2 text-[10.5px] font-medium" :class="currentResult.correct ? 'text-success' : 'text-[#E36A6A]'">
              <component :is="currentResult.correct ? CheckCircle2 : XCircle" :size="13" />
              {{ currentResult.correct ? '回答正确' : `回答错误，正确答案是 ${currentResult.expected}` }}
            </div>
            <p class="mt-1.5 text-[11px] leading-[1.75] text-subink">{{ currentResult.explanation }}</p>
            <p class="mt-1 text-[9.5px] text-muted">出处：{{ currentResult.source }}</p>
          </div>

          <div class="mt-auto flex flex-wrap items-center gap-2 pt-5">
            <button
              class="pill-btn h-9 border border-line bg-surface text-subink hover:border-line-strong disabled:opacity-40"
              :disabled="index === 0"
              @click="prev"
            >
              <ChevronLeft :size="13" />
              上一题
            </button>
            <button
              v-if="!currentResult"
              class="pill-btn h-9 bg-ink text-canvas hover:opacity-90 disabled:opacity-40"
              :disabled="!selected || submitting"
              @click="submit"
            >
              <Loader2 v-if="submitting" :size="13" class="animate-spin" />
              <Sparkles v-else :size="13" />
              提交答案
            </button>
            <button
              v-else
              class="pill-btn h-9 bg-ink text-canvas hover:opacity-90"
              @click="next"
            >
              {{ isLast ? '查看本组结果' : '下一题' }}
              <ChevronRight :size="13" />
            </button>
            <span class="ml-auto text-[9.5px] text-muted">
              {{ answeredCount }} / {{ questions.length }} 已作答
            </span>
          </div>
        </div>
      </section>

      <div class="flex flex-col gap-4">
        <section class="surface p-4">
          <div class="flex items-center justify-between">
            <p class="text-[10.5px] font-medium text-subink">本组进度</p>
            <span class="font-mono text-[10px] text-muted">{{ progress }}%</span>
          </div>
          <div class="mt-2.5 h-1.5 overflow-hidden rounded-full bg-tint">
            <div class="h-full rounded-full bg-brand/70 transition-[width]" :style="{ width: progress + '%' }" />
          </div>
          <div class="mt-3 flex items-center gap-4 text-[10px] text-muted">
            <span class="flex items-center gap-1">
              <span class="h-1.5 w-1.5 rounded-full bg-success" />
              正确 {{ correctCount }}
            </span>
            <span class="flex items-center gap-1">
              <span class="h-1.5 w-1.5 rounded-full bg-[#E36A6A]" />
              错误 {{ answeredCount - correctCount }}
            </span>
            <span class="ml-auto">未答 {{ questions.length - answeredCount }}</span>
          </div>
        </section>

        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-4 py-3">
            <h2 class="text-[11.5px] font-medium">本组错题</h2>
            <span class="text-[9px] text-muted">{{ wrongList.length }} 道</span>
          </header>
          <div class="p-3">
            <div v-if="!wrongList.length" class="px-1 py-6 text-center text-[10.5px] text-muted">
              还没有错题，继续保持。
            </div>
            <ul v-else class="flex flex-col gap-2">
              <li
                v-for="(question, order) in wrongList"
                :key="question.id"
                class="rounded-xl border border-line bg-tint-soft px-3 py-2.5"
              >
                <div class="flex items-center gap-1.5">
                  <span class="font-mono text-[9px] text-muted">错 {{ order + 1 }}</span>
                  <span class="truncate text-[9px] text-muted">{{ question.chapter_title }}</span>
                </div>
                <p class="mt-1 line-clamp-2 text-[10.5px] leading-[1.6] text-subink">{{ question.stem }}</p>
              </li>
            </ul>
            <button
              class="pill-btn mt-3 h-8 w-full justify-center border border-line bg-surface text-[10.5px] text-subink hover:border-line-strong"
              @click="restart"
            >
              <RotateCcw :size="12" />
              换一组题
            </button>
          </div>
        </section>

        <section class="surface p-4">
          <div class="flex items-center gap-1.5 text-[10.5px] font-medium text-subink">
            <Sparkles :size="12" class="text-brand" />
            答题小提示
          </div>
          <p class="mt-2 text-[10px] leading-[1.75] text-muted">
            子网题先算块大小，再判断地址落在哪一块；掩码题注意「可用主机」要去掉网络与广播地址。
            答错后点「问助教」，会把这道题带进问答里逐句讲。
          </p>
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
