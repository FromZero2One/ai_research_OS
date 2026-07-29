<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { useMarketPrices, useFinancialMetrics } from '@/stores/api'
import StockChart from '@/components/StockChart.vue'
import StockSearch from '@/components/StockSearch.vue'

const queryClient = useQueryClient()
const tickerRef = ref('000002')
const period = ref<'daily' | 'weekly' | 'monthly'>('daily')
const tickerNames = ref<Record<string, string>>({})
const autoIngested = ref<Set<string>>(new Set())

const { data: priceData, isPending } = useMarketPrices(tickerRef.value, 520)
const { data: finData } = useFinancialMetrics(tickerRef.value)

const prices = computed(() => priceData.value?.prices || [])
const financials = computed(() => finData.value?.metrics || [])

watch(tickerRef, async (t) => {
  if (!t || tickerNames.value[t]) return
  try { const r = await fetch(`/api/market/search?query=${encodeURIComponent(t)}&limit=5`); const d = await r.json(); const m = d.results?.find((r: any) => r.symbol.toUpperCase() === t.toUpperCase()); if (m?.name) tickerNames.value = { ...tickerNames.value, [t]: m.name } } catch {}
})

const dataLoaded = computed(() => !isPending.value && priceData.value !== undefined)

watch([dataLoaded, tickerRef], () => {
  if (!dataLoaded.value || !tickerRef.value || autoIngested.value.has(tickerRef.value)) return
  if (prices.value.length === 0) {
    autoIngested.value = new Set(autoIngested.value).add(tickerRef.value)
    fetch(`/api/market/prices/${tickerRef.value}/ingest`, { method: 'POST' }).then(() => queryClient.invalidateQueries({ queryKey: ['market', tickerRef.value] })).catch(() => {})
  }
})

const activeName = computed(() => tickerNames.value[tickerRef.value])
const latestPrice = computed(() => prices.value.length > 0 ? prices.value[0].close : null)
const prevClose = computed(() => prices.value.length > 1 ? prices.value[1].close : null)
const change = computed(() => latestPrice.value != null && prevClose.value != null ? latestPrice.value - prevClose.value : null)
const changePct = computed(() => change.value != null && prevClose.value != null ? (change.value / prevClose.value) * 100 : null)
const revenueData = computed(() => financials.value.filter((m) => m.metric_name === 'revenue').reverse())
const incomeData = computed(() => financials.value.filter((m) => m.metric_name === 'net_income').reverse())
const marginData = computed(() => financials.value.filter((m) => m.metric_name === 'operating_margin').reverse())

const summaryCards = computed(() => [
  { label: '最新收盘', value: latestPrice.value, fmt: (v: number) => v.toFixed(2) },
  { label: '最高', value: prices.value.length ? Math.max(...prices.value.map(p => p.high)) : null, fmt: (v: number) => v.toFixed(2) },
  { label: '最低', value: prices.value.length ? Math.min(...prices.value.map(p => p.low)) : null, fmt: (v: number) => v.toFixed(2) },
  { label: '均价', value: prices.value.length ? prices.value.reduce((s, p) => s + p.close, 0) / prices.value.length : null, fmt: (v: number) => v.toFixed(2) },
])

function getWeekKey(d: Date) { const start = new Date(d.getFullYear(), 0, 1); const diff = (d.getTime() - start.getTime() + 864e5) / 864e5; return `${d.getFullYear()}-W${String(Math.ceil(diff / 7)).padStart(2, '0')}` }

const chartPrices = computed(() => {
  if (period.value === 'daily' || prices.value.length === 0) return prices.value
  const groups = new Map<string, typeof prices.value>()
  for (const p of prices.value) {
    const d = new Date(p.date); const key = period.value === 'weekly' ? getWeekKey(d) : `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(p)
  }
  return Array.from(groups.entries()).sort(([a], [b]) => a.localeCompare(b)).map(([_, bars]) => {
    const first = bars[bars.length - 1]; const last = bars[0]
    return { date: last.date, open: first.open, high: Math.max(...bars.map((b) => b.high)), low: Math.min(...bars.map((b) => b.low)), close: last.close, volume: bars.reduce((s, b) => s + b.volume, 0) }
  })
})

function onStockSelect(item: { symbol: string; name: string }) {
  tickerRef.value = item.symbol
  if (item.name) tickerNames.value = { ...tickerNames.value, [item.symbol]: item.name }
}

function formatVal(v: number, fmt: 'num' | 'pct' = 'num') { if (fmt === 'pct') return `${(v * 100).toFixed(1)}%`; if (v > 1e9) return `$${(v / 1e9).toFixed(1)}B`; if (v > 1e6) return `$${(v / 1e6).toFixed(1)}M`; return `$${v.toFixed(0)}` }
</script>

<template>
  <div class="page">
    <div class="page-header"><h1 class="page-title">📊 行情中心</h1><p class="page-desc">股票行情 · 财务指标 · 宏观数据</p></div>

    <StockSearch @select="onStockSelect" />

    <div class="flex items-center gap-3">
      <span class="text-xs text-secondary font-medium">K线周期</span>
      <el-radio-group v-model="period" size="small">
        <el-radio-button value="daily">日K</el-radio-button>
        <el-radio-button value="weekly">周K</el-radio-button>
        <el-radio-button value="monthly">月K</el-radio-button>
      </el-radio-group>
    </div>

    <div v-if="prices.length > 0" class="space-y-3">
      <div class="flex items-baseline gap-3">
        <h2 class="text-xl font-bold" style="color:var(--text-primary)">{{ activeName || tickerRef }}<span v-if="activeName" class="text-secondary text-base font-normal ml-2">{{ tickerRef }}</span></h2>
        <span v-if="change != null" :class="change >= 0 ? 'text-success' : 'text-danger'" class="text-lg font-semibold">{{ change >= 0 ? '+' : '' }}{{ change.toFixed(2) }} ({{ changePct?.toFixed(2) }}%)</span>
      </div>
      <el-row :gutter="12">
        <el-col v-for="s in summaryCards" :key="s.label" :span="6">
          <el-card shadow="never"><div class="text-xs text-secondary">{{ s.label }}</div><div class="text-lg font-bold mt-0.5" style="color:var(--text-primary)">{{ s.value != null ? s.fmt(s.value) : '—' }}</div></el-card>
        </el-col>
      </el-row>
    </div>

    <el-card shadow="never" class="chart-card">
      <div class="flex items-center justify-between mb-3"><span class="text-sm text-secondary">{{ tickerRef }} · K 线图</span><span class="text-xs text-secondary">{{ isPending ? '加载中...' : chartPrices.length > 0 ? `${chartPrices.length}条 ✅` : '暂无数据' }}</span></div>
      <StockChart v-if="chartPrices.length > 0" :key="`${tickerRef}-${period}`" :prices="chartPrices" :height="420" :show-volume="true" />
      <div v-else class="chart-empty"><div v-if="isPending">加载中...</div><div v-else>暂无数据 — 请尝试点公司页的「↻ 刷新」拉取行情</div></div>
    </el-card>

    <el-row :gutter="16">
      <el-col v-if="revenueData.length" :span="8">
        <el-card shadow="never"><template #header>营收趋势</template>
          <div v-for="d in revenueData.slice(-8)" :key="d.fiscal_period" class="bar-row"><span class="bar-label">{{ d.fiscal_period }}</span><div class="bar-track"><div class="bar-fill" :style="{ width: `${(d.metric_value / Math.max(...revenueData.slice(-8).map(x => x.metric_value))) * 100}%`, backgroundColor: '#4f8cff' }" /></div><span class="bar-value">{{ formatVal(d.metric_value) }}</span></div>
        </el-card>
      </el-col>
      <el-col v-if="incomeData.length" :span="8">
        <el-card shadow="never"><template #header>净利润趋势</template>
          <div v-for="d in incomeData.slice(-8)" :key="d.fiscal_period" class="bar-row"><span class="bar-label">{{ d.fiscal_period }}</span><div class="bar-track"><div class="bar-fill" :style="{ width: `${(d.metric_value / Math.max(...incomeData.slice(-8).map(x => x.metric_value))) * 100}%`, backgroundColor: '#34d399' }" /></div><span class="bar-value">{{ formatVal(d.metric_value) }}</span></div>
        </el-card>
      </el-col>
      <el-col v-if="marginData.length" :span="8">
        <el-card shadow="never"><template #header>运营利润率</template>
          <div v-for="d in marginData.slice(-8)" :key="d.fiscal_period" class="bar-row"><span class="bar-label">{{ d.fiscal_period }}</span><div class="bar-track"><div class="bar-fill" :style="{ width: `${(d.metric_value / Math.max(...marginData.slice(-8).map(x => x.metric_value))) * 100}%`, backgroundColor: '#fbbf24' }" /></div><span class="bar-value">{{ formatVal(d.metric_value, 'pct') }}</span></div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.page { max-width: 1100px; margin: 0 auto; display: flex; flex-direction: column; gap: 24px; }
.chart-card { padding: 16px; border-radius: 12px; }
.chart-empty { display: flex; align-items: center; justify-content: center; height: 256px; color: var(--text-secondary); }
.text-success { color: var(--success); }
.text-danger { color: var(--danger); }
.bar-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; font-size: 12px; }
.bar-label { color: var(--text-secondary); width: 60px; flex-shrink: 0; }
.bar-track { flex: 1; height: 16px; border-radius: 4px; background: var(--bg-tertiary); overflow: hidden; }
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.bar-value { color: var(--text-primary); width: 80px; text-align: right; font-family: monospace; font-size: 11px; }
</style>
