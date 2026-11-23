<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Check, Clock, FileUp, LoaderCircle, Plus, X } from 'lucide-vue-next'
import { api } from '@/api/client'
import type {
  AssignmentDetail,
  AssignmentList,
  AssignmentRow,
  SubmissionDto,
  SubmissionRoster,
} from '@/api/client'
import { useAuth } from '@/composables/useAuth'

const route = useRoute()
const { user, authEnabled } = useAuth()

const teacher = computed(() => user.value?.role === 'teacher' || !authEnabled.value)

const rows = ref<AssignmentRow[]>([])
const pendingCount = ref(0)
const loading = ref(false)
const detail = ref<AssignmentDetail | null>(null)
const currentId = ref('')

const answers = ref<Record<string, string>>({})
const submission = ref<SubmissionDto | null>(null)
const editing = ref(false)
const submitting = ref(false)

const roster = ref<SubmissionRoster['items']>([])
const selectedSubmission = ref<SubmissionDto | null>(null)
const scoreDrafts = ref<Record<string, number | string>>({})
const feedbackDrafts = ref<Record<string, string>>({})
const savingItemId = ref('')

const errorMsg = ref('')

const dialogOpen = ref(false)
const importing = ref(false)
const dialogError = ref('')
const notice = ref('')
const mode = ref<'single' | 'markdown'>('single')
const chapters = ref<{ id: string; title: string }[]>([])
const singleForm = ref({ due: '', chapter_id: '' })
const singleItems = ref([{ type: 'short', stem: '', reference: '', rubricText: '', score: 10 }])
const TEMPLATE = `# 新作业

### 题目 1 | 简答 | 10 分
题干写在这里
参考答案: 
评分要点: 要点一=4; 要点二=3; 要点三=3
`
const form = ref({ title: '', due: '', content: TEMPLATE })

const NAMES: Record<string, string> = {
  demo_user: '李金阳',
  stu_lin: '林晓',
  stu_zhao: '赵一鸣',
  teacher: '教师',
}

const SOURCE_LABEL: Record<string, string> = {
  llm: '模型批改',
  rule: '规则初评',
  mixed: '模型 + 规则',
  teacher: '教师已改',
}

const VERDICT: Record<string, { label: string; cls: string }> = {
  correct: { label: '正确', cls: 'bg-success/10 text-success' },
  partial: { label: '部分', cls: 'bg-warn/10 text-warn' },
  wrong: { label: '错误', cls: 'bg-danger/10 text-danger' },
}

function fmtDate(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  const hh = String(date.getHours()).padStart(2, '0')
  const mm = String(date.getMinutes()).padStart(2, '0')
  return `${date.getMonth() + 1} 月 ${date.getDate()} 日 ${hh}:${mm}`
}

function statusLabel(row: AssignmentRow) {
  if (teacher.value) {
    if (row.status === 'closed') return '已关闭'
    if (row.status === 'draft') return '草稿'
    return '已发布'
  }
  if (row.my_status === 'graded') return `${row.my_score ?? 0}/${row.total_score}`
  if (row.my_status === 'grading' || row.my_status === 'submitted') return '批改中'
  if (row.my_status === 'failed') return '待复核'
  return '待提交'
}

function statusCls(row: AssignmentRow) {
  if (!teacher.value && row.my_status === 'graded') return 'bg-success/10 text-success'
  if (!teacher.value && row.my_status !== 'todo') return 'bg-warn/10 text-warn'
  return 'bg-tint text-muted'
}

async function loadRows() {
  loading.value = true
  try {
    const data = await api.get<AssignmentList>('/assignments')
    rows.value = data.items
    pendingCount.value = data.pending
  } catch (exc) {
    errorMsg.value = exc instanceof Error ? exc.message : '加载作业失败'
  } finally {
    loading.value = false
  }
}

async function refreshDetail() {
  if (!currentId.value) return
  try {
    const data = await api.get<AssignmentDetail>(`/assignments/${currentId.value}`)
    detail.value = data
    if (!teacher.value) submission.value = data.my_submission ?? null
  } catch {
    /* 保留当前详情，统计刷新失败不影响改分 */
  }
}

async function loadRoster(id: string) {
  if (!teacher.value) return
  try {
    roster.value = (await api.get<SubmissionRoster>(`/assignments/${id}/submissions`)).items
  } catch {
    roster.value = []
  }
}

async function open(id: string) {
  if (!id) return
  currentId.value = id
  errorMsg.value = ''
  selectedSubmission.value = null
  try {
    const data = await api.get<AssignmentDetail>(`/assignments/${id}`)
    detail.value = data
    submission.value = data.my_submission ?? null
    editing.value = !teacher.value && !submission.value
    answers.value = {}
    for (const item of data.items) {
      const answered = submission.value?.items.find((entry) => entry.item_id === item.id)
      answers.value[item.id] = answered?.answer ?? ''
    }
    await loadRoster(id)
  } catch (exc) {
    detail.value = null
    errorMsg.value = exc instanceof Error ? exc.message : '打开作业失败'
  }
}

async function submitWork() {
  const current = detail.value
  if (!current || submitting.value) return
  submitting.value = true
  errorMsg.value = ''
  try {
    submission.value = await api.post<SubmissionDto>(`/assignments/${current.id}/submissions`, {
      items: current.items.map((item) => ({ item_id: item.id, answer: answers.value[item.id] ?? '' })),
    })
    editing.value = false
    await loadRows()
  } catch (exc) {
    errorMsg.value = exc instanceof Error ? exc.message : '提交失败'
  } finally {
    submitting.value = false
  }
}

function startEditing() {
  editing.value = true
  errorMsg.value = ''
}

async function openSubmission(submissionId: string) {
  try {
    const data = await api.get<SubmissionDto>(`/submissions/${submissionId}`)
    selectedSubmission.value = data
    scoreDrafts.value = {}
    feedbackDrafts.value = {}
    for (const item of data.items) {
      scoreDrafts.value[item.item_id] = item.score
      feedbackDrafts.value[item.item_id] = item.feedback
    }
  } catch (exc) {
    errorMsg.value = exc instanceof Error ? exc.message : '读取提交失败'
  }
}

async function saveItem(itemId: string) {
  const current = selectedSubmission.value
  const draft = scoreDrafts.value[itemId]
  if (!current || draft === '' || Number.isNaN(Number(draft))) return
  savingItemId.value = itemId
  try {
    selectedSubmission.value = await api.patch<SubmissionDto>(
      `/submissions/${current.submission_id}/items/${itemId}`,
      { score: Number(draft), feedback: feedbackDrafts.value[itemId] ?? '' },
    )
    await loadRoster(currentId.value)
    await Promise.all([refreshDetail(), loadRows()])
    if (submission.value?.submission_id === current.submission_id) {
      submission.value = selectedSubmission.value
    }
  } catch (exc) {
    errorMsg.value = exc instanceof Error ? exc.message : '改分失败'
  } finally {
    savingItemId.value = ''
  }
}

function openDialog() {
  dialogOpen.value = true
  dialogError.value = ''
  notice.value = ''
  mode.value = 'single'
  singleForm.value = { due: '', chapter_id: '' }
  singleItems.value = [{ type: 'short', stem: '', reference: '', rubricText: '', score: 10 }]
  form.value = { title: '', due: '', content: TEMPLATE }
  void loadChapters()
}

async function submitImport() {
  if (importing.value) return
  if (!form.value.content.trim()) {
    dialogError.value = '内容不能为空'
    return
  }
  importing.value = true
  dialogError.value = ''
  try {
    const file = new File([form.value.content], 'assignment.md', { type: 'text/markdown' })
    const data = new FormData()
    data.append('file', file)
    if (form.value.title.trim()) data.append('title', form.value.title.trim())
    if (singleForm.value.due) data.append('due_at', new Date(singleForm.value.due).toISOString())
    if (singleForm.value.chapter_id) data.append('chapter_id', singleForm.value.chapter_id)
    const created = await api.upload<{ id: string; warnings?: string[] }>('/assignments/import', data)
    dialogOpen.value = false
    notice.value = created.warnings?.length ? created.warnings.join('；') : ''
    await loadRows()
    await open(created.id)
  } catch (exc) {
    dialogError.value = exc instanceof Error ? exc.message : '导入失败'
  } finally {
    importing.value = false
  }
}

function parsePoints(text: string, score: number) {
  const parts = text
    .split(/[;；\n]/)
    .map((part) => part.trim())
    .filter(Boolean)
  if (!parts.length) return [{ text: '答出核心结论', score }]
  const parsed = parts.map((part) => {
    const match = part.match(/^(.+?)=([0-9]+)$/)
    return match ? { text: match[1].trim(), score: Number(match[2]) } : { text: part, score: 0 }
  })
  const total = parsed.reduce((sum, point) => sum + point.score, 0)
  if (!total) {
    const even = Math.floor(score / parsed.length)
    return parsed.map((point, index) => ({
      ...point,
      score: index === parsed.length - 1 ? score - even * (parsed.length - 1) : even,
    }))
  }
  const scaled = parsed.map((point) => ({
    ...point,
    score: Math.max(0, Math.round((point.score * score) / total)),
  }))
  const diff = score - scaled.reduce((sum, point) => sum + point.score, 0)
  scaled[scaled.length - 1].score = Math.max(0, scaled[scaled.length - 1].score + diff)
  return scaled
}

function addSingleItem() {
  singleItems.value.push({ type: 'short', stem: '', reference: '', rubricText: '', score: 10 })
}

function removeSingleItem(index: number) {
  if (singleItems.value.length > 1) singleItems.value.splice(index, 1)
}

async function submitSingle() {
  if (importing.value) return
  const title = form.value.title.trim()
  if (!title) {
    dialogError.value = '先填作业标题'
    return
  }
  const scoreOf = (value: number) => Number(value) || 10
  const items = singleItems.value.map((row) => ({
    type: row.type,
    stem: row.stem.trim(),
    reference: row.reference.trim(),
    score: scoreOf(row.score),
    rubric: parsePoints(row.rubricText, scoreOf(row.score)),
  }))
  if (items.some((item) => !item.stem)) {
    dialogError.value = '每道题都要填题干'
    return
  }
  importing.value = true
  dialogError.value = ''
  try {
    const created = await api.post<{ id: string }>('/assignments', {
      title,
      chapter_id: singleForm.value.chapter_id || null,
      due_at: singleForm.value.due ? new Date(singleForm.value.due).toISOString() : null,
      status: 'published',
      items,
    })
    dialogOpen.value = false
    notice.value = ''
    await loadRows()
    await open(created.id)
  } catch (exc) {
    dialogError.value = exc instanceof Error ? exc.message : '创建失败'
  } finally {
    importing.value = false
  }
}

async function toggleStatus() {
  const current = detail.value
  if (!current) return
  try {
    await api.patch(`/assignments/${current.id}`, {
      status: current.status === 'closed' ? 'published' : 'closed',
    })
    await loadRows()
    await open(current.id)
  } catch (exc) {
    errorMsg.value = exc instanceof Error ? exc.message : '更新状态失败'
  }
}

async function removeAssignment() {
  const current = detail.value
  if (!current) return
  if (!window.confirm(`删除《${current.title}》？提交与批改记录会一并删除。`)) return
  try {
    await api.del(`/assignments/${current.id}`)
    detail.value = null
    currentId.value = ''
    await loadRows()
    const next = rows.value[0]?.id
    if (next) await open(next)
  } catch (exc) {
    errorMsg.value = exc instanceof Error ? exc.message : '删除失败'
  }
}

async function loadChapters() {
  try {
    chapters.value = (await api.get<{ items: { id: string; title: string }[] }>('/courses/course_cn/chapters')).items
  } catch {
    chapters.value = []
  }
}

function studentName(userKey: string) {
  return NAMES[userKey] ?? userKey
}

async function boot() {
  await loadRows()
  const focus = typeof route.query.focus === 'string' ? route.query.focus : ''
  const target = focus && rows.value.some((row) => row.id === focus) ? focus : rows.value[0]?.id
  if (target) await open(target)
}

watch(
  () => route.query.focus,
  (value) => {
    if (typeof value === 'string' && value && value !== currentId.value) void open(value)
  },
)

onMounted(boot)
</script>

<template>
  <div class="animate-fade-up px-9 py-8">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="flex items-center gap-2">
        <h1 class="text-[26px] font-semibold leading-tight tracking-[-0.025em]">作业</h1>
        <span v-if="!teacher && pendingCount" class="rounded-full bg-warn/10 px-2 py-0.5 text-[10px] text-warn">
          待交 {{ pendingCount }}
        </span>
      </div>
      <button
        v-if="teacher"
        class="pill-btn h-9 border border-line bg-surface text-subink hover:border-line-strong hover:text-ink"
        @click="openDialog"
      >
        <Plus :size="13" />
        新建作业
      </button>
    </div>

    <p v-if="errorMsg" class="mt-3 text-[11.5px] text-danger">{{ errorMsg }}</p>
    <p
      v-if="notice"
      class="mt-3 flex items-start justify-between gap-3 rounded-lg border border-warn/30 bg-warn/5 px-3 py-2 text-[11px] text-warn"
    >
      <span>{{ notice }}</span>
      <button class="text-[10px] text-warn/70 hover:text-warn" @click="notice = ''">知道了</button>
    </p>

    <div class="mt-5 grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
      <aside class="space-y-2">
        <div v-if="loading && !rows.length" class="surface p-6 text-center text-[12px] text-muted">加载中</div>
        <div v-else-if="!rows.length" class="surface p-6 text-center">
          <p class="text-[12.5px] font-medium text-ink">还没有作业</p>
          <p v-if="teacher" class="mt-1 text-[11px] text-muted">点右上「新建作业」上传题目。</p>
          <p v-else class="mt-1 text-[11px] text-muted">等老师发布后这里会出现。</p>
        </div>

        <button
          v-for="row in rows"
          :key="row.id"
          class="w-full rounded-2xl border px-4 py-3 text-left transition"
          :class="
            row.id === currentId
              ? 'border-brand/50 bg-surface ring-1 ring-brand/15 shadow-[0_6px_20px_-16px_rgba(16,24,40,0.5)]'
              : 'border-line bg-surface/70 hover:border-line-strong'
          "
          @click="open(row.id)"
        >
          <div class="flex items-start justify-between gap-2">
            <span class="text-[12.5px] font-medium leading-snug text-ink">{{ row.title }}</span>
            <span class="shrink-0 rounded-full px-1.5 py-0.5 text-[9.5px]" :class="statusCls(row)">
              {{ statusLabel(row) }}
            </span>
          </div>
          <div class="mt-1.5 flex items-center gap-1 text-[10px] text-muted">
            <Clock :size="10" />
            {{ fmtDate(row.due_at) || '未设截止' }}
          </div>
          <div class="mt-0.5 text-[10px] text-muted">
            {{ row.chapter_title || '未分章节' }} · {{ row.item_count }} 题 / {{ row.total_score }} 分
          </div>
          <div v-if="teacher && row.submitted_count !== undefined" class="mt-1 text-[10px] text-muted">
            已交 {{ row.submitted_count }} · 平均 {{ row.avg_score ?? '—' }}
          </div>
        </button>
      </aside>

      <section v-if="detail" class="surface p-6">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 class="text-[17px] font-semibold tracking-tight">{{ detail.title }}</h2>
            <p class="mt-1 text-[10.5px] text-muted">
              {{ detail.item_count }} 题 · {{ detail.total_score }} 分 · 截止 {{ fmtDate(detail.due_at) || '未设' }}
            </p>
          </div>
          <div class="flex flex-wrap items-center justify-end gap-2">
            <span
              v-if="teacher"
              class="rounded-full px-2 py-1 text-[10.5px]"
              :class="
                detail.status === 'draft'
                  ? 'bg-warn/10 text-warn'
                  : detail.status === 'closed'
                    ? 'bg-tint text-muted'
                    : 'bg-success/10 text-success'
              "
            >
              {{ detail.status === 'draft' ? '草稿' : detail.status === 'closed' ? '已关闭' : '已发布' }}
            </span>
            <template v-if="teacher">
              <button
                class="pill-btn h-7 border border-line bg-surface px-2.5 text-[10.5px] text-subink hover:border-line-strong hover:text-ink"
                @click="toggleStatus"
              >
                {{ detail.status === 'closed' ? '重新发布' : '关闭提交' }}
              </button>
              <button
                class="pill-btn h-7 border border-line bg-surface px-2.5 text-[10.5px] text-danger hover:border-danger/40"
                @click="removeAssignment"
              >
                删除
              </button>
            </template>
            <span
              v-if="!teacher"
              class="rounded-full px-2 py-1 text-[10.5px]"
              :class="submission?.status === 'graded' ? 'bg-success/10 text-success' : 'bg-tint text-muted'"
            >
              {{ submission?.status === 'graded' ? `${submission.score}/${submission.max_score}` : '待提交' }}
            </span>
          </div>
        </div>

        <!-- 教师：题目与提交 -->
        <template v-if="teacher">
          <div class="mt-4 space-y-2">
            <details v-for="item in detail.items" :key="item.id" class="rounded-xl border border-line px-3.5 py-2.5">
              <summary class="flex cursor-pointer items-baseline justify-between gap-3 text-[12px]">
                <span class="font-medium text-ink">{{ item.ordinal }}. {{ item.stem }}</span>
                <span class="shrink-0 text-[10px] text-muted">{{ item.type === 'calc' ? '计算' : '简答' }} · {{ item.score }} 分</span>
              </summary>
              <p class="mt-2 text-[11px] leading-relaxed text-subink">{{ item.reference }}</p>
              <div class="mt-1.5 flex flex-wrap gap-1">
                <span
                  v-for="point in item.rubric ?? []"
                  :key="point.text"
                  class="rounded-full bg-tint px-1.5 py-0.5 text-[9.5px] text-muted"
                >
                  {{ point.text }} {{ point.score }}
                </span>
              </div>
            </details>
          </div>

          <div class="mt-6">
            <div class="flex items-center justify-between">
              <h3 class="text-[12.5px] font-medium">提交 {{ roster.length }}</h3>
              <span v-if="detail.stats" class="text-[10px] text-muted">
                已批 {{ detail.stats.graded }} · 待批 {{ detail.stats.ungraded }} · 平均 {{ detail.stats.avg_score ?? '—' }}
                <span v-if="detail.stats.needs_review" class="text-warn">· {{ detail.stats.needs_review }} 题待复核</span>
              </span>
            </div>
            <div v-if="!roster.length" class="mt-2 text-[11px] text-muted">还没有学生提交。</div>
            <div v-else class="mt-2 divide-y divide-line rounded-xl border border-line">
              <button
                v-for="row in roster"
                :key="row.submission_id"
                class="flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-left transition hover:bg-tint-soft"
                @click="openSubmission(row.submission_id)"
              >
                <span class="text-[11.5px] text-ink">{{ studentName(row.user_key) }}</span>
                <span class="flex items-center gap-2 text-[10px] text-muted">
                  <span v-if="row.needs_review_count" class="text-warn">{{ row.needs_review_count }} 题待复核</span>
                  <span class="font-mono">{{ row.score }}/{{ row.max_score }}</span>
                  <span class="rounded-full bg-tint px-1.5 py-0.5">{{ SOURCE_LABEL[row.source] ?? row.source }}</span>
                </span>
              </button>
            </div>

            <div v-if="selectedSubmission" class="mt-3 rounded-xl border border-brand/30 bg-surface p-4">
              <div class="flex items-center justify-between">
                <span class="text-[12px] font-medium">
                  {{ studentName(selectedSubmission.user_key) }} · {{ selectedSubmission.score }} / {{ selectedSubmission.max_score }}
                  <span class="ml-1 text-[10px] font-normal text-muted">{{ SOURCE_LABEL[selectedSubmission.source] }}</span>
                </span>
                <button class="grid h-6 w-6 place-items-center rounded-full text-muted hover:bg-tint" @click="selectedSubmission = null">
                  <X :size="13" />
                </button>
              </div>

              <div v-for="item in selectedSubmission.items" :key="item.item_id" class="mt-3 rounded-lg border border-line p-3">
                <div class="flex items-baseline justify-between gap-2">
                  <span class="text-[11.5px] font-medium">{{ item.ordinal }}. {{ item.stem }}</span>
                  <span class="shrink-0 text-[10px] text-muted">{{ item.score }}/{{ item.max_score }}</span>
                </div>
                <p class="mt-1 text-[10.5px] leading-relaxed text-muted">作答：{{ item.answer || '（空）' }}</p>
                <p class="mt-1 text-[10.5px] leading-relaxed text-subink">{{ item.feedback }}</p>
                <div class="mt-2 flex items-center gap-2">
                  <input
                    v-model="scoreDrafts[item.item_id]"
                    type="number"
                    min="0"
                    :max="item.max_score"
                    class="h-7 w-16 rounded-md border border-line bg-surface px-2 text-[11px] outline-none focus:border-brand/60"
                  />
                  <input
                    v-model="feedbackDrafts[item.item_id]"
                    class="h-7 flex-1 rounded-md border border-line bg-surface px-2 text-[11px] outline-none focus:border-brand/60"
                    placeholder="评语"
                  />
                  <button
                    class="pill-btn h-7 border border-line bg-tint px-2 text-[10.5px] text-subink hover:text-ink"
                    :disabled="savingItemId === item.item_id"
                    @click="saveItem(item.item_id)"
                  >
                    <LoaderCircle v-if="savingItemId === item.item_id" :size="11" class="animate-spin" />
                    <Check v-else :size="11" />
                    保存
                  </button>
                </div>
              </div>
            </div>
          </div>
        </template>

        <!-- 学生：答题 -->
        <template v-else>
          <div v-if="editing" class="mt-4 space-y-3">
            <div v-for="item in detail.items" :key="item.id" class="rounded-xl border border-line p-4">
              <div class="flex items-baseline justify-between gap-3">
                <p class="text-[12.5px] font-medium leading-relaxed">{{ item.ordinal }}. {{ item.stem }}</p>
                <span class="shrink-0 text-[10px] text-muted">{{ item.type === 'calc' ? '计算' : '简答' }} · {{ item.score }} 分</span>
              </div>
              <textarea
                v-model="answers[item.id]"
                rows="4"
                class="mt-2 w-full rounded-lg border border-line bg-surface px-3 py-2 text-[12px] leading-relaxed outline-none transition focus:border-brand/60"
                placeholder="写解答，计算题写出关键步骤"
              />
            </div>
            <div class="flex items-center justify-between">
              <span v-if="submission" class="text-[10.5px] text-muted">重新提交会覆盖上一次作答。</span>
              <button
                class="ml-auto flex h-9 items-center gap-1.5 rounded-lg bg-brand px-4 text-[12px] font-medium text-white transition hover:bg-[#2251d6] disabled:opacity-60"
                :disabled="submitting"
                @click="submitWork"
              >
                <LoaderCircle v-if="submitting" :size="13" class="animate-spin" />
                {{ submitting ? '批改中' : '提交作业' }}
              </button>
            </div>
          </div>

          <template v-else-if="submission">
            <div class="mt-4 rounded-xl border border-line bg-tint-soft p-5">
              <div class="flex items-center justify-between">
                <p class="text-[24px] font-semibold leading-none tracking-tight">
                  {{ submission.score }}<span class="text-[12px] font-normal text-muted"> / {{ submission.max_score }}</span>
                </p>
                <span class="rounded-full bg-surface px-2 py-0.5 text-[10px] text-muted">
                  {{ SOURCE_LABEL[submission.source] ?? submission.source }}
                </span>
              </div>
              <p class="mt-2 text-[11px] text-muted">{{ submission.overall_comment }}</p>
            </div>

            <div v-for="item in submission.items" :key="item.item_id" class="mt-3 rounded-xl border border-line p-4">
              <div class="flex items-baseline justify-between gap-3">
                <p class="text-[12px] font-medium leading-relaxed">{{ item.ordinal }}. {{ item.stem }}</p>
                <span class="shrink-0 text-[10px] text-muted">{{ item.score }}/{{ item.max_score }}</span>
              </div>
              <p class="mt-1.5 text-[10.5px] leading-relaxed text-muted">作答：{{ item.answer || '（空）' }}</p>
              <p class="mt-1 text-[11px] leading-relaxed text-subink">{{ item.feedback }}</p>
              <div class="mt-2 flex flex-wrap gap-1">
                <span
                  v-for="point in item.points"
                  :key="point.point"
                  class="rounded-full px-1.5 py-0.5 text-[9.5px]"
                  :class="point.hit ? 'bg-success/10 text-success' : 'bg-tint text-muted'"
                >
                  {{ point.hit ? '✓' : '×' }} {{ point.point }}
                </span>
              </div>
              <div class="mt-1.5 flex items-center gap-2">
                <span
                  class="rounded-full px-1.5 py-0.5 text-[9.5px]"
                  :class="VERDICT[item.verdict]?.cls ?? 'bg-tint text-muted'"
                >
                  {{ VERDICT[item.verdict]?.label ?? item.verdict }}
                </span>
                <span v-if="item.needs_review" class="text-[9.5px] text-warn">待复核</span>
              </div>
            </div>

            <div class="mt-4 flex justify-end">
              <button class="pill-btn h-8 border border-line bg-surface text-[11px] text-subink hover:text-ink" @click="startEditing">
                重新作答
              </button>
            </div>
          </template>

          <div v-else class="mt-6 rounded-xl border border-line p-6 text-center text-[11.5px] text-muted">
            这份作业还没有作答。
          </div>
        </template>
      </section>

      <section v-else class="surface grid min-h-[320px] place-items-center">
        <div class="text-center">
          <p class="text-[12.5px] font-medium text-ink">选一份作业</p>
          <p class="mt-1 text-[11px] text-muted">左侧列表打开后在这里作答或批改。</p>
        </div>
      </section>
    </div>

    <!-- 新建作业 -->
    <div
      v-if="dialogOpen"
      class="fixed inset-0 z-50 grid place-items-center bg-ink/25 px-6 py-10 backdrop-blur-sm"
      @click.self="dialogOpen = false"
    >
      <div class="max-h-[92vh] w-full max-w-[720px] overflow-y-auto rounded-2xl border border-line bg-surface p-5 shadow-2xl">
        <div class="flex items-center justify-between">
          <h3 class="text-[15px] font-semibold">新建作业</h3>
          <button class="grid h-7 w-7 place-items-center rounded-full text-muted hover:bg-tint" @click="dialogOpen = false">
            <X :size="14" />
          </button>
        </div>

        <div class="mt-4 flex gap-1 rounded-lg bg-tint p-1">
          <button
            class="flex-1 rounded-md px-3 py-1.5 text-[11.5px] transition"
            :class="mode === 'single' ? 'bg-surface text-ink shadow-sm' : 'text-muted hover:text-ink'"
            @click="mode = 'single'"
          >
            逐题填写
          </button>
          <button
            class="flex-1 rounded-md px-3 py-1.5 text-[11.5px] transition"
            :class="mode === 'markdown' ? 'bg-surface text-ink shadow-sm' : 'text-muted hover:text-ink'"
            @click="mode = 'markdown'"
          >
            Markdown 粘贴
          </button>
        </div>

        <div class="mt-3 grid gap-3 sm:grid-cols-[1fr_170px_150px]">
          <label class="flex flex-col gap-1 text-[10.5px] text-muted">
            标题
            <input
              v-model="form.title"
              class="h-9 rounded-lg border border-line bg-surface px-3 text-[12px] text-ink outline-none focus:border-brand/60"
              :placeholder="mode === 'single' ? '第 4 周作业' : '留空用文件里的'"
            />
          </label>
          <label class="flex flex-col gap-1 text-[10.5px] text-muted">
            截止
            <input
              v-model="singleForm.due"
              type="datetime-local"
              class="h-9 rounded-lg border border-line bg-surface px-3 text-[12px] text-ink outline-none focus:border-brand/60"
            />
          </label>
          <label class="flex flex-col gap-1 text-[10.5px] text-muted">
            章节
            <select
              v-model="singleForm.chapter_id"
              class="h-9 rounded-lg border border-line bg-surface px-2 text-[12px] text-ink outline-none focus:border-brand/60"
            >
              <option value="">不挂章节</option>
              <option v-for="chapter in chapters" :key="chapter.id" :value="chapter.id">{{ chapter.title }}</option>
            </select>
          </label>
        </div>

        <template v-if="mode === 'single'">
          <div class="mt-3 space-y-2.5">
            <div v-for="(row, index) in singleItems" :key="index" class="rounded-xl border border-line p-3">
              <div class="flex items-center justify-between">
                <span class="text-[11px] text-muted">第 {{ index + 1 }} 题</span>
                <div class="flex items-center gap-2">
                  <select v-model="row.type" class="h-7 rounded-md border border-line bg-surface px-2 text-[11px] text-ink">
                    <option value="short">简答</option>
                    <option value="calc">计算</option>
                  </select>
                  <input
                    v-model.number="row.score"
                    type="number"
                    min="1"
                    max="100"
                    class="h-7 w-14 rounded-md border border-line bg-surface px-2 text-[11px]"
                  />
                  <span class="text-[10px] text-muted">分</span>
                  <button
                    v-if="singleItems.length > 1"
                    class="text-[10.5px] text-muted hover:text-danger"
                    @click="removeSingleItem(index)"
                  >
                    删除
                  </button>
                </div>
              </div>
              <textarea
                v-model="row.stem"
                rows="2"
                placeholder="题干"
                class="mt-2 w-full rounded-lg border border-line bg-surface px-3 py-2 text-[12px] leading-relaxed outline-none focus:border-brand/60"
              />
              <textarea
                v-model="row.reference"
                rows="2"
                placeholder="参考答案"
                class="mt-1.5 w-full rounded-lg border border-line bg-surface px-3 py-2 text-[11.5px] leading-relaxed outline-none focus:border-brand/60"
              />
              <input
                v-model="row.rubricText"
                placeholder="评分要点，用 ; 分隔并标分值，如 确认接收通道=4; 同步序号=3"
                class="mt-1.5 h-8 w-full rounded-lg border border-line bg-surface px-3 text-[11px] outline-none focus:border-brand/60"
              />
            </div>
          </div>
          <button class="mt-2 text-[11px] text-brand hover:underline" @click="addSingleItem">+ 加一题</button>
        </template>

        <label v-else class="mt-3 flex flex-col gap-1 text-[10.5px] text-muted">
          题目（Markdown）
          <textarea
            v-model="form.content"
            rows="14"
            class="w-full rounded-lg border border-line bg-surface px-3 py-2 font-mono text-[11.5px] leading-relaxed text-ink outline-none focus:border-brand/60"
          />
        </label>

        <p v-if="dialogError" class="mt-2 text-[11px] text-danger">{{ dialogError }}</p>

        <div class="mt-4 flex items-center justify-between">
          <span class="flex items-center gap-1 text-[10px] text-muted">
            <FileUp :size="11" />
            {{ mode === 'single' ? '要点分值会自动对齐题分' : '解析后可直接发布' }}
          </span>
          <button
            class="flex h-9 items-center gap-1.5 rounded-lg bg-brand px-4 text-[12px] font-medium text-white transition hover:bg-[#2251d6] disabled:opacity-60"
            :disabled="importing"
            @click="mode === 'single' ? submitSingle() : submitImport()"
          >
            <LoaderCircle v-if="importing" :size="13" class="animate-spin" />
            {{ importing ? '创建中' : '创建并发布' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
