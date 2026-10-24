<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import {
  useSaveCriteria,
  useCancelScreenerRun,
  useScreenerBacktest,
  useScreenerBacktests,
  useScreenerCriteria,
  useScreenerDataQuality,
  useScreenerMetrics,
  useScreenerPresets,
  useDeleteScreenerPortfolio,
  usePushScreenerToResearch,
  usePushScreenerToWatchlist,
  useScreenerPortfolio,
  useScreenerPortfolios,
  useScreenerRun,
  useScreenerRunDiff,
  useScreenerRunPerformance,
  useScreenerRunReport,
  useRunScreenerSchedule,
  useScreenerRuns,
  useScreenerSchedule,
  type ScreenerPortfolioResult,
  useTriggerScreenerBacktest,
  useTriggerScreenerRun,
  useTriggerScreenerRunPresets,
  type ScreenerJudgement,
  type ScreenerPreset,
  type ScreenerRunSummary,
  type ScreenerSavedPortfolio,
} from '@/stores/api'
import PresetManager from '@/components/PresetManager.vue'

// ── 标准文档编辑 ──
const { data: criteriaData } = useScreenerCriteria()
const criteriaText = ref('')
let criteriaLoaded = false
watch(criteriaData, (v) => {
  if (v && !criteriaLoaded) {
    criteriaText.value = v.criteria
    criteriaLoaded = true
  }
})
const saveCriteria = useSaveCriteria()
async function handleSaveCriteria() {
  try {
    await saveCriteria.mutateAsync({ criteria: criteriaText.value })
    ElMessage.success('标准已保存')
  } catch (e: any) { ElMessage.error(e.message || '保存失败') }
}

// ── 触发 + 运行状态轮询 ──
const activeRunId = ref<string | null>(null)
const triggerRun = useTriggerScreenerRun()
const { data: runsData, refetch: refetchRuns } = useScreenerRuns()

const activeStatus = computed(() => activeRun.value?.status)
// 进行中的运行每 3s 轮询详情
const { data: activeRun } = useScreenerRun(activeRunId, {
  poll: computed(() => !!activeRunId.value && running.value),
})
watch(activeStatus, (s) => {
  if (s === 'completed') ElMessage.success('筛选完成')
  if (s === 'cancelled') ElMessage.info('筛选已取消')
  if (s === 'failed') ElMessage.error(`筛选失败：${activeRun.value?.error || '未知原因'}`)
})

// 页面刷新/从别处触发后，自动接管仍在进行中的 run，否则不会轮询
watch(runsData, (v) => {
  if (activeRunId.value) return
  const active = (v?.runs || []).find((r) => ['pending', 'screening', 'judging', 'cancelling'].includes(r.status))
  if (active) activeRunId.value = active.id
}, { immediate: true })

const running = computed(() =>
  activeStatus.value === 'pending' || activeStatus.value === 'screening' || activeStatus.value === 'judging'
  || activeStatus.value === 'cancelling'
  || (runsData.value?.runs || []).some((r) => ['pending', 'screening', 'judging', 'cancelling'].includes(r.status)),
)

// ── 预设回测 ──
const backtestPresetId = ref<string | null>(null)
const backtestYears = ref(5)
const backtestRunId = ref<string | null>(null)
const backtestStatus = ref<string | null>(null)
const triggerBacktestMutation = useTriggerScreenerBacktest()
const { data: backtestList, refetch: refetchBacktests } = useScreenerBacktests()
const { data: backtestData } = useScreenerBacktest(backtestRunId, {
  poll: computed(() => ['pending', 'running'].includes(backtestStatus.value || '')),
})
watch(backtestData, (d) => {
  backtestStatus.value = d?.status || null
  if (d && (d.status === 'completed' || d.status === 'failed')) {
    refetchBacktests()
    if (d.status === 'completed') ElMessage.success('回测完成')
    if (d.status === 'failed') ElMessage.error(`回测失败：${d.error || '未知原因'}`)
  }
})
watch(backtestList, (v) => {
  if (backtestRunId.value || !v?.backtests?.length) return
  const latest = v.backtests[0]
  backtestRunId.value = latest.id
  backtestStatus.value = latest.status
  if (latest.preset_id) backtestPresetId.value = latest.preset_id
  backtestYears.value = latest.years
}, { immediate: true })
const backtestSummary = computed(() => backtestData.value?.result?.summary || null)
const backtestSplit = computed(() => backtestSummary.value?.split_sample || null)
const backtestYearly = computed(() => backtestData.value?.result?.yearly || [])
const backtestMetricRows = computed(() => {
  const s = backtestSummary.value
  if (!s) return []
  const pct = (v: number | null | undefined, signed = false) =>
    v === null || v === undefined ? '-' : `${signed && v > 0 ? '+' : ''}${(v * 100).toFixed(2)}%`
  return [
    { label: '累计收益', value: pct(s.total_return) },
    { label: '年化', value: pct(s.cagr) },
    { label: '基准年化', value: pct(s.bench_cagr) },
    { label: '年化超额', value: pct(s.excess_cagr, true) },
    { label: '最大回撤', value: pct(s.max_drawdown) },
    { label: 'Sharpe', value: Number(s.sharpe ?? 0).toFixed(2) },
    { label: 'Sortino', value: Number(s.sortino ?? 0).toFixed(2) },
    { label: '胜率', value: pct(s.win_rate) },
  ]
})
const backtestStatusLabel: Record<string, { label: string; type: string }> = {
  pending: { label: '排队中', type: 'info' },
  running: { label: '回测中', type: 'warning' },
  completed: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' },
}
async function startBacktest() {
  if (!backtestPresetId.value) {
    ElMessage.warning('请选择预设')
    return
  }
  try {
    const task = await triggerBacktestMutation.mutateAsync({
      preset_id: backtestPresetId.value,
      years: backtestYears.value,
    })
    backtestRunId.value = task.id
    backtestStatus.value = task.status
    ElMessage.info('回测已启动，会在后台执行')
  } catch (e: any) {
    ElMessage.error(e.message || '回测启动失败')
  }
}

const { data: dataQuality } = useScreenerDataQuality()
const runFilter = ref('all')
const filteredRuns = computed(() => {
  const runs = runsData.value?.runs || []
  if (runFilter.value === 'all') return runs
  if (runFilter.value === 'active') {
    return runs.filter((r) =>
      ['pending', 'screening', 'judging', 'cancelling'].includes(r.status)
    )
  }
  return runs.filter((r) => r.status === runFilter.value)
})

const { data: scheduleData } = useScreenerSchedule()
const runScheduleMutation = useRunScreenerSchedule()
const nextScheduleRun = computed(() => {
  const raw = scheduleData.value?.job?.next_run
  return raw ? formatLocalTime(raw) : '-'
})
async function runScheduleNow() {
  try {
    await runScheduleMutation.mutateAsync()
    ElMessage.success('定时选股已加入后台队列，完成后可在历史运行查看')
  } catch (e: any) {
    ElMessage.error(e.message || '触发失败')
  }
}
function exportRun(run: ScreenerRunSummary) {
  window.open(`/api/screener/runs/${run.id}/export`, '_blank')
}

const cancelRunId = ref<string | null>(null)
const cancelMutation = useCancelScreenerRun()
async function cancelRun(run: ScreenerRunSummary) {
  cancelRunId.value = run.id
  try {
    await cancelMutation.mutateAsync(run.id)
    ElMessage.info('已请求取消，运行会在当前步骤结束后停止')
    if (activeRunId.value === run.id) activeRunId.value = run.id
  } catch (e: any) {
    ElMessage.error(e.message || '取消失败')
  }
}

watch(activeRun, (run) => {
  if (run && (run.status === 'completed' || run.status === 'failed' || run.status === 'cancelled')) {
    refetchRuns()
  }
}, { immediate: true })

async function handleTrigger() {
  try {
    const body = triggerMode.value === 'presets' ? presetParams() : {}
    const run = await triggerRun.mutateAsync(body)
    activeRunId.value = run.id
    ElMessage.info(
      triggerMode.value === 'presets'
        ? '筛选已启动（预设模式，跳过 LLM 翻译）...'
        : '筛选已启动，LLM 翻译标准与逐只深判需要几分钟...',
    )
  } catch (e: any) { ElMessage.error(e.message || '触发失败') }
}

// ── 预设组合模式 ──
const { data: presetsData } = useScreenerPresets()
const presets = computed(() => presetsData.value?.presets || [])
const activePresets = computed(() => presets.value.filter((p) => p.is_active))
watch(activePresets, (ps) => {
  if (!backtestPresetId.value && ps.length) backtestPresetId.value = ps[0].id
}, { immediate: true })
const triggerMode = ref<'presets' | 'freeform'>('presets')
const selectedPresetIds = ref<string[]>([])
const combineMode = ref<'union' | 'intersection' | 'flatten'>('union')
const pool = ref('all')
const showPresetManager = ref(false)

// 指标中文名，用于卡片上的规则摘要
const { data: metricsData } = useScreenerMetrics()
const metricNames = computed(
  () => new Map((metricsData.value?.metrics || []).map((m) => [m.key, m.name_cn])),
)

// 首次加载默认勾选内置标准；之后只裁剪已停用的预设，不覆盖用户选择
const defaultPresetSelectionApplied = ref(false)
watch(activePresets, (list) => {
  if (!list.length) return
  if (!defaultPresetSelectionApplied.value) {
    selectedPresetIds.value = list.filter((p) => p.is_builtin).map((p) => p.id)
    defaultPresetSelectionApplied.value = true
  } else {
    const activeIds = new Set(list.map((p) => p.id))
    selectedPresetIds.value = selectedPresetIds.value.filter((id) => activeIds.has(id))
  }
}, { immediate: true })

function selectAllActive() {
  selectedPresetIds.value = activePresets.value.map((p) => p.id)
}

function togglePresetSelection(id: string) {
  selectedPresetIds.value = selectedPresetIds.value.includes(id)
    ? selectedPresetIds.value.filter((x) => x !== id)
    : [...selectedPresetIds.value, id]
}

function formatThreshold(metric: string, value: number): string {
  if (metric === 'market_cap') {
    return `${(value / 100_000_000).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}亿`
  }
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function presetRuleSummary(p: ScreenerPreset): string {
  const rules = p.quant_rules.map(
    (r) => `${metricNames.value.get(r.metric) || r.metric} ${r.op} ${formatThreshold(r.metric, r.value)}`,
  )
  const shown = rules.slice(0, 4).join(' · ')
  return rules.length > 4 ? `${shown} · +${rules.length - 4}` : shown
}

const _POOLS = [
  { value: 'all', label: '全市场' },
  { value: 'main', label: '主板' },
  { value: 'chinext', label: '创业板' },
  { value: 'star', label: '科创板' },
]
const _COMBINES = [
  { value: 'union', label: '并集（票数排名）' },
  { value: 'intersection', label: '交集（同时满足全部）' },
  { value: 'flatten', label: '拉平（全部条件 AND）' },
]
const styleLabels: Record<string, string> = {
  core: '核心资产', growth: '高成长', value: '深度价值',
  garp: 'GARP', cycle: '周期反转', financial: '金融价值',
  bank: '银行价值', insurance: '保险价值',
  custom: '自定义', quality: '质量',
}

const presetsReady = computed(() =>
  triggerMode.value === 'freeform' || selectedPresetIds.value.length > 0,
)

function presetParams() {
  return {
    mode: 'presets' as const,
    pool: pool.value,
    preset_ids: selectedPresetIds.value,
    combine: combineMode.value,
  }
}

const triggerPresets = useTriggerScreenerRunPresets()

function formatLocalTime(iso?: string | null): string {
  if (!iso) return '-'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  })
}

const statusLabel: Record<string, { label: string; type: string }> = {
  pending: { label: '排队中', type: 'info' },
  screening: { label: '初筛中', type: 'warning' },
  judging: { label: '深判中', type: 'warning' },
  cancelling: { label: '取消中', type: 'info' },
  cancelled: { label: '已取消', type: 'info' },
  completed: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' },
}

// ── 报告查看 ──
const viewingRunId = ref<string | null>(null)
const { data: reportData } = useScreenerRunReport(viewingRunId)
const reportHtml = computed(() => {
  const report = reportData.value?.report
  if (!report) return ''
  return DOMPurify.sanitize(marked.parse(report, { async: false }) as string)
})

function viewReport(run: ScreenerRunSummary) {
  viewingRunId.value = run.id
}

// ── 变化日报 ──
const viewingDiffRunId = ref<string | null>(null)
const diffBaseRunId = ref<string>('')
const { data: diffData } = useScreenerRunDiff(
  viewingDiffRunId,
  computed(() => diffBaseRunId.value || null),
)
const diffHtml = computed(() => {
  const diff = diffData.value?.diff
  if (!diff) return ''
  return DOMPurify.sanitize(marked.parse(diff, { async: false }) as string)
})

function viewDiff(run: ScreenerRunSummary) {
  viewingDiffRunId.value = run.id
  diffBaseRunId.value = ''
}

// ── 推荐后表现 ──
const viewingPerfRunId = ref<string | null>(null)
const { data: perfData } = useScreenerRunPerformance(viewingPerfRunId)
const perf = computed(() => perfData.value)
const perfSummaryRows = computed(() => {
  const summary = perf.value?.summary || {}
  const labels: Record<string, string> = {
    '1m': '1 个月', '3m': '3 个月', '6m': '6 个月', '12m': '12 个月', current: '当前',
  }
  return Object.entries(labels).map(([key, label]) => ({
    key, label, ...(summary[key] || { count: 0, avg_return: null, hit_rate: null }),
  }))
})

function formatPct(value?: number | null): string {
  return value === null || value === undefined ? '-' : `${(value * 100).toFixed(2)}%`
}

function viewPerformance(run: ScreenerRunSummary) {
  viewingPerfRunId.value = run.id
}

// ── 组合构建 ──
const portfolioRunId = ref<string | null>(null)
const portfolioMutation = useScreenerPortfolio(portfolioRunId)
const portfolioResult = ref<ScreenerPortfolioResult | null>(null)
const portfolioParams = ref({
  capital: 1_000_000,
  method: 'equal',
  max_weight: 0.15,
  max_industry_weight: 0.35,
  max_holdings: 20,
})

function viewPortfolio(run: ScreenerRunSummary) {
  portfolioRunId.value = run.id
  portfolioResult.value = null
}

const handoffRunId = ref<string | null>(null)
const handoffMutation = usePushScreenerToResearch(handoffRunId)

// ── 运行明细 + 单只操作 ──
const detailRunId = ref<string | null>(null)
const { data: detailData } = useScreenerRun(detailRunId)
const watchlistRunId = ref<string | null>(null)
const watchlistMutation = usePushScreenerToWatchlist(watchlistRunId)
const verdictLabel: Record<string, { label: string; type: string }> = {
  recommend: { label: '推荐', type: 'success' },
  reject: { label: '未通过', type: 'danger' },
  insufficient: { label: '数据不足', type: 'warning' },
  failed: { label: '深判失败', type: 'info' },
}
function viewDetail(run: ScreenerRunSummary) {
  detailRunId.value = run.id
}
async function pushOneToResearch(row: ScreenerJudgement) {
  if (!detailRunId.value) return
  handoffRunId.value = detailRunId.value
  try {
    const r = await handoffMutation.mutateAsync({ tickers: [row.ticker], limit: 1 })
    if (r.created.length) ElMessage.success(`已为 ${row.name} 创建研究会话`)
    else ElMessage.info(`${row.name} 已有研究会话`)
  } catch (e: any) {
    ElMessage.error(e.message || '送入研究失败')
  }
}
async function addOneToWatchlist(row: ScreenerJudgement) {
  if (!detailRunId.value) return
  watchlistRunId.value = detailRunId.value
  try {
    const r = await watchlistMutation.mutateAsync({ tickers: [row.ticker] })
    if (r.added.length) ElMessage.success(`${row.name} 已加入自选`)
    else if (r.already.length) ElMessage.info(`${row.name} 已在自选中`)
    else ElMessage.warning(`${row.name} 缺少公司记录，无法加入自选`)
  } catch (e: any) {
    ElMessage.error(e.message || '加入自选失败')
  }
}

async function pushToResearch(run: ScreenerRunSummary) {
  handoffRunId.value = run.id
  try {
    const result = await handoffMutation.mutateAsync({ limit: 5 })
    const skipped = result.skipped.length ? `，跳过 ${result.skipped.length} 只` : ''
    ElMessage.success(`已创建 ${result.created.length} 个研究会话${skipped}`)
  } catch (e: any) {
    ElMessage.error(e.message || '送入研究失败')
  }
}

async function buildPortfolio() {
  try {
    portfolioResult.value = await portfolioMutation.mutateAsync({ ...portfolioParams.value })
  } catch (e: any) {
    ElMessage.error(e.message || '组合构建失败')
  }
}

const { data: savedPortfoliosData, refetch: refetchSavedPortfolios } =
  useScreenerPortfolios(portfolioRunId)
const deletePortfolioMutation = useDeleteScreenerPortfolio()

async function savePortfolio() {
  if (!portfolioResult.value) return
  try {
    const { value } = await ElMessageBox.prompt('组合名称（可留空）', '保存组合', {
      inputValue: `组合 ${new Date().toLocaleDateString('zh-CN')}`,
      confirmButtonText: '保存',
      cancelButtonText: '取消',
    })
    const saved = await portfolioMutation.mutateAsync({
      ...portfolioParams.value,
      save: true,
      name: value || null,
    })
    portfolioResult.value = saved
    ElMessage.success('组合已保存')
    await refetchSavedPortfolios()
  } catch (e: any) {
    if (e === 'cancel' || e === 'close') return
    ElMessage.error(e.message || '保存失败')
  }
}

function loadSavedPortfolio(p: ScreenerSavedPortfolio) {
  portfolioResult.value = { ...p.result, run_id: portfolioRunId.value || p.run_id }
  portfolioParams.value = {
    capital: p.params.capital,
    method: p.params.method,
    max_weight: p.params.max_weight,
    max_industry_weight: p.params.max_industry_weight,
    max_holdings: p.params.max_holdings,
  }
}

async function removeSavedPortfolio(p: ScreenerSavedPortfolio) {
  try {
    await ElMessageBox.confirm(`删除组合「${p.name || p.id.slice(0, 8)}」？`, '确认删除', {
      type: 'warning',
    })
    await deletePortfolioMutation.mutateAsync(p.id)
    ElMessage.success('已删除')
  } catch (e: any) {
    if (e === 'cancel' || e === 'close') return
    ElMessage.error(e.message || '删除失败')
  }
}
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h1 class="page-title">🎯 智能选股</h1>
        <p class="page-desc">维护选股标准 → 手动触发 → LLM 翻译标准并逐只深判 → 输出推荐报告</p>
      </div>
    </div>

    <el-row :gutter="12">
      <el-col :span="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>选股标准（markdown，随时修改）</span>
              <el-button size="small" type="primary" :loading="saveCriteria.isPending.value" @click="handleSaveCriteria">保存标准</el-button>
            </div>
          </template>
          <el-input v-model="criteriaText" type="textarea" :rows="14" placeholder="用自然语言描述你的选股标准和股票池..." />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>运行</span>
              <el-radio-group v-model="triggerMode" size="small">
                <el-radio-button value="presets">预设组合</el-radio-button>
                <el-radio-button value="freeform">自由文本</el-radio-button>
              </el-radio-group>
            </div>
          </template>

          <!-- 预设组合模式 -->
          <template v-if="triggerMode === 'presets'">
            <div class="preset-section">
              <div class="section-label">股票池</div>
              <el-select v-model="pool" style="width: 200px">
                <el-option v-for="p in _POOLS" :key="p.value" :value="p.value" :label="p.label" />
              </el-select>
            </div>
            <div class="preset-section">
              <div class="section-label">
                <span>
                  选择预设
                  <span class="section-hint">已选 {{ selectedPresetIds.length }}/{{ activePresets.length }}，默认勾选内置标准</span>
                </span>
                <span class="section-actions">
                  <el-button size="small" link type="primary" @click="selectAllActive">全选</el-button>
                  <el-button size="small" link @click="selectedPresetIds = []">清空</el-button>
                  <el-button size="small" link type="primary" @click="showPresetManager = true">管理预设</el-button>
                </span>
              </div>
              <el-empty v-if="!activePresets.length" description="暂无启用的预设，点击「管理预设」新建" :image-size="48" />
              <div class="preset-cards">
                <div
                  v-for="p in activePresets"
                  :key="p.id"
                  class="preset-card"
                  :class="{ selected: selectedPresetIds.includes(p.id) }"
                  @click="togglePresetSelection(p.id)"
                >
                  <div class="preset-card-head">
                    <span class="preset-card-name">{{ p.name }}</span>
                    <span class="preset-card-tags">
                      <el-tag v-if="p.is_builtin" size="small" type="warning">内置</el-tag>
                      <el-tag v-if="p.style_tag && styleLabels[p.style_tag] !== p.name" size="small">
                        {{ styleLabels[p.style_tag] || p.style_tag }}
                      </el-tag>
                    </span>
                  </div>
                  <div v-if="p.description" class="preset-card-desc">{{ p.description }}</div>
                  <div class="preset-card-rules">{{ presetRuleSummary(p) }}</div>
                  <div class="preset-card-foot">
                    <span v-if="p.qualitative.length" class="preset-card-qual">定性 {{ p.qualitative.length }} 条</span>
                    <span class="preset-card-check">{{ selectedPresetIds.includes(p.id) ? '✓ 已选' : '选择' }}</span>
                  </div>
                </div>
              </div>
            </div>
            <div class="preset-section">
              <div class="section-label">组合方式</div>
              <el-radio-group v-model="combineMode">
                <el-radio v-for="c in _COMBINES" :key="c.value" :value="c.value">{{ c.label }}</el-radio>
              </el-radio-group>
            </div>
          </template>

          <!-- 自由文本模式提示 -->
          <div v-else class="text-secondary freeform-hint">
            使用左侧标准文档（criteria.md），LLM 翻译后执行筛选。
          </div>

          <el-button
            type="primary" class="mt-2" :loading="running" :disabled="running || !presetsReady"
            @click="handleTrigger"
          >
            {{ running ? '筛选进行中...' : '开始筛选' }}
          </el-button>
          <div v-if="running && activeRun" class="run-status">
            <el-tag :type="(statusLabel[activeRun.status]?.type as any) || 'info'">
              {{ statusLabel[activeRun.status]?.label || activeRun.status }}
            </el-tag>
            <span class="text-secondary">候选 {{ activeRun.candidate_count ?? '-' }} / 推荐 {{ activeRun.result_count ?? '-' }}</span>
          </div>
          <div v-if="activeRun?.error" class="run-error">{{ activeRun.error }}</div>
        </el-card>

        <el-card class="mt-3">
          <template #header>
            <div class="card-header">
              <span>定时任务</span>
              <el-tag size="small" :type="scheduleData?.scheduler_running ? 'success' : 'info'">
                {{ scheduleData?.scheduler_running ? '调度器运行中' : '调度器未运行' }}
              </el-tag>
            </div>
          </template>
          <div v-if="scheduleData" class="schedule-grid">
            <div><span class="text-secondary">计划：</span>{{ scheduleData.schedule }}</div>
            <div><span class="text-secondary">预设：</span>{{ scheduleData.presets.join('、') || '-' }}</div>
            <div><span class="text-secondary">下次：</span>{{ nextScheduleRun }}</div>
            <div>
              <span class="text-secondary">通知：</span>
              <template v-if="scheduleData.webhook.enabled">
                已启用（{{ scheduleData.webhook.format }}，
                {{ scheduleData.webhook.notify_on === 'always' ? '每轮' : '有变化时' }}）
              </template>
              <template v-else>未配置 Webhook</template>
            </div>
          </div>
          <div class="mt-2 flex items-center gap-2">
            <el-button
              size="small" type="primary" plain
              :loading="runScheduleMutation.isPending.value"
              @click="runScheduleNow"
            >立即运行定时选股</el-button>
            <span class="text-xs text-secondary">后台执行；失败会推送告警（已配置 Webhook 时）</span>
          </div>
        </el-card>

        <el-card class="mt-3">
          <template #header>
            <div class="card-header">
              <span>数据质量</span>
              <el-tag
                v-if="dataQuality" size="small"
                :type="dataQuality.warnings.length ? 'warning' : 'success'"
              >{{ dataQuality.warnings.length ? `${dataQuality.warnings.length} 项提示` : '正常' }}</el-tag>
            </div>
          </template>
          <template v-if="dataQuality">
            <div class="dq-grid">
              <div><span class="text-secondary">财务期：</span>{{ dataQuality.financial.period || '-' }}（{{ dataQuality.financial.tickers }} 只）</div>
              <div>
                <span class="text-secondary">行情覆盖：</span>
                {{ dataQuality.prices.tickers_with_200_bars }}/{{ dataQuality.prices.companies }} 只
                （{{ formatPct(dataQuality.prices.coverage) }}）
              </div>
              <div><span class="text-secondary">知识库：</span>{{ dataQuality.knowledge.indexed_documents }} 文档 / {{ dataQuality.knowledge.chunks }} 切片</div>
              <div><span class="text-secondary">最新行情：</span>{{ dataQuality.prices.last_price_date || '-' }}</div>
            </div>
            <div class="dq-metrics">
              <el-tag
                v-for="(m, key) in dataQuality.financial.metrics" :key="key" size="small"
                :type="m.coverage >= 0.8 ? 'success' : m.coverage >= 0.5 ? 'warning' : 'danger'"
              >{{ metricNames.get(key) || key }} {{ formatPct(m.coverage) }}</el-tag>
            </div>
            <div v-for="w in dataQuality.warnings" :key="w" class="run-error">⚠ {{ w }}</div>
          </template>
          <el-empty v-else description="加载中..." :image-size="40" />
        </el-card>

        <el-card class="mt-3">
          <template #header>
            <div class="card-header">
              <span>预设回测</span>
              <el-tag
                v-if="backtestData"
                size="small"
                :type="(backtestStatusLabel[backtestData.status]?.type as any) || 'info'"
              >{{ backtestStatusLabel[backtestData.status]?.label || backtestData.status }}</el-tag>
            </div>
          </template>
          <el-form :inline="true" size="small">
            <el-form-item label="预设">
              <el-select v-model="backtestPresetId" style="width: 150px" placeholder="选择预设">
                <el-option v-for="p in activePresets" :key="p.id" :value="p.id" :label="p.name" />
              </el-select>
            </el-form-item>
            <el-form-item label="年数">
              <el-input-number v-model="backtestYears" :min="1" :max="10" />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary" :loading="triggerBacktestMutation.isPending.value"
                @click="startBacktest"
              >开始回测</el-button>
            </el-form-item>
          </el-form>
          <div v-if="backtestData?.error" class="run-error">{{ backtestData.error }}</div>
          <template v-if="backtestSummary">
            <div class="backtest-metrics">
              <div v-for="m in backtestMetricRows" :key="m.label" class="backtest-metric">
                <div class="text-secondary">{{ m.label }}</div>
                <div class="font-medium">{{ m.value }}</div>
              </div>
            </div>
            <template v-if="backtestSplit">
              <div class="section-label mt-2">分段稳健性（前半 vs 后半）</div>
              <el-table :data="[
                { name: '前半', ...backtestSplit.first_half },
                { name: '后半', ...backtestSplit.second_half },
              ]" size="small">
                <el-table-column label="区间" prop="name" width="60" />
                <el-table-column label="期数" prop="periods_count" width="60" />
                <el-table-column label="年化" width="80">
                  <template #default="{ row }">{{ formatPct(row.cagr) }}</template>
                </el-table-column>
                <el-table-column label="基准年化" width="90">
                  <template #default="{ row }">{{ formatPct(row.bench_cagr) }}</template>
                </el-table-column>
                <el-table-column label="超额" width="80">
                  <template #default="{ row }">{{ formatPct(row.excess_cagr) }}</template>
                </el-table-column>
                <el-table-column label="回撤" width="80">
                  <template #default="{ row }">{{ formatPct(row.max_drawdown) }}</template>
                </el-table-column>
                <el-table-column label="胜率" width="70">
                  <template #default="{ row }">{{ formatPct(row.win_rate) }}</template>
                </el-table-column>
              </el-table>
              <div class="text-xs text-secondary mt-1">
                {{ backtestSplit.consistent_excess ? '两段均跑赢基准' : '超额并非两段都为正' }} ·
                {{ backtestSplit.disclaimer }}
              </div>
            </template>
            <div class="section-label mt-2">逐年明细</div>
            <el-table :data="backtestYearly" size="small" max-height="220">
              <el-table-column label="年度" prop="year" width="70" />
              <el-table-column label="收益" width="80">
                <template #default="{ row }">{{ formatPct(row.return) }}</template>
              </el-table-column>
              <el-table-column label="基准" width="80">
                <template #default="{ row }">{{ formatPct(row.bench) }}</template>
              </el-table-column>
              <el-table-column label="超额" width="80">
                <template #default="{ row }">{{ formatPct(row.excess) }}</template>
              </el-table-column>
              <el-table-column label="持仓数" width="70">
                <template #default="{ row }">{{ row.holdings?.length ?? 0 }}</template>
              </el-table-column>
            </el-table>
          </template>
          <el-empty
            v-else-if="!backtestData"
            description="选择预设并运行回测" :image-size="40"
          />
        </el-card>

        <el-card class="mt-3">
          <template #header>
            <div class="card-header">
              <span>历史运行</span>
              <el-radio-group v-model="runFilter" size="small">
                <el-radio-button value="all">全部</el-radio-button>
                <el-radio-button value="active">进行中</el-radio-button>
                <el-radio-button value="completed">已完成</el-radio-button>
                <el-radio-button value="failed">失败</el-radio-button>
                <el-radio-button value="cancelled">已取消</el-radio-button>
              </el-radio-group>
            </div>
          </template>
          <el-table :data="filteredRuns" size="small" @row-click="viewReport">
            <el-table-column label="时间" width="160">
              <template #default="{ row }">{{ formatLocalTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="(statusLabel[row.status]?.type as any) || 'info'">
                  {{ statusLabel[row.status]?.label || row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="候选" prop="candidate_count" width="70" />
            <el-table-column label="推荐" prop="result_count" width="70" />
            <el-table-column label="报告" width="150">
              <template #default="{ row }">
                <el-button v-if="row.report_path" size="small" link type="primary" @click.stop="viewReport(row)">查看</el-button>
                <el-button size="small" link @click.stop="exportRun(row)">CSV</el-button>
                <el-button size="small" link @click.stop="viewDetail(row)">明细</el-button>
              </template>
            </el-table-column>
            <el-table-column label="变化" width="70">
              <template #default="{ row }">
                <el-button size="small" link @click.stop="viewDiff(row)">日报</el-button>
              </template>
            </el-table-column>
            <el-table-column label="表现" width="70">
              <template #default="{ row }">
                <el-button size="small" link @click.stop="viewPerformance(row)">表现</el-button>
              </template>
            </el-table-column>
            <el-table-column label="组合" width="70">
              <template #default="{ row }">
                <el-button size="small" link @click.stop="viewPortfolio(row)">组合</el-button>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="70">
              <template #default="{ row }">
                <el-button
                  v-if="['pending', 'screening', 'judging', 'cancelling'].includes(row.status)"
                  size="small" link type="danger"
                  :disabled="row.status === 'cancelling'"
                  :loading="cancelMutation.isPending.value && cancelRunId === row.id"
                  @click.stop="cancelRun(row)"
                >取消</el-button>
              </template>
            </el-table-column>
            <el-table-column label="研究" width="70">
              <template #default="{ row }">
                <el-button
                  size="small" link type="primary"
                  :loading="handoffMutation.isPending.value && handoffRunId === row.id"
                  @click.stop="pushToResearch(row)"
                >送入</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 预设管理抽屉 -->
    <el-drawer v-model="showPresetManager" title="预设管理" size="640px">
      <PresetManager />
    </el-drawer>

    <el-card v-if="viewingRunId" class="mt-3">
      <template #header>
        <div class="card-header">
          <span>选股报告</span>
          <el-button size="small" link @click="viewingRunId = null">关闭</el-button>
        </div>
      </template>
      <div class="report-md" v-html="reportHtml" />
    </el-card>

    <el-card v-if="viewingDiffRunId" class="mt-3">
      <template #header>
        <div class="card-header">
          <span>变化日报</span>
          <div class="flex items-center gap-2">
            <el-select
              v-model="diffBaseRunId" size="small" clearable
              placeholder="自动（同口径上一轮）" style="width: 220px"
            >
              <el-option value="" label="自动（同口径上一轮）" />
              <el-option
                v-for="r in (runsData?.runs || []).filter(
                  (x) => x.id !== viewingDiffRunId && x.status === 'completed'
                )"
                :key="r.id" :value="r.id"
                :label="`${formatLocalTime(r.created_at)} · ${r.id.slice(0, 8)}`"
              />
            </el-select>
            <el-button size="small" link @click="viewingDiffRunId = null">关闭</el-button>
          </div>
        </div>
      </template>
      <div class="report-md" v-html="diffHtml" />
    </el-card>

    <el-card v-if="detailRunId" class="mt-3">
      <template #header>
        <div class="card-header">
          <span>运行明细 {{ detailRunId.slice(0, 8) }}（{{ detailData?.judgements?.length || 0 }} 只）</span>
          <el-button size="small" link @click="detailRunId = null">关闭</el-button>
        </div>
      </template>
      <el-table :data="detailData?.judgements || []" size="small" max-height="380">
        <el-table-column label="代码" prop="ticker" width="80" />
        <el-table-column label="名称" prop="name" width="100" />
        <el-table-column label="结论" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="(verdictLabel[row.verdict]?.type as any) || 'info'">
              {{ verdictLabel[row.verdict]?.label || row.verdict || '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="置信度" width="75">
          <template #default="{ row }">{{ row.confidence ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="行业" width="90">
          <template #default="{ row }">{{ row.snapshot?.industry || '-' }}</template>
        </el-table-column>
        <el-table-column label="现价" width="80">
          <template #default="{ row }">{{ row.snapshot?.price ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="理由/错误" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.error || (row.reasons || []).join('；') || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="110">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'ok' && row.recommend"
              size="small" link type="primary"
              :loading="handoffMutation.isPending.value && handoffRunId === detailRunId"
              @click.stop="pushOneToResearch(row)"
            >送入</el-button>
            <el-button
              v-if="row.status === 'ok' && row.recommend"
              size="small" link
              :loading="watchlistMutation.isPending.value && watchlistRunId === detailRunId"
              @click.stop="addOneToWatchlist(row)"
            >自选</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="portfolioRunId" class="mt-3">
      <template #header>
        <div class="card-header">
          <span>组合构建</span>
          <el-button size="small" link @click="portfolioRunId = null">关闭</el-button>
        </div>
      </template>
      <el-form :inline="true" size="small">
        <el-form-item label="资金">
          <el-input-number v-model="portfolioParams.capital" :min="1000" :step="100000" />
        </el-form-item>
        <el-form-item label="权重">
          <el-select v-model="portfolioParams.method" style="width: 120px">
            <el-option value="equal" label="等权" />
            <el-option value="score" label="筛选得分" />
            <el-option value="confidence" label="置信度" />
          </el-select>
        </el-form-item>
        <el-form-item label="单票上限">
          <el-input-number v-model="portfolioParams.max_weight" :min="0.01" :max="1" :step="0.01" />
        </el-form-item>
        <el-form-item label="行业上限">
          <el-input-number v-model="portfolioParams.max_industry_weight" :min="0.01" :max="1" :step="0.05" />
        </el-form-item>
        <el-form-item label="最多持仓">
          <el-input-number v-model="portfolioParams.max_holdings" :min="1" :max="100" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="portfolioMutation.isPending.value" @click="buildPortfolio">构建</el-button>
          <el-button :disabled="!portfolioResult" @click="savePortfolio">保存</el-button>
        </el-form-item>
      </el-form>
      <div v-if="savedPortfoliosData?.portfolios?.length" class="saved-portfolios">
        <span class="text-secondary" style="font-size: 12px">已保存：</span>
        <el-tag
          v-for="p in savedPortfoliosData.portfolios" :key="p.id"
          size="small" closable
          @click="loadSavedPortfolio(p)"
          @close="removeSavedPortfolio(p)"
        >
          {{ p.name || p.id.slice(0, 8) }}
          <span v-if="p.created_at"> · {{ formatLocalTime(p.created_at) }}</span>
        </el-tag>
      </div>
      <template v-if="portfolioResult">
        <div class="text-secondary" style="font-size: 12px; margin: 8px 0">
          投入 {{ portfolioResult.invested.toLocaleString('zh-CN', { maximumFractionDigits: 0 }) }} ·
          现金 {{ portfolioResult.cash.toLocaleString('zh-CN', { maximumFractionDigits: 0 }) }}
          （{{ formatPct(portfolioResult.cash_weight) }}）
        </div>
        <div v-for="w in portfolioResult.warnings" :key="w" class="text-secondary" style="font-size: 12px">
          ⚠ {{ w }}
        </div>
        <el-table :data="portfolioResult.holdings" size="small" class="mt-2">
          <el-table-column label="代码" prop="ticker" width="80" />
          <el-table-column label="名称" prop="name" width="100" />
          <el-table-column label="行业" prop="industry" width="100" />
          <el-table-column label="价格" prop="price" width="80" />
          <el-table-column label="权重" width="90">
            <template #default="{ row }">{{ formatPct(row.weight) }}</template>
          </el-table-column>
          <el-table-column label="金额" width="120">
            <template #default="{ row }">{{ row.amount.toLocaleString('zh-CN', { maximumFractionDigits: 0 }) }}</template>
          </el-table-column>
        </el-table>
      </template>
    </el-card>

    <el-card v-if="viewingPerfRunId" class="mt-3">
      <template #header>
        <div class="card-header">
          <span>推荐后表现</span>
          <el-button size="small" link @click="viewingPerfRunId = null">关闭</el-button>
        </div>
      </template>
      <template v-if="perf">
        <div class="text-secondary" style="font-size: 12px; margin-bottom: 8px">
          推荐 {{ perf.recommended_count }} 只 · 有买入价 {{ perf.with_entry_price }} 只 · {{ perf.entry_rule }}
        </div>
        <el-table :data="perfSummaryRows" size="small">
          <el-table-column label="期限" prop="label" width="90" />
          <el-table-column label="样本数" prop="count" width="80" />
          <el-table-column label="平均收益" width="110">
            <template #default="{ row }">{{ formatPct(row.avg_return) }}</template>
          </el-table-column>
          <el-table-column label="基准" width="90">
            <template #default="{ row }">{{ formatPct(row.bench_return) }}</template>
          </el-table-column>
          <el-table-column label="超额" width="90">
            <template #default="{ row }">{{ formatPct(row.excess_return) }}</template>
          </el-table-column>
          <el-table-column label="胜率" width="100">
            <template #default="{ row }">{{ formatPct(row.hit_rate) }}</template>
          </el-table-column>
        </el-table>
        <el-table :data="perf.stocks" size="small" class="mt-2">
          <el-table-column label="代码" prop="ticker" width="80" />
          <el-table-column label="名称" prop="name" width="100" />
          <el-table-column label="行业" prop="industry" width="100" />
          <el-table-column label="买入日" prop="entry_date" width="110" />
          <el-table-column label="买入价" prop="entry_price" width="90" />
          <el-table-column label="当前" width="90">
            <template #default="{ row }">{{ formatPct(row.current_return) }}</template>
          </el-table-column>
          <el-table-column label="1M" width="80">
            <template #default="{ row }">{{ formatPct(row.horizons?.['1m']) }}</template>
          </el-table-column>
          <el-table-column label="3M" width="80">
            <template #default="{ row }">{{ formatPct(row.horizons?.['3m']) }}</template>
          </el-table-column>
          <el-table-column label="6M" width="80">
            <template #default="{ row }">{{ formatPct(row.horizons?.['6m']) }}</template>
          </el-table-column>
          <el-table-column label="12M" width="80">
            <template #default="{ row }">{{ formatPct(row.horizons?.['12m']) }}</template>
          </el-table-column>
        </el-table>
        <div v-if="perf.message" class="text-secondary mt-2">{{ perf.message }}</div>
      </template>
    </el-card>
  </div>
</template>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; }
.schedule-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px; font-size: 13px; }
.dq-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px; font-size: 13px; }
.dq-metrics { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.backtest-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 4px 0 8px; font-size: 13px; }
.backtest-metric { padding: 6px 8px; border-radius: 6px; background: var(--bg-tertiary); }
.saved-portfolios { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 4px 0 8px; }
.saved-portfolios .el-tag { cursor: pointer; }
.run-status { margin-top: 12px; display: flex; align-items: center; gap: 12px; }
.run-error { margin-top: 8px; color: var(--danger); font-size: 13px; white-space: pre-wrap; }
.preset-section { margin-bottom: 14px; }
.section-label {
  font-size: 13px; font-weight: 600; margin-bottom: 6px;
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
}
.section-hint { margin-left: 6px; font-size: 12px; font-weight: 400; color: var(--text-secondary, #909399); }
.section-actions { display: flex; align-items: center; gap: 2px; flex-shrink: 0; }
.preset-cards { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.preset-card {
  border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px;
  cursor: pointer; display: flex; flex-direction: column; gap: 5px;
  transition: border-color 0.15s, background 0.15s;
}
.preset-card:hover { border-color: var(--primary, #409eff); }
.preset-card.selected { border-color: var(--primary, #409eff); background: var(--el-color-primary-light-9, #ecf5ff); }
.preset-card-head { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.preset-card-name { font-size: 13px; font-weight: 600; }
.preset-card-tags { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.preset-card-desc { font-size: 12px; color: var(--text-secondary, #909399); line-height: 1.4; }
.preset-card-rules { font-size: 12px; line-height: 1.45; color: var(--text-regular, #606266); }
.preset-card-foot { display: flex; align-items: center; justify-content: space-between; font-size: 12px; }
.preset-card-qual { color: var(--text-secondary, #909399); }
.preset-card-check { color: var(--primary, #409eff); font-weight: 500; }
.preset-card:not(.selected) .preset-card-check { color: var(--text-secondary, #909399); font-weight: 400; }
.freeform-hint { font-size: 13px; margin-bottom: 8px; }
.report-md :deep(h1) { font-size: 20px; margin: 12px 0; }
.report-md :deep(h2) { font-size: 16px; margin: 16px 0 8px; }
.report-md :deep(h3) { font-size: 14px; margin: 12px 0 6px; }
.report-md :deep(table) { border-collapse: collapse; width: 100%; margin: 8px 0; }
.report-md :deep(th), .report-md :deep(td) { border: 1px solid var(--border); padding: 6px 10px; font-size: 13px; }
</style>
