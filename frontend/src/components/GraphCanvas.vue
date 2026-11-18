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
  forceDark?: boolean
}>()

const emit = defineEmits<{ (e: 'select', id: string): void }>()

const el = ref<HTMLDivElement | null>(null)
let chart: ECharts | null = null
let observer: ResizeObserver | null = null

const { isDark } = useTheme()

const masteryPalette: Record<Mastery, string> = {
  mastered: '#7FC49A',
  weak: '#DEA25C',
  new: '#9AA6BE',
}

const LAYOUT: Record<string, [number, number]> = {
  ipv4: [0, 0],
  osi: [-35, -95],
  ethernet: [55, -170],
  csma: [175, -150],
  mac: [265, -75],
  arp: [180, -55],
  mask: [165, 90],
  cidr: [285, 140],
  route: [75, 165],
  nat: [-140, 175],
  icmp: [-120, 110],
  tcp: [-185, 40],
  udp: [-170, -55],
  handshake: [-265, 120],
  congestion: [-300, 30],
  dns: [-280, -95],
  http: [-190, -150],
  tls: [-80, -175],
}

const theme = computed(() =>
  isDark.value || props.forceDark
    ? {
        tooltipBg: 'rgba(19,21,25,0.96)',
        tooltipBorder: '#2a2d35',
        tooltipText: '#f2f3f5',
        label: '#c6cad2',
        nodeBorder: '#131519',
        nodeShadow: 'rgba(0,0,0,0.45)',
        edgeSolid: '#454b58',
        edgeDashed: '#30343d',
        emphasisLabel: '#ffffff',
      }
    : {
        tooltipBg: 'rgba(255,255,255,0.96)',
        tooltipBorder: '#e7e8ee',
        tooltipText: '#111318',
        label: '#3f4450',
        nodeBorder: '#ffffff',
        nodeShadow: 'rgba(16,24,40,0.10)',
        edgeSolid: '#aeb3c0',
        edgeDashed: '#c9ccd6',
        emphasisLabel: '#111318',
      },
)

function buildOption() {
  const t = theme.value
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
        draggable: false,
        cursor: 'pointer',
        categories: props.categories,
        data: props.nodes.map((n, i) => {
          const fallbackAngle = (i / props.nodes.length) * Math.PI * 2 - Math.PI / 2
          const [x, y] = LAYOUT[n.id] ?? [Math.cos(fallbackAngle) * 260, Math.sin(fallbackAngle) * 170]
          return {
            id: n.id,
            name: n.name,
            value: n.value,
            category: n.category,
            x,
            y,
            symbolSize: 11 + Math.sqrt(n.value) * 3.2,
            itemStyle: {
              color: masteryPalette[masteryMap[n.id] ?? 'new'],
              borderColor: t.nodeBorder,
              borderWidth: 1.5,
              shadowBlur: 6,
              shadowColor: t.nodeShadow,
            },
            label: {
              show: true,
              position: 'right',
              distance: 5,
              fontSize: 11,
              color: t.label,
            },
          }
        }),
        links: props.links.map((l) => ({
          source: l.source,
          target: l.target,
          lineStyle: {
            color: l.kind === 'prerequisite' ? t.edgeSolid : t.edgeDashed,
            width: l.kind === 'prerequisite' ? 1.5 : 1.1,
            type: l.kind === 'contains' ? 'dashed' : l.kind === 'related' ? 'dotted' : 'solid',
            curveness: 0.06,
            opacity: 0.9,
          },
        })),
        lineStyle: { curveness: 0.06 },
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
  chart = init(el.value)
  chart.setOption(buildOption())
  chart.on('click', (params) => {
    const p = params as unknown as { dataType?: string; data?: { id?: string } }
    if (p.dataType === 'node' && p.data?.id) emit('select', p.data.id)
  })
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(el.value)
  highlightSelected()
})

function highlightSelected() {
  if (!chart) return
  chart.dispatchAction({ type: 'downplay', seriesIndex: 0 })
  if (!props.selectedId) return
  const index = props.nodes.findIndex((n) => n.id === props.selectedId)
  if (index >= 0) chart.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: index })
}

watch(
  () => props.selectedId,
  () => highlightSelected(),
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
