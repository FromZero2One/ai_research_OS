<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import {
  useScreenerDataQuality,
  useScreenerLatestReport,
  useScreenerMetrics,
  useScreenerPresets,
  useScreenerRun,
  useScreenerRunReport,
  useRunScreenerSchedule,
  useScreenerRuns,
  useScreenerSchedule,
  useTriggerScreenerRunPresets,
  type ScreenerJudgement,
  type ScreenerPreset,
  type ScreenerRunSummary,
} from '@/stores/api'

// ── 触发 + 运行状态轮询 ──
const activeRunId = ref<string | null>(null)
const { data: runsData, refetch: refetchRuns } = useScreenerRuns()

const activeStatus = computed(() => activeRun.value?.status)
// 进行中的运行每 3s 轮询详情
const { data: activeRun } = useScreenerRun(activeRunId, {
  poll: computed(() => !!activeRunId.value && running.value),
})
watch(activeStatus, (s) => {
  if (s === 'completed') ElMessage.success('筛选完成')
  if (s === 'failed') ElMessage.error(`筛选失败：${activeRun.value?.error || '未知原因'}`)
})

// 页面刷新/从别处触发后，自动接管仍在进行中的 run，否则不会轮询
watch(runsData, (v) => {
  if (activeRunId.value) return
  const active = (v?.runs || []).find((r) => ['pending', 'screening', 'judging'].includes(r.status))
  if (active) activeRunId.value = active.id
}, { immediate: true })

const running = computed(() =>
  activeStatus.value === 'pending' || activeStatus.value === 'screening' || activeStatus.value === 'judging'
  || (runsData.value?.runs || []).some((r) => ['pending', 'screening', 'judging'].includes(r.status)),
)

watch(activeRun, (run) => {
  if (run && (run.status === 'completed' || run.status === 'failed')) refetchRuns()
}, { immediate: true })

async function handleTrigger() {
  try {
    const run = await triggerPresets.mutateAsync(presetParams())
    activeRunId.value = run.id
    ElMessage.info('筛选已启动（预设模式），深判需要几分钟...')
  } catch (e: any) { ElMessage.error(e.message || '触发失败') }
}

// ── 预设组合模式 ──
const { data: presetsData } = useScreenerPresets()
const presets = computed(() => presetsData.value?.presets || [])
const activePresets = computed(() => presets.value.filter((p) => p.is_active))
const selectedPresetIds = ref<string[]>([])
const combineMode = ref<'union' | 'intersection' | 'flatten'>('union')
const pool = ref('all')

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
  cancelled: { label: '已取消', type: 'info' },
  completed: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' },
}

// 各状态对应的阶段描述，让用户在等待时知道当前在做什么
const stageDesc: Record<string, string> = {
  pending: '等待调度中，稍后开始初筛',
  screening: '正在采集全市场快照并执行量化初筛',
  judging: '正在进行 LLM 逐只定性深判',
  completed: '筛选完成，报告已生成',
  failed: '筛选失败，请查看错误信息',
}

// ── 数据质量 ──
const { data: dataQuality } = useScreenerDataQuality()

function formatPct(value?: number | null): string {
  return value === null || value === undefined ? '-' : `${(value * 100).toFixed(2)}%`
}

// ── 定时任务 ──
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

// ── 报告查看：默认最新报告，点击历史运行切换 ──
const viewingRunId = ref<string | null>(null)
const { data: latestReportData } = useScreenerLatestReport()
const { data: reportData } = useScreenerRunReport(viewingRunId)
const reportMarkdown = computed(() =>
  viewingRunId.value ? (reportData.value?.report ?? '') : (latestReportData.value?.report ?? ''),
)
const reportSource = computed(() =>
  viewingRunId.value
    ? `运行 ${viewingRunId.value.slice(0, 8)} · ${formatLocalTime(
      (runsData.value?.runs || []).find((r) => r.id === viewingRunId.value)?.created_at,
    )}`
    : '最新报告',
)
const reportHtml = computed(() => {
  if (!reportMarkdown.value) return ''
  return DOMPurify.sanitize(marked.parse(reportMarkdown.value, { async: false }) as string)
})

function viewReport(run: ScreenerRunSummary) {
  viewingRunId.value = run.report_path ? run.id : null
  if (!run.report_path) ElMessage.info('该运行尚无报告')
}
function backToLatest() {
  viewingRunId.value = null
}

// ── 运行明细 ──
const detailRunId = ref<string | null>(null)
const { data: detailData } = useScreenerRun(detailRunId)
const verdictLabel: Record<string, { label: string; type: string }> = {
  recommend: { label: '推荐', type: 'success' },
  reject: { label: '未通过', type: 'danger' },
  insufficient: { label: '数据不足', type: 'warning' },
  failed: { label: '深判失败', type: 'info' },
}
function viewDetail(run: ScreenerRunSummary) {
  detailRunId.value = run.id
}
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h1 class="page-title">🎯 价值推荐清单</h1>
        <p class="page-desc">选择预设组合 → 触发筛选 → 查看价值推荐报告</p>
      </div>
    </div>

    <!-- 触发栏 -->
    <el-card>
      <template #header>
        <div class="card-header">
          <span>开始筛选</span>
          <el-button
            type="primary" :loading="running" :disabled="running || selectedPresetIds.length === 0"
            @click="handleTrigger"
          >
            {{ running ? '筛选进行中...' : '开始筛选' }}
          </el-button>
        </div>
      </template>
      <div class="trigger-bar">
        <div class="trigger-field">
          <span class="section-label">股票池</span>
          <el-select v-model="pool" style="width: 140px">
            <el-option v-for="p in _POOLS" :key="p.value" :value="p.value" :label="p.label" />
          </el-select>
        </div>
        <div class="trigger-field">
          <span class="section-label">组合方式</span>
          <el-select v-model="combineMode" style="width: 200px">
            <el-option v-for="c in _COMBINES" :key="c.value" :value="c.value" :label="c.label" />
          </el-select>
        </div>
        <div class="trigger-field trigger-presets">
          <span class="section-label">
            <span>选择预设（已选 {{ selectedPresetIds.length }}/{{ activePresets.length }}）</span>
            <span class="section-actions">
              <el-button size="small" link type="primary" @click="selectedPresetIds = activePresets.map((p) => p.id)">全选</el-button>
              <el-button size="small" link @click="selectedPresetIds = []">清空</el-button>
            </span>
          </span>
          <el-empty v-if="!activePresets.length" description="暂无启用的预设" :image-size="48" />
          <div class="preset-cards">
            <div
              v-for="p in activePresets"
              :key="p.id"
              class="preset-card"
              :class="{ selected: selectedPresetIds.includes(p.id) }"
              @click="selectedPresetIds = selectedPresetIds.includes(p.id)
                ? selectedPresetIds.filter((x) => x !== p.id)
                : [...selectedPresetIds, p.id]"
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
            </div>
          </div>
        </div>
      </div>
      <div v-if="running && activeRun" class="run-status">
        <el-tag :type="(statusLabel[activeRun.status]?.type as any) || 'info'">
          {{ statusLabel[activeRun.status]?.label || activeRun.status }}
        </el-tag>
        <span class="text-secondary">{{ stageDesc[activeRun.status] || '' }}</span>
        <span class="text-secondary">候选 {{ activeRun.candidate_count ?? '-' }} / 推荐 {{ activeRun.result_count ?? '-' }}</span>
      </div>
      <div v-if="activeRun?.error" class="run-error">{{ activeRun.error }}</div>
    </el-card>

    <!-- 数据质量 -->
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

    <!-- 报告 -->
    <el-card class="mt-3">
      <template #header>
        <div class="card-header">
          <span>推荐报告 · {{ reportSource }}</span>
          <el-button v-if="viewingRunId" size="small" link type="primary" @click="backToLatest">回到最新报告</el-button>
        </div>
      </template>
      <div v-if="reportHtml" class="report-md" v-html="reportHtml" />
      <el-empty v-else-if="!running" description="暂无报告" :image-size="60" />
      <el-empty v-else description="筛选进行中，完成后生成报告..." :image-size="60" />
    </el-card>

    <!-- 定时任务 -->
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

    <!-- 历史运行 -->
    <el-card class="mt-3">
      <template #header>
        <span>历史运行</span>
      </template>
      <el-table :data="runsData?.runs || []" size="small">
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
        <el-table-column label="操作" width="130">
          <template #default="{ row }">
            <el-button v-if="row.report_path" size="small" link type="primary" @click="viewReport(row)">报告</el-button>
            <el-button size="small" link @click="viewDetail(row)">明细</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 运行明细 -->
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
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; }
.schedule-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px; font-size: 13px; }
.dq-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px; font-size: 13px; }
.dq-metrics { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.trigger-bar { display: flex; flex-direction: column; gap: 12px; }
.trigger-field { display: flex; flex-direction: column; gap: 6px; }
.trigger-presets { flex: 1; }
.run-status { margin-top: 12px; display: flex; align-items: center; gap: 12px; }
.run-error { margin-top: 8px; color: var(--danger); font-size: 13px; white-space: pre-wrap; }
.section-label {
  font-size: 13px; font-weight: 600; margin-bottom: 4px;
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
}
.section-actions { display: flex; align-items: center; gap: 2px; flex-shrink: 0; }
.preset-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.preset-card {
  border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px;
  cursor: pointer; display: flex; flex-direction: column; gap: 5px;
  transition: border-color 0.15s, background 0.15s;
}
.preset-card:hover { border-color: var(--primary, #409eff); }
.preset-card.selected { border-color: var(--primary, #409eff); background: rgba(64, 158, 255, 0.06); }
.preset-card-head { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.preset-card-name { font-weight: 600; font-size: 13px; }
.preset-card-tags { display: flex; gap: 4px; flex-shrink: 0; }
.preset-card-desc {
  font-size: 12px; color: var(--text-secondary, #909399);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.preset-card-rules { font-size: 12px; color: var(--text-secondary, #909399); }
</style>
