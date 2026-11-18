<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  BookMarked,
  ChevronRight,
  FileCode2,
  FileText,
  FileType2,
  Layers,
  Presentation,
  RefreshCw,
  Upload,
} from 'lucide-vue-next'
import { documents } from '@/mock/data'

const typeIcon = {
  pdf: FileText,
  md: FileCode2,
  docx: FileType2,
  pptx: Presentation,
}

const statusText = {
  ready: '已就绪',
  parsing: '解析中',
  failed: '失败',
}

const statusTone = {
  ready: 'bg-success',
  parsing: 'bg-brand animate-soft-pulse',
  failed: 'bg-danger',
}

const coverage: Record<string, string> = {
  doc_01: '第 1–4 章',
  doc_02: '第 3 章',
  doc_03: '第 2–3 章',
  doc_04: '第 4 章',
}

const quality: Record<string, { label: string; tone: string }> = {
  doc_01: { label: '好', tone: 'text-success' },
  doc_02: { label: '好', tone: 'text-success' },
  doc_03: { label: '待优化', tone: 'text-warn' },
  doc_04: { label: '解析中', tone: 'text-muted' },
}

const selectedId = ref(documents[0].id)
const selected = computed(() => documents.find((d) => d.id === selectedId.value) ?? documents[0])

const chunks = [
  {
    id: 'chunk_4412',
    text: '子网划分把原来的主机位再分为子网号与主机号两部分，网络前缀不变，路由器据此转发。',
    topic: 'IPv4',
    score: 0.94,
  },
  {
    id: 'chunk_4418',
    text: '块大小 = 2^(32−前缀)。网络地址一定落在块大小的整数倍上，广播地址是下一块减一。',
    topic: 'CIDR',
    score: 0.88,
  },
  {
    id: 'chunk_4425',
    text: 'RFC 950 早期规定不能使用全 0 与全 1 的子网号，现代设备默认支持全 0 子网。',
    topic: '子网掩码',
    score: 0.72,
  },
]

const totalChunks = computed(() => documents.reduce((sum, d) => sum + d.chunks, 0))
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
      <button class="pill-btn h-9 bg-ink pl-3.5 text-canvas hover:opacity-90">
        <Upload :size="15" />
        上传文档
      </button>
    </div>

    <section class="surface mt-5 grid grid-cols-2 divide-line md:grid-cols-4 md:divide-x">
      <div class="px-5 py-3.5">
        <div class="text-[10px] text-muted">文档</div>
        <div class="mt-1 text-[19px] font-semibold leading-none">{{ documents.length }}</div>
      </div>
      <div class="px-5 py-3.5">
        <div class="text-[10px] text-muted">分块</div>
        <div class="mt-1 text-[19px] font-semibold leading-none">{{ totalChunks }}</div>
      </div>
      <div class="px-5 py-3.5">
        <div class="text-[10px] text-muted">覆盖章节</div>
        <div class="mt-1 text-[19px] font-semibold leading-none">6</div>
      </div>
      <div class="flex items-center justify-between px-5 py-3.5">
        <div>
          <div class="text-[10px] text-muted">索引版本</div>
          <div class="mt-1 flex items-center gap-1.5">
            <span class="h-1.5 w-1.5 rounded-full bg-success" />
            <span class="text-[12px] font-medium">v3 已发布</span>
          </div>
        </div>
        <button class="icon-btn" aria-label="重建索引">
          <RefreshCw :size="14" />
        </button>
      </div>
    </section>

    <div class="mt-4 grid gap-4 xl:grid-cols-[1fr_320px]">
      <div class="flex flex-col gap-4">
        <div
          class="flex h-[118px] flex-col items-center justify-center gap-1.5 rounded-[18px] border border-dashed border-line-strong bg-surface/55 text-center transition-all duration-200 hover:border-brand/35 hover:bg-brand-soft/25"
        >
          <Upload :size="18" class="text-muted" />
          <p class="text-[12px] text-subink">拖拽文件到这里，或点击选择</p>
          <p class="text-[10px] text-muted">md / txt / docx / pdf / pptx · 单个不超过 20 MB</p>
        </div>

        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-5 py-3.5">
            <div class="flex items-center gap-2">
              <h2 class="text-[12.5px] font-medium">全部文档</h2>
              <span class="rounded-md bg-tint px-1.5 py-0.5 text-[10px] text-muted">
                {{ documents.length }}
              </span>
            </div>
            <button class="text-[10.5px] text-muted hover:text-ink">按更新时间排序</button>
          </header>

          <div
            class="hidden grid-cols-[1fr_76px_44px_48px_62px_78px_16px] gap-3 border-b border-line px-5 py-2 text-[9.5px] text-muted md:grid"
          >
            <span>文档</span>
            <span>章节</span>
            <span>分块</span>
            <span>质量</span>
            <span>状态</span>
            <span>更新</span>
            <span />
          </div>

          <ul>
            <li
              v-for="doc in documents"
              :key="doc.id"
              class="grid cursor-pointer grid-cols-1 items-center gap-2 border-b border-line px-5 py-3 transition-colors last:border-b-0 md:grid-cols-[1fr_76px_44px_48px_62px_78px_16px] md:gap-3"
              :class="selectedId === doc.id ? 'bg-brand-soft/35' : 'hover:bg-tint-soft'"
              @click="selectedId = doc.id"
            >
              <div class="flex min-w-0 items-center gap-2.5">
                <span class="grid h-8 w-8 shrink-0 place-items-center rounded-[10px] bg-tint text-muted">
                  <component :is="typeIcon[doc.type]" :size="14" />
                </span>
                <div class="min-w-0">
                  <p class="truncate text-[12px] text-subink">{{ doc.title }}</p>
                  <p class="mt-0.5 text-[9.5px] text-muted md:hidden">
                    {{ doc.type.toUpperCase() }} · {{ coverage[doc.id] }} · {{ doc.chunks }} 分块
                  </p>
                </div>
              </div>
              <span class="hidden text-[10px] text-muted md:block">{{ coverage[doc.id] }}</span>
              <span class="hidden font-mono text-[10px] text-muted md:block">{{ doc.chunks }}</span>
              <span class="hidden text-[9.5px] md:block" :class="quality[doc.id].tone">
                {{ quality[doc.id].label }}
              </span>
              <span class="hidden items-center gap-1.5 text-[10px] text-muted md:flex">
                <span class="h-1.5 w-1.5 rounded-full" :class="statusTone[doc.status]" />
                {{ statusText[doc.status] }}
              </span>
              <span class="hidden font-mono text-[9.5px] text-muted md:block">
                {{ doc.updated.split(' ')[0] }}
              </span>
              <ChevronRight
                :size="13"
                class="hidden shrink-0 md:block"
                :class="selectedId === doc.id ? 'text-brand' : 'text-muted'"
              />
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
          <button class="text-[9.5px] text-muted hover:text-subink">重建</button>
        </header>

        <div class="border-b border-line px-4 py-3">
          <p class="truncate text-[11.5px] font-medium text-ink">{{ selected.title }}</p>
          <p class="mt-0.5 text-[9.5px] text-muted">
            {{ selected.chunks }} 个分块 · {{ selected.size }} · {{ coverage[selected.id] }}
          </p>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto p-3">
          <div class="mb-2 flex items-center gap-1.5 px-1 text-[9.5px] text-muted">
            <BookMarked :size="11" />
            已映射到知识点
          </div>
          <div v-if="selected.status === 'parsing'" class="px-1 py-8 text-center text-[10.5px] text-muted">
            解析中，完成后可预览切片。
          </div>
          <div v-else class="flex flex-col gap-2">
            <article
              v-for="c in chunks"
              :key="c.id"
              class="rounded-xl border border-line bg-surface px-3 py-2.5 transition-colors hover:border-line-strong"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="rounded-full bg-brand-soft px-1.5 py-0.5 text-[9px] text-brand">
                  {{ c.topic }}
                </span>
                <span class="font-mono text-[9px] text-muted">{{ c.score.toFixed(2) }}</span>
              </div>
              <p class="mt-1.5 line-clamp-3 text-[10.5px] leading-[1.65] text-subink">{{ c.text }}</p>
              <p class="mt-1.5 font-mono text-[8.5px] text-muted">{{ c.id }}</p>
            </article>
          </div>
        </div>

        <div class="border-t border-line p-3">
          <button class="pill-btn h-8 w-full justify-center border border-line bg-tint-soft text-[10.5px] text-subink hover:border-line-strong">
            <RefreshCw :size="12" />
            重建该文档索引
          </button>
        </div>
      </section>
    </div>
  </div>
</template>
