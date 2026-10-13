<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, shallowRef, computed, nextTick, type ShallowRef } from 'vue'
import * as echarts from 'echarts'

// 报告可视化：基于证据 structured_facts 的已核实数字渲染图表，
// 不解析报告 markdown（数字一律来自抽取结果，与报告的 [已核实事实] 同源）。
interface Fact { metric_name?: string; value?: number | string; unit?: string; period?: string }
interface Evidence {
  evidence_type: string
  classification_source?: string | null
  structured_facts?: { facts?: Fact[]; not_mentioned?: boolean } | null
}

const props = defineProps<{ evidences: Evidence[] }>()

const chartRef = ref<HTMLDivElement | null>(null)
const trendRef = ref<HTMLDivElement | null>(null)
const distChart = shallowRef<echarts.ECharts | null>(null)
const trendChart = shallowRef<echarts.ECharts | null>(null)
let resizeObserver: ResizeObserver | null = null

const AXIS_COLOR = '#9aa0a6'
const SPLIT_COLOR = '#2d3140'
const TOOLTIP_BG = '#1a1d28'

// ── 报告期解析（与后端 research/period_compare.parse_period 对应）──
interface ParsedPeriod { label: string; order: number }
function parsePeriod(p?: string): ParsedPeriod | null {
  if (!p) return null
  let m = /(\d{4})[Qq]\s*([1-4])/.exec(p)
  if (m) return { label: `${m[1]}Q${m[2]}`, order: Number(m[1]) * 10 + Number(m[2]) }
  m = /(\d{4})\s*年?(?:第\s*([一二三四1-4])\s*季?度?|([一二三四])季?度?)/.exec(p)
  if (m) {
    const q = Number({ 一: 1, 二: 2, 三: 3, 四: 4 }[m[2] || m[3]] || m[2] || m[3])
    if (q >= 1 && q <= 4) return { label: `${m[1]}Q${q}`, order: Number(m[1]) * 10 + q }
  }
  if (/(\d{4})(年)?(中报|半年报)/.exec(p)) {
    m = /(\d{4})/.exec(p)!
    return { label: `${m[1]}半年报`, order: Number(m[1]) * 10 + 2.5 }
  }
  m = /(\d{4})(年)?(报|度|全年)?$/.exec(p.trim())
  if (m) return { label: `${m[1]}年报`, order: Number(m[1]) * 10 + 5 }
  return null
}

// ── 证据方向分布 ──
const distData = computed(() => {
  const counts: Record<string, number> = { supporting: 0, opposing: 0, neutral: 0 }
  let llmCount = 0
  for (const ev of props.evidences) {
    if (ev.evidence_type in counts) counts[ev.evidence_type]++
    if (ev.classification_source === 'llm') llmCount++
  }
  const total = props.evidences.length
  return { counts, llmCount, total }
})

// ── 财务指标多周期序列 ──
interface MetricSeries { name: string; unit: string; periods: string[]; values: (number | null)[] }
const metricSeries = computed<MetricSeries[]>(() => {
  // (metric, unit) -> {label(order) -> value}
  const groups = new Map<string, Map<string, { order: number; label: string; value: number }>>()
  for (const ev of props.evidences) {
    const facts = ev.structured_facts?.facts
    if (!facts || ev.structured_facts?.not_mentioned) continue
    for (const f of facts) {
      if (f.metric_name == null || f.value == null) continue
      const v = Number(f.value)
      if (!Number.isFinite(v)) continue
      const pt = parsePeriod(f.period)
      if (!pt) continue
      const key = `${f.metric_name}|${f.unit || ''}`
      if (!groups.has(key)) groups.set(key, new Map())
      const inner = groups.get(key)!
      // 同期同指标取先出现的（不同证据重复抽取时保持首个已核实值）
      if (!inner.has(pt.label)) inner.set(pt.label, { order: pt.order, label: pt.label, value: v })
    }
  }

  const series: MetricSeries[] = []
  for (const [key, points] of groups) {
    if (points.size < 2) continue // 单点无法成趋势
    const [metricName, unit] = key.split('|')
    const sorted = [...points.values()].sort((a, b) => a.order - b.order)
    series.push({ name: metricName, unit, periods: sorted.map((p) => p.label), values: sorted.map((p) => p.value) })
  }
  // 最多 4 组，优先数据点多的
  return series.sort((a, b) => b.values.length - a.values.length).slice(0, 4)
})

const allPeriodLabels = computed(() => {
  const labels = new Set<string>()
  for (const s of metricSeries.value) for (const p of s.periods) labels.add(p)
  return [...labels]
})

const SERIES_COLORS = ['#4f8cff', '#34d399', '#fbbf24', '#f87171']

function ensureChart(el: HTMLDivElement | null, inst: ShallowRef<echarts.ECharts | null>): echarts.ECharts | null {
  if (inst.value) return inst.value
  if (!el || el.clientWidth === 0 || el.clientHeight === 0) return null
  inst.value = echarts.init(el, undefined, { renderer: 'canvas' })
  return inst.value
}

function updateDist() {
  const chart = distChart.value
  if (!chart) return
  const { counts } = distData.value
  chart.setOption(
    {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'item', backgroundColor: TOOLTIP_BG, borderColor: SPLIT_COLOR, textStyle: { color: '#e8eaed', fontSize: 12 } },
      legend: { bottom: 0, textStyle: { color: AXIS_COLOR, fontSize: 11 } },
      series: [
        {
          type: 'pie',
          radius: ['45%', '70%'],
          center: ['50%', '45%'],
          label: { color: AXIS_COLOR, formatter: '{b}\n{c} 条' },
          data: [
            { name: '支持', value: counts.supporting, itemStyle: { color: '#34d399' } },
            { name: '反对', value: counts.opposing, itemStyle: { color: '#f87171' } },
            { name: '中性', value: counts.neutral, itemStyle: { color: '#6b7280' } },
          ],
        },
      ],
    },
    true,
  )
}

function updateTrend() {
  const chart = trendChart.value
  if (!chart) return
  const labels = allPeriodLabels.value
  const series = metricSeries.value
  const yAxis: echarts.YAXisComponentOption[] = []
  const axesUsed = Math.min(3, series.length)
  for (let i = 0; i < axesUsed; i++) {
    yAxis.push({
      type: 'value',
      scale: true,
      ...(i === 0 ? { position: 'left' as const } : i === 1 ? { position: 'right' as const } : {}),
      splitLine: { show: i === 0, lineStyle: { color: SPLIT_COLOR, type: 'dashed' } },
      axisLabel: { show: i < 2, color: AXIS_COLOR, fontSize: 10 },
    })
  }
  chart.setOption(
    {
      backgroundColor: 'transparent',
      grid: { left: '10%', right: axesUsed > 1 ? '10%' : '4%', top: '12%', bottom: '18%' },
      legend: { top: 0, right: 0, textStyle: { color: AXIS_COLOR, fontSize: 11 } },
      tooltip: {
        trigger: 'axis',
        backgroundColor: TOOLTIP_BG,
        borderColor: SPLIT_COLOR,
        textStyle: { color: '#e8eaed', fontSize: 12 },
        valueFormatter: (v: unknown) => (v == null ? '—' : String(v)),
      },
      xAxis: { type: 'category', data: labels, axisLine: { lineStyle: { color: SPLIT_COLOR } }, axisLabel: { color: AXIS_COLOR, fontSize: 10 } },
      yAxis,
      series: series.map((s, i) => ({
        name: s.unit ? `${s.name}（${s.unit}）` : s.name,
        type: 'line' as const,
        smooth: true,
        yAxisIndex: Math.min(i, axesUsed - 1),
        data: labels.map((l) => {
          const idx = s.periods.indexOf(l)
          return idx >= 0 ? s.values[idx] : null
        }),
        connectNulls: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2, color: SERIES_COLORS[i % SERIES_COLORS.length] },
        itemStyle: { color: SERIES_COLORS[i % SERIES_COLORS.length] },
      })),
    },
    true,
  )
}

onMounted(() => {
  resizeObserver = new ResizeObserver(() => {
    for (const inst of [distChart, trendChart]) {
      if (inst.value) inst.value.resize()
    }
    if (!distChart.value || !trendChart.value) refresh()
  })
  if (chartRef.value) resizeObserver.observe(chartRef.value)
  refresh()
})

async function refresh() {
  await nextTick()
  if (ensureChart(chartRef.value, distChart)) updateDist()
  if (ensureChart(trendRef.value, trendChart)) updateTrend()
}

watch(() => props.evidences, refresh, { deep: true })

onUnmounted(() => {
  resizeObserver?.disconnect()
  distChart.value?.dispose()
  trendChart.value?.dispose()
})
</script>

<template>
  <div class="charts-grid">
    <div class="chart-block">
      <div class="chart-title">证据方向分布<span class="chart-sub">{{ distData.total }} 条 · {{ distData.llmCount }} 条 AI 分类</span></div>
      <div ref="chartRef" class="chart-canvas" style="height: 260px" />
    </div>
    <div v-if="metricSeries.length" class="chart-block">
      <div class="chart-title">财务指标趋势<span class="chart-sub">来自已核实事实（structured_facts）</span></div>
      <div ref="trendRef" class="chart-canvas" style="height: 260px" />
    </div>
  </div>
</template>

<style scoped>
.charts-grid { display: grid; grid-template-columns: 1fr; gap: 16px; }
.chart-block { padding: 16px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); }
.chart-title { font-size: 14px; font-weight: 500; color: var(--text-primary); margin-bottom: 8px; }
.chart-sub { font-size: 12px; font-weight: 400; color: var(--text-secondary); margin-left: 8px; }
.chart-canvas { width: 100%; }
</style>
