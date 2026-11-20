<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  ArrowRight,
  BookOpen,
  ClipboardList,
  FileText,
  Search,
  Sparkles,
  Waypoints,
} from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import GraphCanvas from '@/components/GraphCanvas.vue'
import { categories as seedCategories, graphLinks as seedLinks, graphNodes as seedNodes } from '@/mock/data'
import type { GraphLink, GraphNode } from '@/mock/data'
import { masteryLabel, type Mastery } from '@/mock/workbench'
import { api, type GraphDto, type PracticeQuestion } from '@/api/client'
import { useStudent } from '@/composables/useStudent'

const COURSE_ID = 'course_cn'
const { currentKey } = useStudent()

type GraphNodeEx = GraphNode & { chapter_id?: string }
type ChapterStat = { chapter_id: string; label: string; attempts: number; correct: number; rate: number }

const nodes = ref<GraphNodeEx[]>(seedNodes.map((node) => ({ ...node, refs: [] })))
const links = ref<GraphLink[]>(seedLinks)
const categories = ref<{ name: string }[]>(seedCategories)
const chapters = ref<{ id: string; title: string }[]>([])
const chapterStats = ref<Record<string, ChapterStat>>({})
const questionConcepts = ref<Record<string, string>>({})
const attempts = ref<{ question_id: string; correct: boolean }[]>([])
const questions = ref<PracticeQuestion[]>([])
const selectedId = ref<string | null>('tcp')
const query = ref('')

const selected = computed(() => nodes.value.find((node) => node.id === selectedId.value) ?? null)

const categoryName = computed(() => {
  if (!selected.value) return ''
  const byChapter = chapters.value.find((chapter) => chapter.id === selected.value?.chapter_id)
  return byChapter?.title ?? categories.value[selected.value.category]?.name ?? ''
})

const conceptStats = computed<Record<string, { total: number; correct: number }>>(() => {
  const stats: Record<string, { total: number; correct: number }> = {}
  for (const attempt of attempts.value) {
    const conceptId = questionConcepts.value[attempt.question_id]
    if (!conceptId) continue
    const bucket = stats[conceptId] ?? { total: 0, correct: 0 }
    bucket.total += 1
    if (attempt.correct) bucket.correct += 1
    stats[conceptId] = bucket
  }
  return stats
})

function masteryOf(node: GraphNodeEx): Mastery {
  const stat = conceptStats.value[node.id]
  if (!stat || !stat.total) return 'new'
  return stat.correct / stat.total >= 0.8 ? 'mastered' : 'weak'
}

const masteryMapReal = computed<Record<string, Mastery>>(() => {
  const map: Record<string, Mastery> = {}
  for (const node of nodes.value) map[node.id] = masteryOf(node)
  return map
})

const mastery = computed<Mastery>(() => (selected.value ? masteryOf(selected.value) : 'new'))

const chapterStat = computed<ChapterStat | null>(() => {
  const chapterId = selected.value?.chapter_id
  return chapterId ? chapterStats.value[chapterId] ?? null : null
})

const counts = computed(() => {
  const counter = { mastered: 0, weak: 0, new: 0 }
  for (const value of Object.values(masteryMapReal.value)) counter[value] += 1
  return counter
})

const masteryTone: Record<string, string> = {
  mastered: 'bg-success/12 text-success',
  weak: 'bg-warn/12 text-warn',
  new: 'bg-tint text-muted',
}

const difficultyLabel: Record<string, string> = { easy: '基础', medium: '进阶', hard: '挑战' }

const related = computed(() => {
  if (!selected.value) return []
  return links.value
    .filter((link) => link.source === selected.value!.id || link.target === selected.value!.id)
    .map((link) => (link.source === selected.value!.id ? link.target : link.source))
    .slice(0, 6)
    .map((id) => nodes.value.find((node) => node.id === id))
    .filter((node): node is GraphNodeEx => Boolean(node))
})

const nextSteps = computed(() => {
  if (!selected.value) return []
  return links.value
    .filter((link) => link.kind === 'prerequisite' && link.source === selected.value!.id)
    .map((link) => nodes.value.find((node) => node.id === link.target))
    .filter((node): node is GraphNodeEx => Boolean(node))
})

const practiceLink = computed(() => ({
  path: '/practice',
  query: {
    ...(selected.value?.chapter_id ? { chapter: selected.value.chapter_id } : {}),
    ...(selected.value ? { concept: selected.value.id } : {}),
  },
}))

function search() {
  const keyword = query.value.trim()
  if (!keyword) return
  const hit = nodes.value.find((node) => node.name.includes(keyword))
  if (hit) selectedId.value = hit.id
}

function focusWeak() {
  const hit = nodes.value.find((node) => masteryOf(node) === 'weak')
  if (hit) selectedId.value = hit.id
}

async function loadGraph() {
  try {
    const graph = await api.get<GraphDto>(`/courses/${COURSE_ID}/graph`)
    chapters.value = graph.chapters
    categories.value = graph.chapters.map((chapter) => ({ name: chapter.title }))
    const graphLinks = graph.links
    nodes.value = graph.nodes.map((node) => {
      const degree = graphLinks.filter((link) => link.source === node.id || link.target === node.id).length
      return {
        id: node.id,
        name: node.name,
        category: node.category,
        desc: node.desc,
        refs: [],
        value: Math.max(2, degree),
        chapter_id: node.chapter_id ?? undefined,
      }
    })
    links.value = graphLinks
  } catch {
    // 后端不可用时保留内置图谱，页面依旧可演示
  }
}

async function loadStats() {
  try {
    const stats = await api.get<{ by_chapter: ChapterStat[] }>('/practice/stats')
    const map: Record<string, ChapterStat> = {}
    for (const row of stats.by_chapter ?? []) map[row.chapter_id] = row
    chapterStats.value = map
  } catch {
    chapterStats.value = {}
  }
}

async function loadMasteryData() {
  try {
    const [bank, history] = await Promise.all([
      api.get<{ items: PracticeQuestion[] }>('/questions?limit=30&shuffle=false'),
      api.get<{ items: { question_id: string; correct: boolean }[] }>(
        `/practice/attempts?limit=100&user_key=${currentKey.value}`,
      ),
    ])
    const map: Record<string, string> = {}
    for (const question of bank.items) {
      if (question.concept_id) map[question.id] = question.concept_id
    }
    questionConcepts.value = map
    attempts.value = history.items ?? []
  } catch {
    questionConcepts.value = {}
    attempts.value = []
  }
}

async function loadDetail() {
  if (!selectedId.value) return
  const node = nodes.value.find((item) => item.id === selectedId.value)
  if (!node) return
  try {
    const detail = await api.get<{
      title: string
      description: string
      sources: { title: string; locator?: { section_path?: string[]; page?: number | null } }[]
    }>(`/concepts/${selectedId.value}`)
    node.desc = detail.description || node.desc
    node.refs = (detail.sources ?? []).map((source) => {
      const path = (source.locator?.section_path ?? []).join(' / ')
      const page = source.locator?.page ? `第 ${source.locator.page} 页` : ''
      return [source.title, path || page].filter(Boolean).join(' · ')
    })
  } catch {
    // 详情拉取失败时保留图谱自带描述
  }
}

async function loadQuestions() {
  if (!selectedId.value) {
    questions.value = []
    return
  }
  try {
    const result = await api.get<{ items: PracticeQuestion[] }>(
      `/questions?limit=5&shuffle=false&concept_id=${selectedId.value}`,
    )
    questions.value = result.items
  } catch {
    questions.value = []
  }
}

watch(selectedId, () => {
  void loadDetail()
  void loadQuestions()
})

onMounted(() => {
  void loadGraph().then(() => {
    void loadDetail()
    void loadStats()
    void loadMasteryData()
    void loadQuestions()
  })
})

watch(currentKey, () => {
  void loadMasteryData()
})
</script>

<template>
  <div class="animate-fade-up px-9 py-8">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="text-[26px] font-semibold leading-tight tracking-[-0.025em]">知识图谱</h1>
        <p class="mt-1.5 max-w-[620px] text-[12.5px] leading-relaxed text-muted">
          节点颜色是掌握程度，连线是关系类型：实线箭头为先修，虚线为包含，点线为关联。点节点看定义、原文出处、下一步学什么，以及能直接练的题。
        </p>
      </div>
      <div class="relative">
        <Search :size="14" class="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
        <input
          v-model="query"
          type="text"
          placeholder="搜索知识点，回车定位"
          class="h-9 w-[248px] rounded-full border border-line bg-surface pl-9 pr-4 text-[12.5px] text-ink outline-none transition-colors placeholder:text-muted focus:border-brand/50 focus:ring-2 focus:ring-brand/10"
          @keydown.enter="search"
        />
      </div>
    </div>

    <div class="mt-4 flex flex-wrap items-center gap-2">
      <span class="flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-[10.5px] text-subink">
        <span class="h-2 w-2 rounded-full bg-[#7FC49A]" />
        已掌握 {{ counts.mastered }}
      </span>
      <button
        class="flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-[10.5px] text-subink transition-colors hover:border-warn/40"
        @click="focusWeak"
      >
        <span class="h-2 w-2 rounded-full bg-[#DEA25C]" />
        薄弱 {{ counts.weak }}
      </button>
      <span class="flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-[10.5px] text-subink">
        <span class="h-2 w-2 rounded-full bg-[#9AA6BE]" />
        未学 {{ counts.new }}
      </span>
      <span class="ml-auto text-[10px] text-muted">
        {{ nodes.length }} 个知识点 · {{ links.length }} 条关系
      </span>
    </div>

    <div class="mt-4 grid gap-4 xl:grid-cols-[1fr_340px]">
      <section class="surface relative overflow-hidden">
        <div class="h-[600px] w-full">
          <GraphCanvas
            :nodes="nodes"
            :links="links"
            :categories="categories"
            :mastery="masteryMapReal"
            :selected-id="selectedId"
            @select="selectedId = $event"
          />
        </div>

        <div
          class="pointer-events-none absolute bottom-4 left-4 flex flex-wrap items-center gap-3 rounded-full border border-line bg-surface/85 px-3.5 py-1.5 text-[10px] text-muted shadow-[0_8px_24px_-16px_rgba(16,24,40,0.22)] backdrop-blur-xl"
        >
          <span class="flex items-center gap-1.5">
            <span class="relative h-[2px] w-5 rounded-full bg-[#3A6BE0]">
              <span class="absolute -right-1 -top-[3px] h-0 w-0 border-y-[4px] border-l-[5px] border-y-transparent border-l-[#3A6BE0]" />
            </span>
            先修
          </span>
          <span class="flex items-center gap-1.5">
            <span class="h-px w-5 border-t-[1.5px] border-dashed border-[#9AA2B1]" />包含
          </span>
          <span class="flex items-center gap-1.5">
            <span class="h-px w-5 border-t border-dotted border-[#C2C8D4]" />关联
          </span>
          <span class="text-line-strong">|</span>
          <span>点节点高亮相邻链路</span>
        </div>
      </section>

      <section class="surface flex min-h-[600px] flex-col overflow-hidden">
        <header class="flex items-center justify-between border-b border-line px-4 py-3">
          <div class="flex items-center gap-2">
            <Waypoints :size="14" class="text-muted" />
            <h2 class="text-[12px] font-medium">知识点</h2>
          </div>
          <span
            v-if="selected"
            class="rounded-full px-2 py-0.5 text-[9.5px]"
            :class="masteryTone[mastery]"
          >
            {{ masteryLabel[mastery] }}
          </span>
        </header>

        <div v-if="selected" class="flex min-h-0 flex-1 flex-col">
          <div class="border-b border-line p-4">
            <span class="text-[10px] text-muted">{{ categoryName }}</span>
            <h3 class="mt-1 text-[19px] font-semibold tracking-tight">{{ selected.name }}</h3>
            <p class="mt-2 text-[12px] leading-relaxed text-subink">{{ selected.desc }}</p>

            <div
              v-if="chapterStat"
              class="mt-3 flex items-center justify-between rounded-xl border border-line bg-tint-soft px-3 py-2 text-[10.5px] text-subink"
            >
              <span class="flex items-center gap-1.5">
                <Sparkles :size="11" :class="chapterStat.rate >= 80 ? 'text-success' : 'text-warn'" />
                本章已答 {{ chapterStat.attempts }} 题 · 正确率 {{ chapterStat.rate }}%
              </span>
              <RouterLink :to="practiceLink" class="text-brand hover:underline">去练</RouterLink>
            </div>
            <div v-else class="mt-3 text-[10px] text-muted">
              本章还没做过题，可以先看原文，再去做一组练习。
            </div>
          </div>

          <div class="min-h-0 flex-1 overflow-y-auto p-4">
            <div class="text-[10.5px] text-muted">原文出处</div>
            <ul class="mt-2 flex flex-col gap-1.5">
              <li
                v-for="ref in selected.refs"
                :key="ref"
                class="flex items-center gap-2 rounded-xl border border-line bg-tint-soft px-3 py-2.5 text-[11px] text-subink"
              >
                <FileText :size="12" class="shrink-0 text-muted" />
                {{ ref }}
              </li>
              <li v-if="!selected.refs.length" class="text-[10.5px] text-muted">
                正在读取出处…
              </li>
            </ul>

            <template v-if="nextSteps.length">
              <div class="mt-4 text-[10.5px] text-muted">学完它，下一步</div>
              <div class="mt-2 flex flex-wrap gap-1.5">
                <button
                  v-for="step in nextSteps"
                  :key="step.id"
                  class="flex items-center gap-1 rounded-full border border-[#4C7DF0]/30 bg-[#4C7DF0]/8 px-2.5 py-1 text-[10.5px] text-[#3A6BE0] transition-colors hover:border-[#4C7DF0]/50"
                  @click="selectedId = step.id"
                >
                  {{ step.name }}
                  <ArrowRight :size="10" />
                </button>
              </div>
            </template>

            <div class="mt-4 text-[10.5px] text-muted">相邻知识点</div>
            <div class="mt-2 flex flex-wrap gap-1.5">
              <button
                v-for="n in related"
                :key="n.id"
                class="rounded-full border border-line bg-tint-soft px-2.5 py-1 text-[10.5px] text-subink transition-colors hover:border-brand/30 hover:bg-brand-soft/60 hover:text-ink"
                @click="selectedId = n.id"
              >
                {{ n.name }}
              </button>
            </div>

            <div class="mt-4 flex items-center justify-between">
              <span class="text-[10.5px] text-muted">相关题目</span>
              <span class="text-[9px] text-muted">{{ questions.length }} 道</span>
            </div>
            <div class="mt-2 flex flex-col gap-1.5">
              <RouterLink
                v-for="question in questions"
                :key="question.id"
                :to="practiceLink"
                class="flex items-center gap-2 rounded-xl border border-line px-3 py-2.5 text-left transition-colors hover:border-line-strong hover:bg-tint-soft"
              >
                <ClipboardList :size="12" class="shrink-0 text-muted" />
                <span class="min-w-0 flex-1 truncate text-[10.5px] text-subink">{{ question.stem }}</span>
                <span class="shrink-0 rounded bg-tint px-1.5 py-0.5 text-[9px] text-muted">
                  {{ difficultyLabel[question.difficulty] ?? '进阶' }}
                </span>
                <ArrowRight :size="11" class="shrink-0 text-muted" />
              </RouterLink>
              <div v-if="!questions.length" class="rounded-xl border border-dashed border-line px-3 py-3 text-[10px] text-muted">
                这个知识点暂无独立题目，去做本章的一组题也能覆盖到。
              </div>
            </div>
          </div>

          <div class="border-t border-line p-3">
            <RouterLink
              :to="{ path: '/chat', query: { q: `请讲清楚「${selected.name}」，并给一个课程中的例子。` } }"
              class="pill-btn h-9 w-full justify-center bg-ink text-[11.5px] text-canvas hover:opacity-90"
            >
              <BookOpen :size="13" />
              针对这个知识点问 AI
            </RouterLink>
          </div>
        </div>

        <div v-else class="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
          <Waypoints :size="22" class="text-line-strong" />
          <p class="text-[12px] text-muted">点击图中节点查看详情</p>
        </div>
      </section>
    </div>
  </div>
</template>
