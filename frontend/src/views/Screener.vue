<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import {
  useSaveCriteria,
  useScreenerCriteria,
  useScreenerPresets,
  useScreenerRun,
  useScreenerRunReport,
  useScreenerRuns,
  useTriggerScreenerRun,
  useTriggerScreenerRunPresets,
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
                选择预设
                <el-button size="small" link type="primary" @click="showPresetManager = true">管理预设</el-button>
              </div>
              <el-empty v-if="!activePresets.length" description="暂无启用的预设，点击「管理预设」新建" :image-size="48" />
              <div class="preset-cards">
                <div
                  v-for="p in activePresets"
                  :key="p.id"
                  class="preset-card"
                  :class="{ selected: selectedPresetIds.includes(p.id) }"
                  @click="selectedPresetIds.includes(p.id)
                    ? selectedPresetIds = selectedPresetIds.filter((id) => id !== p.id)
                    : selectedPresetIds.push(p.id)"
                >
                  <div class="preset-card-name">{{ p.name }}</div>
                  <el-tag v-if="p.style_tag" size="small" class="preset-card-tag">{{ styleLabels[p.style_tag] || p.style_tag }}</el-tag>
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
.section-label { font-size: 13px; font-weight: 600; margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }
.preset-cards { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.preset-card {
  border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px;
  cursor: pointer; display: flex; align-items: center; justify-content: space-between; gap: 6px;
  transition: border-color 0.15s, background 0.15s;
}
.preset-card:hover { border-color: var(--primary, #409eff); }
.preset-card.selected { border-color: var(--primary, #409eff); background: var(--el-color-primary-light-9, #ecf5ff); }
.preset-card-name { font-size: 13px; font-weight: 500; }
.preset-card-tag { flex-shrink: 0; }
.freeform-hint { font-size: 13px; margin-bottom: 8px; }
.report-md :deep(h1) { font-size: 20px; margin: 12px 0; }
.report-md :deep(h2) { font-size: 16px; margin: 16px 0 8px; }
.report-md :deep(h3) { font-size: 14px; margin: 12px 0 6px; }
.report-md :deep(table) { border-collapse: collapse; width: 100%; margin: 8px 0; }
.report-md :deep(th), .report-md :deep(td) { border: 1px solid var(--border); padding: 6px 10px; font-size: 13px; }
</style>
