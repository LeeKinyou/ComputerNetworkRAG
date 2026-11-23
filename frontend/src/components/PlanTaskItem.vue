<script setup lang="ts">
import { BookOpen, ClipboardList, CircleHelp, Clock } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import type { LearningTask } from '@/api/client'

defineProps<{ task: LearningTask; index?: number }>()

const router = useRouter()

const actionMeta: Record<string, { label: string; cls: string }> = {
  review: { label: '复习', cls: 'bg-warn/10 text-warn' },
  learn: { label: '入门', cls: 'bg-brand-soft text-brand' },
  practice: { label: '巩固', cls: 'bg-success/10 text-success' },
  submit: { label: '作业', cls: 'bg-brand-soft text-brand' },
}

function goPractice(conceptId?: string | null) {
  router.push({ path: '/practice', query: { concept: conceptId ?? '' } })
}

function goAsk(title: string) {
  router.push({ path: '/chat', query: { q: `帮我讲清楚「${title}」这个知识点` } })
}

function goAssignment(id?: string | null) {
  router.push(id ? { path: '/assignments', query: { focus: id } } : { path: '/assignments' })
}
</script>

<template>
  <div class="flex items-start gap-3 rounded-xl border border-line bg-tint-soft px-4 py-3">
    <span
      v-if="index !== undefined"
      class="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-surface text-[11px] font-semibold text-muted"
    >
      {{ index + 1 }}
    </span>
    <div class="min-w-0 flex-1">
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-[13px] font-medium text-ink">{{ task.title }}</span>
        <span class="rounded-full px-1.5 py-0.5 text-[9.5px] font-medium" :class="actionMeta[task.action]?.cls">
          {{ actionMeta[task.action]?.label }}
        </span>
        <span class="text-[10px] text-muted">{{ task.chapter_title }}</span>
      </div>
      <p class="mt-1 text-[11px] leading-relaxed text-muted">{{ task.reason }}</p>
    </div>
    <span class="mt-0.5 flex shrink-0 items-center gap-1 text-[10px] text-muted">
      <Clock :size="10.5" />
      {{ task.minutes }} 分钟
    </span>
    <div class="mt-0.5 flex shrink-0 items-center gap-1.5">
      <button
        v-if="task.kind === 'assignment'"
        class="pill-btn h-7 border border-line bg-surface px-2.5 text-[10.5px] text-subink hover:border-brand/40 hover:text-brand"
        @click="goAssignment(task.assignment_id)"
      >
        <ClipboardList :size="11" />
        去作业
      </button>
      <template v-else>
        <button
          class="pill-btn h-7 border border-line bg-surface px-2.5 text-[10.5px] text-subink hover:border-brand/40 hover:text-brand"
          @click="goPractice(task.concept_id)"
        >
          <BookOpen :size="11" />
          去练习
        </button>
        <button
          class="pill-btn h-7 border border-line bg-surface px-2.5 text-[10.5px] text-subink hover:border-line-strong hover:text-ink"
          @click="goAsk(task.title)"
        >
          <CircleHelp :size="11" />
          去问
        </button>
      </template>
    </div>
  </div>
</template>
