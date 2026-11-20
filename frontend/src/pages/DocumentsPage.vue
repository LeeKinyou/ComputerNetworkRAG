<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import {
  BookMarked,
  ChevronRight,
  FileCode2,
  FileText,
  FileType2,
  Layers,
  Presentation,
  Quote,
  RefreshCw,
  Upload,
} from 'lucide-vue-next'
import { ApiError, api, type DocumentCitations, type DocumentSummary } from '@/api/client'

const COURSE_ID = 'course_cn'

interface DocRow {
  id: string
  title: string
  type: string
  size: string
  status: string
  chunkCount: number
  chapter: string
  updated: string
  citations: number
  quality: { label: string; tone: string }
}

const typeIcon: Record<string, typeof FileText> = {
  pdf: FileText,
  md: FileCode2,
  docx: FileType2,
  pptx: Presentation,
  txt: FileText,
}

const statusText: Record<string, string> = {
  ready: '已就绪',
  parsing: '解析中',
  failed: '失败',
}

const statusTone: Record<string, string> = {
  ready: 'bg-success',
  parsing: 'bg-brand animate-soft-pulse',
  failed: 'bg-[#E36A6A]',
}

const docList = ref<DocRow[]>([])
const chapters = ref<{ id: string; title: string }[]>([])
const selectedId = ref('')
const chunkList = ref<{ id: string; text: string; topic: string; score: number }[]>([])
const citationInfo = ref<DocumentCitations | null>(null)
const citationsLoading = ref(false)
const uploading = ref(false)
const deleting = ref(false)
const loading = ref(true)
const notice = ref('')
const fileInput = ref<HTMLInputElement | null>(null)

const EMPTY_DOC: DocRow = {
  id: '',
  title: '还没有课程文档',
  type: 'txt',
  size: '—',
  status: 'ready',
  chunkCount: 0,
  chapter: '—',
  updated: '—',
  citations: 0,
  quality: { label: '—', tone: 'text-muted' },
}

const selected = computed(
  () => docList.value.find((item) => item.id === selectedId.value) ?? docList.value[0] ?? EMPTY_DOC,
)

function extOf(filename: string, mime: string): string {
  const name = filename.toLowerCase()
  for (const key of ['pdf', 'docx', 'pptx', 'md', 'txt']) {
    if (name.endsWith(`.${key}`)) return key
  }
  if (mime.includes('pdf')) return 'pdf'
  if (mime.includes('word')) return 'docx'
  if (mime.includes('presentation')) return 'pptx'
  if (mime.includes('markdown')) return 'md'
  return 'txt'
}

function formatSize(bytes: number): string {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDay(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function mapDoc(item: DocumentSummary): DocRow {
  const chapter = chapters.value.find((entry) => entry.id === item.chapter_id)
  return {
    id: item.id,
    title: item.title || item.filename,
    type: extOf(item.filename, item.mime),
    size: formatSize(item.size),
    status: item.status === 'failed' ? 'failed' : item.status === 'parsing' ? 'parsing' : 'ready',
    chunkCount: item.chunk_count,
    chapter: chapter?.title ?? '未挂章节',
    updated: formatDay(item.created_at),
    citations: item.citation_count ?? 0,
    quality:
      item.status === 'failed'
        ? { label: '需修复', tone: 'text-[#E36A6A]' }
        : item.chunk_count
          ? { label: '好', tone: 'text-success' }
          : { label: '待解析', tone: 'text-muted' },
  }
}

async function loadDocs() {
  loading.value = true
  try {
    const [documents, chapterList] = await Promise.all([
      api.get<{ items: DocumentSummary[] }>(`/courses/${COURSE_ID}/documents`),
      api.get<{ items: { id: string; title: string }[] }>(`/courses/${COURSE_ID}/chapters`),
    ])
    chapters.value = chapterList.items
    docList.value = documents.items.map(mapDoc)
    if (!selectedId.value || !docList.value.some((item) => item.id === selectedId.value)) {
      selectedId.value = docList.value[0]?.id ?? ''
    }
    notice.value = ''
  } catch (error) {
    notice.value = error instanceof ApiError ? error.message : '知识库加载失败'
  } finally {
    loading.value = false
  }
}

async function loadChunks() {
  if (!selectedId.value) {
    chunkList.value = []
    return
  }
  try {
    const result = await api.get<{
      items: { chunk_id: string; section_path: string[]; page: number | null; text: string }[]
    }>(`/documents/${selectedId.value}/chunks?limit=50`)
    chunkList.value = result.items.map((chunk) => ({
      id: chunk.chunk_id,
      text: chunk.text,
      topic: chunk.section_path?.length
        ? chunk.section_path[chunk.section_path.length - 1]
        : chunk.page
          ? `第 ${chunk.page} 页`
          : '课程材料',
      score: 1,
    }))
  } catch {
    chunkList.value = []
  }
}

async function loadCitations() {
  if (!selectedId.value) {
    citationInfo.value = null
    return
  }
  citationsLoading.value = true
  try {
    citationInfo.value = await api.get<DocumentCitations>(
      `/documents/${selectedId.value}/citations?limit=3`,
    )
  } catch {
    citationInfo.value = null
  } finally {
    citationsLoading.value = false
  }
}

const citedChunks = computed(() => citationInfo.value?.chunk_counts ?? {})

function pickFile() {
  fileInput.value?.click()
}

async function onFile(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  uploading.value = true
  notice.value = ''
  try {
    const form = new FormData()
    form.append('file', file)
    form.append('title', file.name.replace(/\.[^.]+$/, ''))
    await api.upload(`/courses/${COURSE_ID}/documents`, form)
    await loadDocs()
    notice.value = `${file.name} 已入库`
  } catch (error) {
    notice.value =
      error instanceof ApiError
        ? { UNSUPPORTED_FILE_TYPE: '这个格式暂不支持', FILE_TOO_LARGE: '文件超过了 20 MB', DOCUMENT_TEXT_UNAVAILABLE: '没有读到可用的文字' }[error.code] ??
          error.message
        : '上传失败'
  } finally {
    uploading.value = false
    target.value = ''
  }
}

const totalChunks = computed(() => docList.value.reduce((sum, doc) => sum + doc.chunkCount, 0))
const chapterCount = computed(
  () => new Set(docList.value.map((doc) => doc.chapter).filter((item) => item !== '未挂章节')).size,
)

async function removeSelected() {
  const doc = selected.value
  if (!doc.id || doc.id.startsWith('doc_seed')) return
  if (!window.confirm(`删除《${doc.title}》？该文档的分块与索引会一并移除。`)) return
  deleting.value = true
  notice.value = ''
  try {
    await api.del(`/documents/${doc.id}`)
    await loadDocs()
    await loadChunks()
    await loadCitations()
    notice.value = `${doc.title} 已移出知识库`
  } catch (error) {
    notice.value = error instanceof ApiError ? error.message : '删除失败'
  } finally {
    deleting.value = false
  }
}

watch(selectedId, () => {
  void loadChunks()
  void loadCitations()
})

onMounted(() => {
  void loadDocs().then(() => {
    void loadChunks()
    void loadCitations()
  })
})
</script>

<template>
  <div class="animate-fade-up px-9 py-8">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="text-[26px] font-semibold leading-tight tracking-[-0.025em]">知识库</h1>
        <p class="mt-1.5 max-w-[600px] text-[12.5px] leading-relaxed text-muted">
          课程材料的统一入口：解析、分块、建索引，并把每个分块挂到知识点上。
        </p>
      </div>
      <button
        class="pill-btn h-9 bg-ink pl-3.5 text-canvas hover:opacity-90 disabled:opacity-50"
        :disabled="uploading"
        @click="pickFile"
      >
        <Upload :size="15" />
        {{ uploading ? '正在入库…' : '上传文档' }}
      </button>
      <input ref="fileInput" type="file" class="hidden" accept=".md,.txt,.pdf,.docx,.pptx" @change="onFile" />
    </div>

    <section class="surface mt-5 grid grid-cols-2 divide-line md:grid-cols-4 md:divide-x">
      <div class="px-5 py-3.5">
        <div class="text-[10px] text-muted">文档</div>
        <div class="mt-1 text-[19px] font-semibold leading-none">{{ docList.length }}</div>
      </div>
      <div class="px-5 py-3.5">
        <div class="text-[10px] text-muted">分块</div>
        <div class="mt-1 text-[19px] font-semibold leading-none">{{ totalChunks }}</div>
      </div>
      <div class="px-5 py-3.5">
        <div class="text-[10px] text-muted">覆盖章节</div>
        <div class="mt-1 text-[19px] font-semibold leading-none">{{ chapterCount }}</div>
      </div>
      <div class="flex items-center justify-between px-5 py-3.5">
        <div>
          <div class="text-[10px] text-muted">索引</div>
          <div class="mt-1 flex items-center gap-1.5">
            <span class="h-1.5 w-1.5 rounded-full bg-success" />
            <span class="text-[12px] font-medium">实时索引</span>
          </div>
        </div>
        <button class="icon-btn" aria-label="刷新知识库" @click="loadDocs">
          <RefreshCw :size="14" />
        </button>
      </div>
    </section>

    <p v-if="notice" class="mt-3 rounded-xl border border-line bg-tint-soft px-3.5 py-2 text-[11px] text-subink">
      {{ notice }}
    </p>

    <div class="mt-4 grid gap-4 xl:grid-cols-[1fr_320px]">
      <div class="flex flex-col gap-4">
        <div
          class="flex h-[118px] cursor-pointer flex-col items-center justify-center gap-1.5 rounded-[18px] border border-dashed border-line-strong bg-surface/55 text-center transition-all duration-200 hover:border-brand/35 hover:bg-brand-soft/25"
          @click="pickFile"
        >
          <Upload :size="18" class="text-muted" />
          <p class="text-[12px] text-subink">点击选择课程文件</p>
          <p class="text-[10px] text-muted">md / txt / docx / pdf / pptx · 单个不超过 20 MB</p>
        </div>

        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-5 py-3.5">
            <div class="flex items-center gap-2">
              <h2 class="text-[12.5px] font-medium">全部文档</h2>
              <span class="rounded-md bg-tint px-1.5 py-0.5 text-[10px] text-muted">
                {{ docList.length }}
              </span>
            </div>
            <span class="text-[10.5px] text-muted">{{ loading ? '加载中…' : '按更新时间排序' }}</span>
          </header>

          <div
            class="hidden grid-cols-[1fr_76px_44px_44px_48px_62px_78px_16px] gap-3 border-b border-line px-5 py-2 text-[9.5px] text-muted md:grid"
          >
            <span>文档</span>
            <span>章节</span>
            <span>分块</span>
            <span>引用</span>
            <span>质量</span>
            <span>状态</span>
            <span>更新</span>
            <span />
          </div>

          <ul>
            <li
              v-for="doc in docList"
              :key="doc.id"
              class="grid cursor-pointer grid-cols-1 items-center gap-2 border-b border-line px-5 py-3 transition-colors last:border-b-0 md:grid-cols-[1fr_76px_44px_44px_48px_62px_78px_16px] md:gap-3"
              :class="selectedId === doc.id ? 'bg-brand-soft/35' : 'hover:bg-tint-soft'"
              @click="selectedId = doc.id"
            >
              <div class="flex min-w-0 items-center gap-2.5">
                <span class="grid h-8 w-8 shrink-0 place-items-center rounded-[10px] bg-tint text-muted">
                  <component :is="typeIcon[doc.type] ?? FileText" :size="14" />
                </span>
                <div class="min-w-0">
                  <p class="truncate text-[12px] text-subink">{{ doc.title }}</p>
                  <p class="mt-0.5 text-[9.5px] text-muted md:hidden">
                    {{ doc.type.toUpperCase() }} · {{ doc.chapter }} · {{ doc.chunkCount }} 分块 ·
                    被引用 {{ doc.citations }} 次
                  </p>
                </div>
              </div>
              <span class="hidden truncate text-[10px] text-muted md:block">{{ doc.chapter }}</span>
              <span class="hidden font-mono text-[10px] text-muted md:block">{{ doc.chunkCount }}</span>
              <span
                class="hidden font-mono text-[10px] md:block"
                :class="doc.citations ? 'text-subink' : 'text-muted'"
              >
                {{ doc.citations }}
              </span>
              <span class="hidden text-[9.5px] md:block" :class="doc.quality.tone">
                {{ doc.quality.label }}
              </span>
              <span class="hidden items-center gap-1.5 text-[10px] text-muted md:flex">
                <span class="h-1.5 w-1.5 rounded-full" :class="statusTone[doc.status]" />
                {{ statusText[doc.status] }}
              </span>
              <span class="hidden font-mono text-[9.5px] text-muted md:block">
                {{ doc.updated }}
              </span>
              <ChevronRight
                :size="13"
                class="hidden shrink-0 md:block"
                :class="selectedId === doc.id ? 'text-brand' : 'text-muted'"
              />
            </li>
            <li v-if="!loading && !docList.length" class="px-5 py-10 text-center text-[11px] text-muted">
              还没有文档，上传一份课件试试。
            </li>
          </ul>
        </section>
      </div>

      <section class="surface flex flex-col overflow-hidden">
        <header class="flex items-center justify-between border-b border-line px-4 py-3">
          <div class="flex items-center gap-1.5">
            <Layers :size="13" class="text-muted" />
            <h2 class="text-[11.5px] font-medium">切片预览</h2>
          </div>
          <button class="text-[9.5px] text-muted hover:text-subink" @click="loadChunks">刷新</button>
        </header>

        <div class="border-b border-line px-4 py-3">
          <p class="truncate text-[11.5px] font-medium text-ink">{{ selected.title }}</p>
          <p class="mt-0.5 text-[9.5px] text-muted">
            {{ selected.chunkCount }} 个分块 · {{ selected.size }} · {{ selected.chapter }}
          </p>
          <div class="mt-2 flex items-center gap-1.5 text-[9.5px] text-muted">
            <Quote :size="11" />
            <span>
              被 {{ selected.citations }} 个提问引用 · 命中
              {{ citationInfo?.chunk_total ?? 0 }} 个分块
            </span>
          </div>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto p-3">
          <div class="mb-2 flex items-center gap-1.5 px-1 text-[9.5px] text-muted">
            <BookMarked :size="11" />
            已映射到知识点
          </div>
          <div v-if="!chunkList.length" class="px-1 py-8 text-center text-[10.5px] text-muted">
            {{ loading ? '正在加载切片…' : '这份文档还没有可预览的分块。' }}
          </div>
          <div v-else class="flex flex-col gap-2">
            <article
              v-for="chunk in chunkList"
              :key="chunk.id"
              class="rounded-xl border border-line bg-surface px-3 py-2.5 transition-colors hover:border-line-strong"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="truncate rounded-full bg-brand-soft px-1.5 py-0.5 text-[9px] text-brand">
                  {{ chunk.topic }}
                </span>
                <span
                  v-if="citedChunks[chunk.id]"
                  class="shrink-0 rounded-full bg-tint px-1.5 py-0.5 font-mono text-[9px] text-subink"
                >
                  引用 {{ citedChunks[chunk.id] }}
                </span>
              </div>
              <p class="mt-1.5 line-clamp-4 text-[10.5px] leading-[1.65] text-subink">{{ chunk.text }}</p>
              <p class="mt-1.5 truncate font-mono text-[8.5px] text-muted">{{ chunk.id }}</p>
            </article>
          </div>
        </div>

        <div class="border-t border-line px-4 py-3">
          <div class="flex items-center justify-between text-[9.5px] text-muted">
            <span>被这些提问引用</span>
            <span class="font-mono">{{ citationInfo?.run_total ?? 0 }} 个</span>
          </div>
          <p v-if="citationsLoading" class="mt-2 text-[10px] text-muted">正在读取引用记录…</p>
          <p v-else-if="!citationInfo?.items.length" class="mt-2 text-[10px] text-muted">
            还没有问答引用过这份材料。
          </p>
          <div v-else class="mt-2 flex flex-col gap-1.5">
            <RouterLink
              v-for="hit in citationInfo.items"
              :key="hit.run_id"
              :to="{ path: '/chat', query: { q: hit.question } }"
              class="group rounded-lg border border-line px-2.5 py-1.5 transition-colors hover:border-line-strong"
            >
              <p class="line-clamp-2 text-[10px] leading-[1.55] text-subink group-hover:text-ink">
                {{ hit.question }}
              </p>
              <p class="mt-1 truncate font-mono text-[8.5px] text-muted">
                {{ formatDay(hit.created_at) }} · 命中 {{ hit.hit_chunks }} 个分块
              </p>
            </RouterLink>
          </div>
        </div>

        <div class="border-t border-line p-3">
          <button
            class="pill-btn h-8 w-full justify-center border border-line bg-tint-soft text-[10.5px] text-subink hover:border-line-strong"
            @click="loadChunks"
          >
            <RefreshCw :size="12" />
            重新读取该文档切片
          </button>
          <button
            v-if="selected.id && !selected.id.startsWith('doc_seed')"
            class="pill-btn mt-2 h-8 w-full justify-center border border-line bg-tint-soft text-[10.5px] text-[#E36A6A] hover:border-[#E36A6A]/40 disabled:opacity-50"
            :disabled="deleting"
            @click="removeSelected"
          >
            {{ deleting ? '正在删除…' : '删除这份文档' }}
          </button>
        </div>
      </section>
    </div>
  </div>
</template>
