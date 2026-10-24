<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import {
  useSaveCriteria,
  useScreenerCriteria,
  useScreenerMetrics,
  useScreenerPresets,
  useScreenerRun,
  useScreenerRunReport,
  useScreenerRuns,
  useTriggerScreenerRun,
  useTriggerScreenerRunPresets,
  type ScreenerPreset,
  type ScreenerRunSummary,
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
  if (run && (run.status === 'completed' || run.status === 'failed')) {
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
  garp: 'GARP', cycle: '周期反转', custom: '自定义', quality: '质量',
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

const statusLabel: Record<string, { label: string; type: string }> = {
  pending: { label: '排队中', type: 'info' },
  screening: { label: '初筛中', type: 'warning' },
  judging: { label: '深判中', type: 'warning' },
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
          <template #header><span>历史运行</span></template>
          <el-table :data="runsData?.runs || []" size="small" @row-click="viewReport">
            <el-table-column label="时间" width="160">
              <template #default="{ row }">{{ row.created_at?.replace('T', ' ').slice(0, 16) }}</template>
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
            <el-table-column label="报告" width="80">
              <template #default="{ row }">
                <el-button v-if="row.report_path" size="small" link type="primary" @click.stop="viewReport(row)">查看</el-button>
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
  </div>
</template>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; }
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
