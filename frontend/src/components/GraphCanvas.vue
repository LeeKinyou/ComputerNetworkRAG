<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { init, use, type ECharts } from 'echarts/core'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useTheme } from '@/composables/useTheme'
import type { GraphLink, GraphNode } from '@/mock/data'
import { masteryMap, type Mastery } from '@/mock/workbench'

use([GraphChart, TooltipComponent, CanvasRenderer])

const props = defineProps<{
  nodes: GraphNode[]
  links: GraphLink[]
  categories: { name: string }[]
  selectedId?: string | null
  mastery?: Record<string, Mastery>
  forceDark?: boolean
}>()

const emit = defineEmits<{ (e: 'select', id: string): void }>()

const el = ref<HTMLDivElement | null>(null)
let chart: ECharts | null = null
let observer: ResizeObserver | null = null
/** 画布实际宽度：手机上要缩小字号与初始缩放，否则节点标签会挤成一团。 */
const chartWidth = ref(0)

const { isDark } = useTheme()

const masteryPalette: Record<Mastery, string> = {
  mastered: '#7FC49A',
  weak: '#DEA25C',
  new: '#9AA6BE',
}

/** 章节描边色：只做簇的视觉分隔，不参与掌握度编码。 */
const CHAPTER_TONES = ['#5B7BD5', '#4C9AA8', '#7C6BC4', '#C08A4E', '#5F9E78', '#B06A72']

/** 章节列布局：每章一列、列内等距纵排，标签不会互相压住，50+ 节点也读得清。 */
function buildPositions(): Record<string, [number, number]> {
  const groups: Record<number, GraphNode[]> = {}
  for (const node of props.nodes) {
    const key = Number(node.category) || 0
    ;(groups[key] ??= []).push(node)
  }
  const keys = Object.keys(groups)
    .map(Number)
    .sort((a, b) => a - b)
  const colGap = 152
  const rowGap = 44
  const startX = -((keys.length - 1) * colGap) / 2
  const positions: Record<string, [number, number]> = {}
  keys.forEach((key, columnIndex) => {
    const list = groups[key]
    list.forEach((node, index) => {
      const y = (index - (list.length - 1) / 2) * rowGap
      positions[node.id] = [startX + columnIndex * colGap + (index % 2 ? 12 : -12), y]
    })
  })
  return positions
}

const theme = computed(() =>
  isDark.value || props.forceDark
    ? {
        tooltipBg: 'rgba(19,21,25,0.96)',
        tooltipBorder: '#2a2d35',
        tooltipText: '#f2f3f5',
        label: '#c6cad2',
        labelDim: 'rgba(198,202,210,0.5)',
        nodeBorder: '#131519',
        nodeShadow: 'rgba(0,0,0,0.45)',
        edges: { prerequisite: '#6E9BFF', contains: '#4A505C', related: '#3A404A' },
        emphasisLabel: '#ffffff',
      }
    : {
        tooltipBg: 'rgba(255,255,255,0.96)',
        tooltipBorder: '#e7e8ee',
        tooltipText: '#111318',
        label: '#3f4450',
        labelDim: 'rgba(63,68,80,0.5)',
        nodeBorder: '#ffffff',
        nodeShadow: 'rgba(16,24,40,0.10)',
        edges: { prerequisite: '#4C7DF0', contains: '#B4B9C6', related: '#CDD1DA' },
        emphasisLabel: '#111318',
      },
)

const masteryOf = (id: string): Mastery => (props.mastery ?? masteryMap)[id] ?? 'new'

const focus = computed(() => {
  if (!props.selectedId) return null
  const ids = new Set<string>([props.selectedId])
  for (const link of props.links) {
    if (link.source === props.selectedId) ids.add(link.target)
    if (link.target === props.selectedId) ids.add(link.source)
  }
  return ids
})

function buildOption() {
  const t = theme.value
  const compact = chartWidth.value > 0 && chartWidth.value < 560
  const positions = buildPositions()
  // 每章只给度数最高的三个概念挂常驻标签，其余靠悬停与右栏，避免 53 个名字糊成一团
  const topLabels = new Set<string>()
  const byChapter: Record<number, GraphNode[]> = {}
  for (const node of props.nodes) {
    const key = Number(node.category) || 0
    ;(byChapter[key] ??= []).push(node)
  }
  for (const list of Object.values(byChapter)) {
    for (const node of [...list].sort((a, b) => b.value - a.value).slice(0, 3)) {
      topLabels.add(node.id)
    }
  }
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      backgroundColor: t.tooltipBg,
      borderColor: t.tooltipBorder,
      borderWidth: 1,
      padding: [7, 10],
      textStyle: { color: t.tooltipText, fontSize: 11.5 },
      extraCssText: 'box-shadow: 0 4px 16px rgba(0,0,0,.18); border-radius: 8px;',
    },
    series: [
      {
        type: 'graph',
        layout: 'none',
        roam: true,
        zoom: compact ? 0.42 : 0.9,
        scaleLimit: { min: 0.3, max: 2.6 },
        draggable: false,
        cursor: 'pointer',
        categories: props.categories,
        data: props.nodes.map((n) => {
          const [x, y] = positions[n.id] ?? [0, 0]
          const active = !focus.value || focus.value.has(n.id)
          const isSelected = n.id === props.selectedId
          return {
            id: n.id,
            name: n.name,
            value: n.value,
            category: n.category,
            x,
            y,
            symbolSize: (12 + Math.sqrt(n.value) * 3.6 + (isSelected ? 3 : 0)) * (compact ? 0.9 : 1),
            itemStyle: {
              color: masteryPalette[masteryOf(n.id)],
              borderColor: isSelected
                ? t.edges.prerequisite
                : CHAPTER_TONES[Number(n.category) % CHAPTER_TONES.length] ?? t.nodeBorder,
              borderWidth: isSelected ? 2.5 : 1.4,
              shadowBlur: isSelected ? 14 : 5,
              shadowColor: isSelected ? 'rgba(76,125,240,0.32)' : t.nodeShadow,
              opacity: active ? 1 : 0.5,
            },
            label: {
              show: isSelected || topLabels.has(n.id) || Boolean(focus.value && active),
              position: Number(n.category) >= 3 ? 'left' : 'right',
              distance: compact ? 6 : 9,
              fontSize: compact ? 9.5 : 10.5,
              fontWeight: isSelected ? 600 : 400,
              color: active ? t.label : t.labelDim,
            },
          }
        }),
        links: props.links.map((l) => {
          const kind = l.kind === 'prerequisite' ? 'prerequisite' : l.kind === 'contains' ? 'contains' : 'related'
          const adjacent = Boolean(
            props.selectedId && (l.source === props.selectedId || l.target === props.selectedId),
          )
          const dimmed = Boolean(focus.value && !adjacent)
          return {
            source: l.source,
            target: l.target,
            symbol: kind === 'prerequisite' ? ['none', 'arrow'] : ['none', 'none'],
            symbolSize: kind === 'prerequisite' ? 5 : 0,
            lineStyle: {
              color: t.edges[kind],
              width: adjacent ? 2.2 : kind === 'prerequisite' ? 1.6 : 1.1,
              type: kind === 'contains' ? 'dashed' : kind === 'related' ? 'dotted' : 'solid',
              curveness: 0.06,
              opacity: dimmed ? 0.12 : adjacent ? 1 : kind === 'related' ? 0.48 : 0.82,
            },
          }
        }),
        lineStyle: { curveness: 0.06 },
        layoutAnimation: false,
        emphasis: {
          focus: 'none',
          scale: 1.12,
          itemStyle: { shadowBlur: 14, shadowColor: 'rgba(47,107,255,.28)' },
          lineStyle: { width: 2, color: '#2f6bff', opacity: 1 },
          label: { fontWeight: 600, color: t.emphasisLabel },
        },
        labelLayout: { hideOverlap: true },
        edgeLabel: { show: false },
      },
    ],
  }
}

onMounted(() => {
  if (!el.value) return
  chartWidth.value = el.value.clientWidth
  chart = init(el.value)
  chart.setOption(buildOption())
  chart.on('click', (params) => {
    const p = params as unknown as { dataType?: string; data?: { id?: string } }
    if (p.dataType === 'node' && p.data?.id) emit('select', p.data.id)
  })
  observer = new ResizeObserver(() => {
    if (!el.value) return
    const width = el.value.clientWidth
    const wasCompact = chartWidth.value > 0 && chartWidth.value < 560
    const nowCompact = width > 0 && width < 560
    // 只在跨断点时重绘，普通尺寸变化仅做 resize，避免拖拽缩放时抖动
    if (wasCompact !== nowCompact) {
      chartWidth.value = width
      chart?.setOption(buildOption(), true)
    }
    chart?.resize()
  })
  observer.observe(el.value)
  highlightSelected()
})

function highlightSelected() {
  if (!chart) return
  chart.setOption(buildOption())
}

watch(
  () => props.selectedId,
  () => highlightSelected(),
)

// 图谱是异步加载的：节点/关系/掌握度回填后必须重绘，否则画布一直停留在内置示意数据
watch(
  () => [props.nodes, props.links, props.mastery] as const,
  () => chart?.setOption(buildOption(), true),
)

watch(isDark, () => {
  chart?.setOption(buildOption(), true)
  highlightSelected()
})

watch(
  () => props.forceDark,
  () => {
    chart?.setOption(buildOption(), true)
    highlightSelected()
  },
)

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="el" class="h-full w-full" />
</template>
