<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, shallowRef, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = withDefaults(defineProps<{
  prices: { date: string; open: number; high: number; low: number; close: number; volume: number }[]
  height?: number
  showVolume?: boolean
}>(), { height: 400, showVolume: true })

const chartRef = ref<HTMLDivElement | null>(null)
const chartInstance = shallowRef<echarts.ECharts | null>(null)
let resizeObserver: ResizeObserver | null = null

function ensureChart(): echarts.ECharts | null {
  if (chartInstance.value) return chartInstance.value
  const el = chartRef.value
  // Defer init until the container actually has size — echarts.init on a
  // 0-size element (e.g. inside a hidden el-tab-pane) warns and stays broken.
  if (!el || el.clientWidth === 0 || el.clientHeight === 0) return null
  chartInstance.value = echarts.init(el, undefined, { renderer: 'canvas' })
  return chartInstance.value
}

function calcMA(prices: typeof props.prices, days: number): (number | null)[] {
  return prices.map((_, i) => {
    if (i < days - 1) return null
    let sum = 0
    for (let j = 0; j < days; j++) sum += prices[i - j].close
    return Math.round((sum / days) * 100) / 100
  })
}

function updateChart() {
  const chart = chartInstance.value
  if (!chart || !props.prices.length) return

  const sorted = props.prices.length > 1 && props.prices[0].date > props.prices[1].date
    ? [...props.prices].reverse()
    : props.prices

  const firstYear = sorted[0].date.slice(0, 4)
  const lastYear = sorted[sorted.length - 1].date.slice(0, 4)
  const multiYear = firstYear !== lastYear
  const dates = sorted.map((p) => multiYear ? p.date.slice(0, 7) : p.date.slice(5))
  const ohlc = sorted.map((p) => [p.open, p.close, p.low, p.high])
  const volumes = sorted.map((p) => p.volume)
  const ma5 = calcMA(sorted, 5)
  const ma20 = calcMA(sorted, 20)

  const option: echarts.EChartsOption = {
    backgroundColor: 'transparent',
    grid: props.showVolume
      ? [{ left: '8%', right: '8%', top: '8%', height: '60%' }, { left: '8%', right: '8%', top: '78%', height: '15%' }]
      : [{ left: '8%', right: '8%', top: '8%', bottom: '8%' }],
    xAxis: [
      { type: 'category', data: dates, axisLine: { lineStyle: { color: '#2d3140' } }, axisLabel: { color: '#9aa0a6', fontSize: 10 }, splitLine: { show: false } },
      { type: 'category', gridIndex: 1, data: dates, axisLabel: { show: false }, splitLine: { show: false } },
    ],
    yAxis: [
      { scale: true, splitLine: { lineStyle: { color: '#2d3140', type: 'dashed' } }, axisLabel: { color: '#9aa0a6', fontSize: 10 } },
      { scale: true, gridIndex: 1, splitLine: { show: false }, axisLabel: { show: false } },
    ],
    series: [
      { name: 'K 线', type: 'candlestick', data: ohlc, itemStyle: { color: '#34d399', color0: '#f87171', borderColor: '#34d399', borderColor0: '#f87171' } },
      { name: 'MA5', type: 'line', data: ma5, smooth: true, symbol: 'none', lineStyle: { width: 1, color: '#fbbf24' } },
      { name: 'MA20', type: 'line', data: ma20, smooth: true, symbol: 'none', lineStyle: { width: 1, color: '#4f8cff' } },
      ...(props.showVolume
        ? [{ name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: volumes.map((v, i) => ({ value: v, itemStyle: { color: props.prices[i].close >= props.prices[i].open ? '#34d399' : '#f87171' } })) } as any]
        : []),
    ],
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' }, backgroundColor: '#1a1d28', borderColor: '#2d3140', textStyle: { color: '#e8eaed', fontSize: 12 } },
    legend: { data: ['K 线', 'MA5', 'MA20'], textStyle: { color: '#9aa0a6', fontSize: 11 }, top: 0, right: 0 },
    dataZoom: [{ type: 'inside', start: Math.max(0, 100 - 120), end: 100 }, { type: 'slider', start: Math.max(0, 100 - 120), end: 100, height: 20, bottom: 0 }],
  }

  chart.setOption(option, true)
}

onMounted(() => {
  // The observer fires whenever the container size changes (including when a
  // hidden tab pane becomes visible: 0 -> real size), so it both initializes
  // the chart lazily and keeps it in sync with the layout.
  if (chartRef.value) {
    resizeObserver = new ResizeObserver(() => {
      if (!chartInstance.value) {
        if (ensureChart()) updateChart()
      } else {
        chartInstance.value.resize()
      }
    })
    resizeObserver.observe(chartRef.value)
  }
  if (ensureChart()) updateChart()
  onUnmounted(() => {
    resizeObserver?.disconnect()
    chartInstance.value?.dispose()
  })
})

watch(() => props.prices, async () => {
  // Data can arrive after mount (first load, refetch after refresh). If the
  // chart wasn't initialized yet, do it now — the container always exists.
  if (props.prices.length && !chartInstance.value) {
    await nextTick()
    ensureChart()
  }
  updateChart()
}, { deep: true })
</script>

<template>
  <div class="chart-wrap" :style="{ height: `${height}px`, width: '100%' }">
    <!-- ECharts owns this element's inner DOM — Vue must never re-render or
         conditionally remove it, otherwise the vdom desyncs from the real DOM. -->
    <div ref="chartRef" class="chart-canvas" />
    <div v-if="!prices.length" class="empty-chart">暂无数据</div>
  </div>
</template>

<style scoped>
.chart-wrap { position: relative; }
.chart-canvas { position: absolute; inset: 0; }
.empty-chart { position: absolute; inset: 0; z-index: 1; display: flex; align-items: center; justify-content: center; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); color: var(--text-secondary); }
</style>
