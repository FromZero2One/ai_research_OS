<script setup lang="ts">
import { computed } from 'vue'
import { useDashboard, useHealth, useLLMUsage, useObservations, useSchedulerStatus } from '@/stores/api'

const { data: scheduler } = useSchedulerStatus()
const { data: obsData } = useObservations()
const { data: dashboard } = useDashboard()
const { data: llmUsage } = useLLMUsage()

const hDash = useHealth('/dashboard')
const hResearch = useHealth('/research/sessions?limit=1')
const hCompanies = useHealth('/companies?limit=1')
const hScheduler = useHealth('/scheduler/status')

const stats = computed(() => [
  { label: 'API 状态', value: hDash.isSuccess.value ? '正常' : '异常' },
  { label: '调度器', value: scheduler.value?.running ? '运行中' : '已停止' },
  { label: '观测记录', value: obsData.value?.observations?.length || 0 },
  { label: 'Dashboard', value: dashboard.value ? '可用' : '不可用' },
])
const healthList = computed(() => [
  { name: 'Dashboard', isLoading: hDash.isLoading.value, isError: hDash.isError.value },
  { name: '研究', isLoading: hResearch.isLoading.value, isError: hResearch.isError.value },
  { name: '公司', isLoading: hCompanies.isLoading.value, isError: hCompanies.isError.value },
  { name: '调度器', isLoading: hScheduler.isLoading.value, isError: hScheduler.isError.value },
])
</script>

<template>
  <div class="page">
    <h1 class="page-title">📡 系统状态</h1>
    <p class="page-desc">系统运行状态、调度任务和执行记录</p>

    <el-row :gutter="16">
      <el-col v-for="s in stats" :key="s.label" :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-label">{{ s.label }}</div>
          <div class="stat-value">{{ s.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never">
      <template #header><div class="flex items-center justify-between"><span>⏱️ 调度器</span><el-tag :type="scheduler?.running ? 'success' : 'danger'" size="small">{{ scheduler?.running ? '运行中' : '已停止' }}</el-tag></div></template>
      <div v-if="scheduler?.jobs?.length" class="space-y-2">
        <div v-for="job in scheduler.jobs" :key="job.id" class="item-block">
          <div><div class="font-medium">{{ job.id }}</div><div class="text-xs text-secondary mt-0.5">触发: {{ job.trigger }}</div></div>
          <div class="text-xs text-secondary shrink-0">{{ job.next_run ? `下次: ${new Date(job.next_run).toLocaleString('zh-CN')}` : '无调度' }}</div>
        </div>
      </div>
      <el-empty v-else description="暂无调度任务" />
    </el-card>

    <el-card shadow="never">
      <template #header><div class="flex items-center justify-between"><span>🎯 LLM Token 用量</span><span class="text-xs text-secondary">{{ llmUsage?.note }}</span></div></template>
      <div v-if="llmUsage?.models && Object.keys(llmUsage.models).length" class="space-y-2">
        <div v-for="(s, model) in llmUsage.models" :key="model" class="item-block">
          <div><div class="font-medium text-sm">{{ model }}</div><div class="text-xs text-secondary mt-0.5">调用 {{ s.calls }} 次 · 最近 {{ s.last_used ? new Date(s.last_used).toLocaleString('zh-CN') : '' }}</div></div>
          <div class="text-xs text-secondary text-right">输入 {{ s.prompt_tokens.toLocaleString() }}<br />输出 {{ s.completion_tokens.toLocaleString() }} · 共 {{ s.total_tokens.toLocaleString() }}</div>
        </div>
        <div class="usage-total">合计：{{ llmUsage.totals.calls }} 次调用 · {{ llmUsage.totals.total_tokens.toLocaleString() }} tokens（输入 {{ llmUsage.totals.prompt_tokens.toLocaleString() }} / 输出 {{ llmUsage.totals.completion_tokens.toLocaleString() }}）</div>
      </div>
      <el-empty v-else description="暂无 LLM 调用记录" />
    </el-card>

    <el-card shadow="never">
      <template #header><div class="flex items-center justify-between"><span>👁️ 最近观测</span><span class="text-xs text-secondary">{{ obsData?.observations?.length || 0 }} 条记录</span></div></template>
      <div v-if="obsData?.observations?.length" class="space-y-2">
        <div v-for="obs in obsData.observations" :key="obs.id" class="item-block flex-col">
          <div class="flex items-center justify-between w-full"><span class="font-medium text-sm">{{ obs.company_name || obs.ticker }}</span><el-tag :type="obs.status === 'need_research' ? 'danger' : 'warning'" size="small">{{ obs.status }}</el-tag></div>
          <div class="text-xs text-secondary mt-1">{{ obs.reasons?.join('、') || '无信号' }}</div>
          <div class="text-xs text-gray mt-1">{{ obs.observed_at ? new Date(obs.observed_at).toLocaleString('zh-CN') : '' }}</div>
        </div>
      </div>
      <el-empty v-else description="暂无观测记录。运行调度器或手动触发观察。" />
    </el-card>

    <el-card shadow="never">
      <template #header>🔌 API 健康检查</template>
      <div class="space-y-2">
        <div v-for="h in healthList" :key="h.name" class="item-block">
          <span>{{ h.name }}</span>
          <span v-if="h.isLoading" class="text-xs text-secondary">检查中...</span>
          <span v-else-if="h.isError" class="text-xs text-danger">异常</span>
          <span v-else class="text-xs text-success">正常</span>
        </div>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header>⌨️ 快捷键</template>
      <div v-for="s in [{ keys: '⌘K / Ctrl+K', desc: '打开命令面板' }, { keys: '↑↓', desc: '命令面板中导航' }, { keys: 'Enter', desc: '执行命令' }, { keys: 'Esc', desc: '关闭面板' }]" :key="s.keys" class="shortcut-row">
        <kbd class="shortcut-key">{{ s.keys }}</kbd>
        <span class="shortcut-desc">{{ s.desc }}</span>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.page { max-width: 900px; margin: 0 auto; display: flex; flex-direction: column; gap: 24px; }
.stat-card { text-align: center; }
.stat-label { font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; }
.stat-value { font-size: 18px; font-weight: 600; color: var(--text-primary); }
.item-block { padding: 12px; border-radius: 8px; background: var(--bg-tertiary); display: flex; justify-content: space-between; align-items: flex-start; }
.item-block.flex-col { flex-direction: column; }
.usage-total { padding: 10px 12px; border-radius: 8px; background: var(--bg-secondary); font-size: 13px; color: var(--text-primary); }
.shortcut-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.shortcut-key { padding: 2px 8px; border-radius: 4px; background: var(--bg-tertiary); border: 1px solid var(--border); font-size: 12px; font-family: monospace; color: var(--text-primary); }
.shortcut-desc { font-size: 14px; color: var(--text-secondary); }
.text-danger { color: var(--danger); }
.text-success { color: var(--success); }
</style>
