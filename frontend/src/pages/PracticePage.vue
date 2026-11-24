<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
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
import { RouterLink, useRoute } from 'vue-router'
import { ApiError, api } from '@/api/client'
import type { AttemptResult, PracticeQuestion } from '@/api/client'
import { useStudent } from '@/composables/useStudent'

const COURSE_ID = 'course_cn'
const route = useRoute()
const { currentKey } = useStudent()

const chapters = ref<{ id: string; title: string }[]>([])
const chapterId = ref(typeof route.query.chapter === 'string' ? route.query.chapter : '')
const conceptId = ref(typeof route.query.concept === 'string' ? route.query.concept : '')
const conceptIds = ref<string[]>(
  typeof route.query.concepts === 'string'
    ? route.query.concepts.split(',').map((item) => item.trim()).filter(Boolean)
    : [],
)
// 错题本「重做这 N 道错题」带过来的题目集合
const questionIds = ref<string[]>(
  typeof route.query.questions === 'string'
    ? route.query.questions.split(',').map((item) => item.trim()).filter(Boolean)
    : [],
)
const questions = ref<PracticeQuestion[]>([])
const index = ref(0)
const answers = reactive<Record<string, string>>({})
const results = reactive<Record<string, AttemptResult>>({})
const loading = ref(false)
const submitting = ref(false)
const finished = ref(false)
const toast = ref('')
const recommended = ref(false)
const preview = ref('')
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

async function loadCumulative() {
  try {
    const stats = await api.get<{ total: number; correct: number; rate: number }>(
      `/practice/stats?user_key=${currentKey.value}`,
    )
    cumulative.value = { total: stats.total, correct: stats.correct, rate: stats.rate }
  } catch {
    cumulative.value = null
  }
}

async function start() {
  loading.value = true
  finished.value = false
  recommended.value = false
  index.value = 0
  for (const key of Object.keys(answers)) delete answers[key]
  for (const key of Object.keys(results)) delete results[key]
  void loadCumulative()
  try {
    const params = ['limit=10', 'shuffle=true']
    if (questionIds.value.length) {
      params.push(`question_ids=${questionIds.value.join(',')}`)
      params.push(`limit=${Math.min(30, questionIds.value.length)}`)
    }
    if (chapterId.value) params.push(`chapter_id=${chapterId.value}`)
    if (conceptId.value) params.push(`concept_id=${conceptId.value}`)
    if (conceptIds.value.length) params.push(`concept_ids=${conceptIds.value.join(',')}`)
    const result = await api.get<{ items: PracticeQuestion[] }>(`/questions?${params.join('&')}`)
    questions.value = result.items
    if (!result.items.length && questionIds.value.length) {
      questionIds.value = []
      notify('这些错题已在题库中移除，已切到全部章节')
      await start()
      return
    }
    if (!result.items.length && conceptIds.value.length) {
      conceptIds.value = []
      notify('这些知识点暂无题目，已切到全部章节')
      await start()
      return
    }
    if (!result.items.length && conceptId.value) {
      conceptId.value = ''
      notify('这个知识点暂无独立题目，已切到本章')
      await start()
      return
    }
    if (!result.items.length) {
      notify(conceptId.value ? '这个知识点暂无独立题目，试试整个章节' : '这个章节暂时没有题目')
    }
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

async function recommend() {
  loading.value = true
  finished.value = false
  index.value = 0
  chapterId.value = ''
  conceptId.value = ''
  conceptIds.value = []
  questionIds.value = []
  for (const key of Object.keys(answers)) delete answers[key]
  for (const key of Object.keys(results)) delete results[key]
  try {
    const result = await api.get<{ items: PracticeQuestion[] }>(
      `/questions/recommended?user_key=${currentKey.value}&limit=10`,
    )
    questions.value = result.items
    recommended.value = true
    if (!result.items.length) notify('暂时没有可推荐的题目')
  } catch (error) {
    notify(error instanceof ApiError ? error.message : '推荐失败，请稍后再试')
  } finally {
    loading.value = false
  }
}

async function submit() {
  const question = current.value
  if (!question || !selected.value || submitting.value || results[question.id]) return
  submitting.value = true
  try {
    const result = await api.post<AttemptResult>('/practice/attempts', {
      question_id: question.id,
      answer: selected.value,
      user_key: currentKey.value,
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

watch(currentKey, () => {
  void start()
})

// 同一页面内 query 变化（例如从结果页点「再练一组」周边的概念链接）也要重新组卷
watch(
  () => [route.query.chapter, route.query.concept, route.query.concepts, route.query.questions],
  () => {
    chapterId.value = typeof route.query.chapter === 'string' ? route.query.chapter : ''
    conceptId.value = typeof route.query.concept === 'string' ? route.query.concept : ''
    conceptIds.value =
      typeof route.query.concepts === 'string'
        ? route.query.concepts.split(',').map((item) => item.trim()).filter(Boolean)
        : []
    questionIds.value =
      typeof route.query.questions === 'string'
        ? route.query.questions.split(',').map((item) => item.trim()).filter(Boolean)
        : []
    void start()
  },
)

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="animate-fade-up page">
    <div class="flex flex-wrap items-start justify-between gap-3 sm:gap-4">
      <div>
        <h1 class="text-[22px] font-semibold leading-tight tracking-[-0.025em] sm:text-[26px]">练习中心</h1>
      </div>
      <div
        class="scroll-x -mx-4 flex w-full items-center gap-1.5 overflow-x-auto px-4 pb-0.5 sm:mx-0 sm:w-auto sm:flex-wrap sm:overflow-visible sm:px-0 sm:pb-0"
      >
        <span
          v-if="questionIds.length"
          class="shrink-0 rounded-full bg-[#FBECEC] px-2.5 py-1 text-[10px] text-[#B4552D]"
        >
          错题重做 · {{ questionIds.length }} 题
        </span>
        <span
          v-else-if="recommended"
          class="shrink-0 rounded-full bg-[#FFF3E2] px-2.5 py-1 text-[10px] text-[#8A6A32]"
        >
          为你推荐
        </span>
        <span
          v-else-if="conceptId"
          class="shrink-0 rounded-full bg-brand-soft px-2.5 py-1 text-[10px] text-brand"
        >
          按知识点组卷
        </span>
        <span
          v-else-if="conceptIds.length"
          class="shrink-0 rounded-full bg-brand-soft px-2.5 py-1 text-[10px] text-brand"
        >
          专项 · {{ conceptIds.length }} 个知识点
        </span>
        <button
          class="shrink-0 rounded-full px-2.5 py-1 text-[10.5px] transition-colors"
          :class="chapterId === '' && !recommended && !conceptIds.length && !questionIds.length ? 'bg-surface text-ink shadow-sm' : 'text-muted hover:text-subink'"
          @click="chapterId = ''; conceptId = ''; conceptIds = []; questionIds = []; start()"
        >
          全部章节
        </button>
        <button
          v-for="chapter in chapters"
          :key="chapter.id"
          class="shrink-0 rounded-full px-2.5 py-1 text-[10.5px] transition-colors"
          :class="chapterId === chapter.id ? 'bg-surface text-ink shadow-sm' : 'text-muted hover:text-subink'"
          @click="chapterId = chapter.id; conceptId = ''; conceptIds = []; questionIds = []; start()"
        >
          {{ chapter.title }}
        </button>
        <button
          class="shrink-0 rounded-full border border-line px-2.5 py-1 text-[10.5px] text-subink transition-colors hover:border-line-strong hover:text-ink"
          @click="recommend"
        >
          为我推荐
        </button>
      </div>
    </div>

    <section class="surface mt-4 grid grid-cols-2 divide-line sm:mt-5 md:grid-cols-4 md:divide-x">
      <div class="px-4 py-3 sm:px-5 sm:py-3.5">
        <div class="text-[10px] text-muted">本组题目</div>
        <div class="mt-1 text-[19px] font-semibold leading-none">{{ questions.length }}</div>
      </div>
      <div class="px-4 py-3 sm:px-5 sm:py-3.5">
        <div class="text-[10px] text-muted">已作答</div>
        <div class="mt-1 text-[19px] font-semibold leading-none">{{ answeredCount }}</div>
      </div>
      <div class="border-t border-line px-4 py-3 sm:px-5 sm:py-3.5 md:border-t-0">
        <div class="text-[10px] text-muted">本组正确率</div>
        <div
          class="mt-1 text-[19px] font-semibold leading-none"
          :class="answeredCount ? (accuracy >= 60 ? 'text-success' : 'text-warn') : 'text-muted'"
        >
          {{ answeredCount ? accuracy + '%' : '—' }}
        </div>
      </div>
      <div class="flex items-center justify-between border-t border-line px-4 py-3 sm:px-5 sm:py-3.5 md:border-t-0">
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

    <div class="mt-4 grid grid-cols-[minmax(0,1fr)] items-start gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
      <section class="surface flex min-h-[360px] flex-col overflow-hidden sm:min-h-[420px]">
        <header class="flex items-center justify-between gap-2 border-b border-line px-4 py-3 sm:px-5 sm:py-3.5">
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
          <span class="hidden text-[9.5px] text-muted sm:inline">数字键选择 · Enter 提交</span>
        </header>

        <div v-if="loading" class="flex flex-1 items-center justify-center gap-2 text-[12px] text-muted">
          <Loader2 :size="14" class="animate-spin" />
          正在组卷…
        </div>

        <div v-else-if="!questions.length" class="flex flex-1 flex-col items-center justify-center gap-2 text-[12px] text-muted">
          这个章节还没有题目，先做「全部章节」试试。
        </div>

        <div v-else-if="finished" class="flex flex-1 flex-col p-4 sm:p-5">
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

        <div v-else class="flex flex-1 flex-col p-4 sm:p-5">
          <p v-if="recommended && current?.reason" class="mb-2 text-[10.5px] text-brand">
            {{ current.reason }}
          </p>
          <p class="text-[15px] font-medium leading-[1.75] tracking-[-0.01em] text-ink">
            {{ current?.stem }}
          </p>

          <button
            v-if="current?.image_url"
            class="mt-3 block w-full cursor-zoom-in"
            type="button"
            @click="preview = current.image_url ?? ''"
          >
            <img
              :src="current.image_url"
              alt="题目配图：点击放大"
              class="w-full rounded-[12px] border border-line bg-surface"
            />
          </button>

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
      </div>
    </div>

    <div
      v-if="toast"
      class="pointer-events-none fixed bottom-24 left-1/2 lg:bottom-8 z-50 -translate-x-1/2 rounded-full bg-ink px-3.5 py-1.5 text-[11px] text-canvas shadow-lg"
    >
      {{ toast }}
    </div>
  </div>

  <div
    v-if="preview"
    class="fixed inset-0 z-[60] flex cursor-zoom-out items-center justify-center bg-black/65 p-8"
    @click="preview = ''"
  >
    <img :src="preview" alt="题目配图" class="max-h-full max-w-full rounded-[16px] bg-surface shadow-2xl" />
  </div>
</template>
