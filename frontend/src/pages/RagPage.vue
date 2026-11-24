<script setup lang="ts">
import { ref } from 'vue'
import { ArrowUp, Database, FileText, Layers, SlidersHorizontal } from 'lucide-vue-next'
import { ragPassages } from '@/mock/data'

const query = ref('192.168.10.137/27 的网络地址和可用主机范围是多少？')

const pipeline = [
  { label: '查询改写', detail: '提取前缀 /27' },
  { label: '向量召回', detail: 'BGE-M3 · 20 条' },
  { label: 'BM25 召回', detail: '词项匹配 · 20 条' },
  { label: 'RRF 融合', detail: 'k=60' },
  { label: '重排', detail: '保留 5 条' },
]
</script>

<template>
  <div class="animate-fade-up page">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="text-[26px] font-semibold leading-tight tracking-[-0.025em]">RAG 问答</h1>
      </div>
    </div>

    <div
      class="mt-6 flex items-center gap-2 rounded-[18px] border border-line bg-surface px-4 py-3 shadow-[0_2px_10px_-6px_rgba(16,24,40,0.12)] focus-within:border-brand/45 focus-within:ring-2 focus-within:ring-brand/10"
    >
      <Database :size="16" class="shrink-0 text-muted" />
      <input
        v-model="query"
        type="text"
        class="h-7 min-w-0 flex-1 bg-transparent text-[13px] text-ink outline-none placeholder:text-muted"
      />
      <button class="grid h-8 w-8 place-items-center rounded-full bg-ink text-canvas transition-opacity hover:opacity-90">
        <ArrowUp :size="15" />
      </button>
    </div>

    <div class="mt-3 flex flex-wrap items-center gap-1.5">
      <template v-for="(step, i) in pipeline" :key="step.label">
        <div class="flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5">
          <span class="grid h-4 w-4 place-items-center rounded-full bg-tint text-[9px] text-muted">
            {{ i + 1 }}
          </span>
          <div class="leading-tight">
            <div class="text-[10.5px] text-subink">{{ step.label }}</div>
            <div class="text-[9.5px] text-muted">{{ step.detail }}</div>
          </div>
        </div>
        <span v-if="i < pipeline.length - 1" class="text-line-strong">→</span>
      </template>
    </div>

    <div class="mt-5 grid grid-cols-[minmax(0,1fr)] items-start gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
      <div class="flex flex-col gap-4">
        <section class="surface p-5">
          <div class="flex items-center gap-2 text-[11px] text-muted">
            <Layers :size="13" />
            生成结果 · 5 条证据
          </div>
          <div class="mt-3 text-[13.5px] leading-[1.85] text-subink">
            <p>
              按 <span class="font-mono text-[12.5px] text-ink">/27</span> 计算，主机位 5 位，块大小为 32：
            </p>
            <ul class="mt-2 list-disc space-y-1 pl-5">
              <li>网络地址：<span class="font-mono text-[12.5px] text-ink">192.168.10.128</span></li>
              <li>广播地址：<span class="font-mono text-[12.5px] text-ink">192.168.10.159</span></li>
              <li>可用主机：<span class="font-mono text-[12.5px] text-ink">.129 – .158</span>，共 30 个</li>
            </ul>
          </div>

          <div class="mt-4 grid gap-2 sm:grid-cols-3">
            <div class="rounded-xl border border-line bg-tint-soft px-3 py-2.5">
              <div class="text-[10px] text-muted">相似度最高</div>
              <div class="mt-1 font-mono text-[13px] text-ink">0.94</div>
            </div>
            <div class="rounded-xl border border-line bg-tint-soft px-3 py-2.5">
              <div class="text-[10px] text-muted">召回 / 保留</div>
              <div class="mt-1 font-mono text-[13px] text-ink">40 → 5</div>
            </div>
            <div class="rounded-xl border border-line bg-tint-soft px-3 py-2.5">
              <div class="text-[10px] text-muted">生成耗时</div>
              <div class="mt-1 font-mono text-[13px] text-ink">1.24 s</div>
            </div>
          </div>
        </section>

        <section class="surface overflow-hidden">
          <header class="flex items-center justify-between border-b border-line px-4 py-3 sm:px-5 sm:py-3.5">
            <h2 class="text-[12.5px] font-medium">引用片段</h2>
            <span class="text-[10.5px] text-muted">按重排分数排序</span>
          </header>
          <ul class="p-2">
            <li
              v-for="p in ragPassages"
              :key="p.id"
              class="flex gap-3 rounded-xl px-3 py-3 transition-colors hover:bg-tint-soft"
            >
              <span class="grid h-7 w-7 shrink-0 place-items-center rounded-[9px] bg-tint text-muted">
                <FileText :size="13" />
              </span>
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2">
                  <span class="truncate text-[11.5px] text-subink">{{ p.source }}</span>
                  <span class="shrink-0 text-[10px] text-muted">{{ p.locator }}</span>
                  <span class="ml-auto shrink-0 font-mono text-[10.5px] text-brand">
                    {{ p.score.toFixed(2) }}
                  </span>
                </div>
                <p class="mt-1 line-clamp-2 text-[11.5px] leading-relaxed text-muted">{{ p.text }}</p>
                <div class="mt-2 h-0.5 overflow-hidden rounded-full bg-tint">
                  <div class="h-full rounded-full bg-brand/70" :style="{ width: p.score * 100 + '%' }" />
                </div>
              </div>
            </li>
          </ul>
        </section>
      </div>

      <div class="flex flex-col gap-4">
        <section class="surface p-5">
          <div class="flex items-center gap-2">
            <SlidersHorizontal :size="14" class="text-muted" />
            <h2 class="text-[12.5px] font-medium">检索设置</h2>
          </div>
          <div class="mt-3 flex flex-col gap-2.5">
            <div class="flex items-center justify-between text-[11.5px]">
              <span class="text-muted">Top-K</span>
              <span class="font-mono text-subink">5</span>
            </div>
            <div class="flex items-center justify-between text-[11.5px]">
              <span class="text-muted">混合检索</span>
              <span class="rounded-full bg-success/12 px-2 py-0.5 text-[10px] text-success">开启</span>
            </div>
            <div class="flex items-center justify-between text-[11.5px]">
              <span class="text-muted">重排模型</span>
              <span class="text-subink">BGE-Reranker</span>
            </div>
            <div class="flex items-center justify-between text-[11.5px]">
              <span class="text-muted">索引版本</span>
              <span class="font-mono text-subink">v3</span>
            </div>
            <div class="flex items-center justify-between text-[11.5px]">
              <span class="text-muted">Embedding</span>
              <span class="text-subink">BGE-M3</span>
            </div>
          </div>
        </section>

        <section class="surface p-5">
          <h2 class="text-[12.5px] font-medium">本次检索</h2>
          <p class="mt-1 text-[11px] leading-relaxed text-muted">
            命中 4 份文档，其中 2 份为教材与标准，1 份为实验手册。
          </p>
          <div class="mt-3 flex flex-col gap-1.5">
            <div class="flex items-center justify-between rounded-lg bg-tint-soft px-2.5 py-1.5 text-[10.5px]">
              <span class="text-muted">向量召回</span>
              <span class="font-mono text-subink">20 条 / 386ms</span>
            </div>
            <div class="flex items-center justify-between rounded-lg bg-tint-soft px-2.5 py-1.5 text-[10.5px]">
              <span class="text-muted">BM25 召回</span>
              <span class="font-mono text-subink">20 条 / 42ms</span>
            </div>
            <div class="flex items-center justify-between rounded-lg bg-tint-soft px-2.5 py-1.5 text-[10.5px]">
              <span class="text-muted">RRF 融合</span>
              <span class="font-mono text-subink">k=60 / 3ms</span>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
