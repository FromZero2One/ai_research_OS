<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useCoverageMatrix, useFinancialMetrics, useIngestPrices, useMarketPrices, useStockSearch } from '@/stores/api'
import FinancialBars from '@/components/FinancialBars.vue'
import StockChart from '@/components/StockChart.vue'
import StockSearch from '@/components/StockSearch.vue'

const tickerRef = ref('000002')
const period = ref<'daily' | 'weekly' | 'monthly'>('daily')
const tickerNames = ref<Record<string, string>>({})
const autoIngested = ref<Set<string>>(new Set())
const ingestPrices = useIngestPrices()
const { data: coverage } = useCoverageMatrix()
const { data: nameData } = useStockSearch(computed(() => tickerRef.value))

const { data: priceData, isPending } = useMarketPrices(tickerRef, 520)
const { data: finData } = useFinancialMetrics(tickerRef)

const prices = computed(() => priceData.value?.prices || [])
const financials = computed(() => finData.value?.metrics || [])

const dataLoaded = computed(() => !isPending.value && priceData.value !== undefined)

watch([dataLoaded, tickerRef], () => {
  if (!dataLoaded.value || !tickerRef.value || autoIngested.value.has(tickerRef.value)) return
  if (prices.value.length === 0) {
    autoIngested.value = new Set(autoIngested.value).add(tickerRef.value)
    ingestPrices.mutate(tickerRef.value)
  }
})

const activeName = computed(() => {
  const known = tickerNames.value[tickerRef.value]
  if (known) return known
  const hit = nameData.value?.results.find((r) => r.symbol.toUpperCase() === tickerRef.value.toUpperCase())
  return hit?.name || ''
})
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

const HEALTH_META: Record<string, { label: string; color: string }> = {
  ok: { label: 'OK', color: 'var(--success)' },
  warn: { label: '预警', color: 'var(--warning)' },
  stale: { label: '过期', color: 'var(--danger)' },
  missing: { label: '缺失', color: 'var(--danger)' },
}
function healthMeta(h?: string) { return HEALTH_META[h || 'missing'] || HEALTH_META.missing }

// 定性覆盖辅助：health -> 展示标签 / 颜色
const qualLabel = (h?: string) => ({ ok: '✔', partial: '⚠️', missing: '✘' } as Record<string, string>)[h || 'missing'] ?? '✘'
const qualColor = (h?: string) => ({ ok: '#34d399', partial: 'var(--warning)', missing: '#f87171' } as Record<string, string>)[h || 'missing'] ?? '#f87171'

</script>

<template>
  <div class="page">
    <div class="page-header"><h1 class="page-title">📊 行情中心</h1><p class="page-desc">股票行情 · 财务指标 · 宏观数据</p></div>

    <el-card v-if="coverage && coverage.rows.length" shadow="never">
      <template #header><div class="flex items-center justify-between"><span>🩺 数据覆盖矩阵</span><span class="text-xs text-secondary">{{ coverage.counts.companies }} 家关注 · 全覆盖 {{ coverage.counts.fully_covered }} · 缺口 {{ coverage.counts.with_gaps }} · 过期 {{ coverage.counts.stale }} · 定性 {{ coverage.counts.qualitative_ok }}</span></div></template>
      <div class="coverage-grid">
        <div class="coverage-row coverage-head">
          <span class="c-ticker">公司</span>
          <span v-for="dt in coverage.data_types" :key="dt" class="c-cell">{{ dt }}</span>
          <span class="c-cell">定性</span>
        </div>
        <div v-for="row in coverage.rows" :key="row.ticker" class="coverage-row" @click="tickerRef = row.ticker; tickerNames = { ...tickerNames, [row.ticker]: row.name }">
          <span class="c-ticker" :style="{ color: row.worst_health === 'ok' ? 'var(--text-primary)' : 'var(--warning)' }">{{ row.ticker }} {{ row.name }}</span>
          <span v-for="dt in coverage.data_types" :key="dt" class="c-cell">
            <span class="health-dot" :style="{ background: healthMeta(row.cells[dt]?.health).color }" />
            <span class="text-xs text-secondary">{{ row.cells[dt]?.health === 'missing' ? '—' : `${Math.round(row.cells[dt].age_hours || 0)}h` }}</span>
          </span>
          <span class="c-cell" :style="{ color: qualColor(row.qualitative?.health) }">{{ qualLabel(row.qualitative?.health) }}</span>
        </div>
      </div>
    </el-card>

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
          <FinancialBars :data="revenueData" color="#4f8cff" />
        </el-card>
      </el-col>
      <el-col v-if="incomeData.length" :span="8">
        <el-card shadow="never"><template #header>净利润趋势</template>
          <FinancialBars :data="incomeData" color="#34d399" />
        </el-card>
      </el-col>
      <el-col v-if="marginData.length" :span="8">
        <el-card shadow="never"><template #header>运营利润率</template>
          <FinancialBars :data="marginData" color="#fbbf24" format="pct" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.page { max-width: 1100px; margin: 0 auto; display: flex; flex-direction: column; gap: 24px; }
.chart-card { padding: 16px; border-radius: 12px; }
.chart-empty { display: flex; align-items: center; justify-content: center; height: 256px; color: var(--text-secondary); }
.coverage-grid { display: flex; flex-direction: column; gap: 6px; }
.coverage-row { display: grid; grid-template-columns: 1fr repeat(5, 90px); align-items: center; gap: 8px; padding: 6px 10px; border-radius: 8px; cursor: pointer; }
.coverage-row:hover { background: var(--bg-tertiary); }
.coverage-head { cursor: default; color: var(--text-secondary); font-size: 12px; }
.coverage-head:hover { background: transparent; }
.c-ticker { font-size: 13px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.c-cell { display: flex; align-items: center; gap: 6px; }
.health-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.text-success { color: var(--success); }
.text-danger { color: var(--danger); }
</style>
