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
import { masteryLabel, masteryMap } from '@/mock/workbench'
import { api, type Evidence, type GraphDto } from '@/api/client'

const COURSE_ID = 'course_cn'

const nodes = ref<GraphNode[]>(seedNodes.map((node) => ({ ...node, refs: [] })))
const links = ref<GraphLink[]>(seedLinks)
const categories = ref<{ name: string }[]>(seedCategories)
const selectedId = ref<string | null>('ipv4')
const query = ref('')

const selected = computed(() => nodes.value.find((node) => node.id === selectedId.value) ?? null)
const categoryName = computed(() =>
  selected.value ? categories.value[selected.value.category]?.name ?? '' : '',
)
const mastery = computed(() => (selected.value ? masteryMap[selected.value.id] ?? 'new' : 'new'))

const counts = computed(() => {
  const counter = { mastered: 0, weak: 0, new: 0 }
  for (const node of nodes.value) counter[masteryMap[node.id] ?? 'new'] += 1
  return counter
})

const masteryTone: Record<string, string> = {
  mastered: 'bg-success/12 text-success',
  weak: 'bg-warn/12 text-warn',
  new: 'bg-tint text-muted',
}

const related = computed(() => {
  if (!selected.value) return []
  return links.value
    .filter((link) => link.source === selected.value!.id || link.target === selected.value!.id)
    .map((link) => (link.source === selected.value!.id ? link.target : link.source))
    .slice(0, 6)
    .map((id) => nodes.value.find((node) => node.id === id))
    .filter((node): node is GraphNode => Boolean(node))
})

function search() {
  const keyword = query.value.trim()
  if (!keyword) return
  const hit = nodes.value.find((node) => node.name.includes(keyword))
  if (hit) selectedId.value = hit.id
}

function focusWeak() {
  const hit = nodes.value.find((node) => masteryMap[node.id] === 'weak')
  if (hit) selectedId.value = hit.id
}

async function loadGraph() {
  try {
    const graph = await api.get<GraphDto>(`/courses/${COURSE_ID}/graph`)
    const chapterNames = graph.chapters.map((chapter) => chapter.title)
    nodes.value = graph.nodes.map((node) => ({
      id: node.id,
      name: node.name,
      category: node.category,
      desc: node.desc,
      refs: [],
    })) as unknown as GraphNode[]
    links.value = graph.links as unknown as GraphLink[]
    categories.value = chapterNames.map((name) => ({ name }))
  } catch {
    // 后端不可用时保留内置图谱，页面依旧可演示
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
      sources: Evidence[]
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

watch(selectedId, () => {
  void loadDetail()
})

onMounted(() => {
  void loadGraph().then(() => loadDetail())
})
</script>

<template>
  <div class="animate-fade-up px-9 py-8">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="text-[26px] font-semibold leading-tight tracking-[-0.025em]">知识图谱</h1>
        <p class="mt-1.5 max-w-[600px] text-[12.5px] leading-relaxed text-muted">
          颜色代表你的掌握程度，不是关系类型。点节点看定义、出处和题目，也能直接针对它开一个问答任务。
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

    <div class="mt-4 grid gap-4 xl:grid-cols-[1fr_328px]">
      <section class="surface relative overflow-hidden">
        <div class="h-[600px] w-full">
          <GraphCanvas
            :nodes="nodes"
            :links="links"
            :categories="categories"
            :selected-id="selectedId"
            @select="selectedId = $event"
          />
        </div>

        <div
          class="pointer-events-none absolute bottom-4 left-4 flex flex-wrap items-center gap-3 rounded-full border border-line bg-surface/85 px-3.5 py-1.5 text-[10px] text-muted shadow-[0_8px_24px_-16px_rgba(16,24,40,0.22)] backdrop-blur-xl"
        >
          <span class="flex items-center gap-1.5">
            <span class="h-px w-5 bg-line-strong" />先修
          </span>
          <span class="flex items-center gap-1.5">
            <span class="h-px w-5 border-t border-dashed border-line-strong" />包含
          </span>
          <span class="flex items-center gap-1.5">
            <span class="h-px w-5 border-t border-dotted border-line-strong" />关联
          </span>
          <span class="text-line-strong">|</span>
          <span>点击节点查看详情</span>
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
              v-if="mastery === 'weak'"
              class="mt-3 rounded-xl border border-warn/30 bg-warn/8 px-3 py-2 text-[10.5px] leading-relaxed text-warn"
            >
              近两次作答都错在「块对齐」这一步，建议先复习再做题。
            </div>
            <div v-else-if="mastery === 'new'" class="mt-3 text-[10px] text-muted">
              还没学过这个知识点。可以先看原文，再开一个问答任务。
            </div>
            <div v-else class="mt-3 flex items-center gap-1.5 text-[10px] text-muted">
              <Sparkles :size="11" class="text-success" />
              上次作答 10 月 12 日 · 正确
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
            </ul>

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

            <div class="mt-4 text-[10.5px] text-muted">相关题目</div>
            <div class="mt-2 flex flex-col gap-1.5">
              <button
                class="flex items-center justify-between rounded-xl border border-line px-3 py-2.5 text-left transition-colors hover:border-line-strong hover:bg-tint-soft"
              >
                <span class="flex items-center gap-2 text-[11px] text-subink">
                  <ClipboardList :size="12" class="text-muted" />
                  {{ selected.name }} · 基础判断
                </span>
                <ArrowRight :size="12" class="text-muted" />
              </button>
              <button
                class="flex items-center justify-between rounded-xl border border-line px-3 py-2.5 text-left transition-colors hover:border-line-strong hover:bg-tint-soft"
              >
                <span class="flex items-center gap-2 text-[11px] text-subink">
                  <ClipboardList :size="12" class="text-muted" />
                  {{ selected.name }} · 场景应用
                </span>
                <ArrowRight :size="12" class="text-muted" />
              </button>
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
