<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, BookMarked, CircleCheck, CircleHelp, RotateCcw, Sparkles } from 'lucide-vue-next'
import { api } from '@/api/client'
import type { WrongBook } from '@/api/client'
import { useStudent } from '@/composables/useStudent'

const router = useRouter()
const { currentKey } = useStudent()
const data = ref<WrongBook | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    data.value = await api.get<WrongBook>(`/practice/wrongbook?user_key=${currentKey.value}`)
  } catch {
    data.value = null
  } finally {
    loading.value = false
  }
}

function retry(conceptId: string | null) {
  router.push({ path: '/practice', query: conceptId ? { concept: conceptId } : {} })
}

/** 错题重做：把当前所有待复习题按错得最多的顺序带进练习页。 */
const retryAllLink = computed(() => {
  const items = data.value?.items ?? []
  if (!items.length) return '/practice'
  return `/practice?questions=${items.map((item) => item.question_id).join(',')}`
})

function ask(stem: string) {
  router.push({ path: '/chat', query: { q: stem } })
}

const summary = computed(() => [
  { label: '待复习', value: data.value?.unresolved ?? 0, hint: '最近一次仍答错', tone: 'text-warn' },
  { label: '已纠正', value: data.value?.solved ?? 0, hint: '错过但已答对', tone: 'text-success' },
  { label: '涉及知识点', value: data.value?.concepts_affected ?? 0, hint: '按概念聚合', tone: 'text-subink' },
])

onMounted(load)
watch(currentKey, load)
</script>

<template>
  <div class="animate-fade-up px-9 py-8">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="text-[26px] font-semibold leading-tight tracking-[-0.025em]">错题本</h1>
      </div>
      <RouterLink
        :to="retryAllLink"
        class="pill-btn h-9 border border-line bg-surface text-subink hover:border-line-strong hover:text-ink"
      >
        <span v-if="data?.items.length">重做这 {{ data.items.length }} 道错题</span>
        <span v-else>去练习</span>
        <ArrowRight :size="13" />
      </RouterLink>
    </div>

    <div class="mt-6 grid grid-cols-3 gap-3">
      <section
        v-for="item in summary"
        :key="item.label"
        class="rounded-2xl border border-line bg-surface px-5 py-4"
      >
        <p class="text-[10.5px] text-muted">{{ item.label }}</p>
        <p class="mt-1 flex items-baseline gap-1.5">
          <span class="text-[26px] font-semibold leading-none tracking-tight" :class="item.tone">{{ item.value }}</span>
          <span class="text-[10.5px] text-muted">题</span>
        </p>
        <p class="mt-1.5 text-[10px] text-muted">{{ item.hint }}</p>
      </section>
    </div>

    <div v-if="loading && !data" class="mt-6 rounded-2xl border border-line bg-surface px-5 py-10 text-center text-[12px] text-muted">
      正在整理错题…
    </div>

    <div
      v-else-if="!data || !data.groups.length"
      class="mt-6 rounded-2xl border border-line bg-surface px-5 py-14 text-center"
    >
      <span class="mx-auto grid h-11 w-11 place-items-center rounded-full bg-success/10 text-success">
        <CircleCheck :size="20" />
      </span>
      <p class="mt-3 text-[13px] font-medium text-ink">暂时没有待复习的错题</p>
      <p class="mt-1 text-[11px] text-muted">练习里答错的题会自动收进这里，答对一次就移出。</p>
      <button
        class="pill-btn mx-auto mt-4 h-8 bg-ink px-4 text-[11px] text-canvas"
        @click="router.push('/practice')"
      >
        做一组练习
      </button>
    </div>

    <div v-else class="mt-6 space-y-3">
      <section
        v-for="group in data.groups"
        :key="group.concept_id ?? group.title"
        class="rounded-2xl border border-line bg-surface p-5"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="flex items-center gap-2.5">
            <span class="grid h-7 w-7 place-items-center rounded-lg bg-brand-soft text-brand">
              <BookMarked :size="14" />
            </span>
            <div>
              <h2 class="text-[14px] font-semibold leading-tight">{{ group.title }}</h2>
              <p class="mt-0.5 text-[10.5px] text-muted">{{ group.chapter_title }}</p>
            </div>
          </div>
          <span class="shrink-0 rounded-full bg-warn/10 px-2 py-0.5 text-[10px] font-medium text-warn">
            待复习 {{ group.wrong }}
          </span>
        </div>

        <ul class="mt-3 divide-y divide-line">
          <li v-for="item in group.items" :key="item.question_id" class="flex items-start gap-4 py-3">
            <div class="min-w-0 flex-1">
              <p class="line-clamp-2 text-[12.5px] leading-relaxed text-subink">{{ item.stem }}</p>
              <p class="mt-1 text-[10px] text-muted">
                错 {{ item.wrong }} 次 · 共作答 {{ item.attempts }} 次 · {{ item.chapter_title }}
              </p>
            </div>
            <div class="flex shrink-0 items-center gap-1.5">
              <button
                class="pill-btn h-7 border border-line bg-surface px-2.5 text-[10.5px] text-subink hover:border-line-strong hover:text-ink"
                @click="retry(item.concept_id)"
              >
                <RotateCcw :size="11" />
                重练
              </button>
              <button
                class="pill-btn h-7 border border-line bg-surface px-2.5 text-[10.5px] text-subink hover:border-brand/40 hover:text-brand"
                @click="ask(item.stem)"
              >
                <CircleHelp :size="11" />
                问助教
              </button>
            </div>
          </li>
        </ul>
      </section>

      <p class="flex items-center gap-1.5 px-1 pt-1 text-[10px] text-muted">
        <Sparkles :size="11" />
        重练会在练习中心按该知识点重新组卷，答对后再回这里刷新即可看到它移出。
      </p>
    </div>
  </div>
</template>
