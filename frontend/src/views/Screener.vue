<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import {
  useSaveCriteria,
  useScreenerCriteria,
  useScreenerRun,
  useScreenerRunReport,
  useScreenerRuns,
  useTriggerScreenerRun,
  type ScreenerRunSummary,
} from '@/stores/api'

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
    const run = await triggerRun.mutateAsync({})
    activeRunId.value = run.id
    ElMessage.info('筛选已启动，LLM 翻译标准与逐只深判需要几分钟...')
  } catch (e: any) { ElMessage.error(e.message || '触发失败') }
}

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
          <template #header><span>运行</span></template>
          <el-button type="primary" :loading="running" :disabled="running" @click="handleTrigger">
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
.report-md :deep(h1) { font-size: 20px; margin: 12px 0; }
.report-md :deep(h2) { font-size: 16px; margin: 16px 0 8px; }
.report-md :deep(h3) { font-size: 14px; margin: 12px 0 6px; }
.report-md :deep(table) { border-collapse: collapse; width: 100%; margin: 8px 0; }
.report-md :deep(th), .report-md :deep(td) { border: 1px solid var(--border); padding: 6px 10px; font-size: 13px; }
</style>
