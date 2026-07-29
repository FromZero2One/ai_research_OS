<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useTimeline } from '@/stores/api'

const ticker = ref('')
const searchTicker = ref('')
const { data, isLoading } = useTimeline(searchTicker.value)
const router = useRouter()

function handleSearch() { searchTicker.value = ticker.value.toUpperCase().trim() }

const typeIcons: Record<string, string> = {
  session_created: '🆕', plan_generated: '🎯', report_generated: '📝',
  report_version: '📄', research_completed: '✅', status_change: '🔄', observation: '👁️',
}
const typeLabels: Record<string, string> = {
  session_created: '创建研究', plan_generated: '研究计划', report_generated: '报告生成',
  report_version: '报告版本', research_completed: '研究完结', status_change: '状态变更',
}
</script>

<template>
  <div class="page">
    <div class="page-header"><h1 class="page-title">研究时间线</h1><p class="page-desc">按公司查看所有研究活动的完整历史</p></div>

    <div class="search-bar">
      <el-input v-model="ticker" placeholder="输入公司代码，如 NVDA" style="text-transform: uppercase" @keydown.enter="handleSearch" />
      <el-button @click="handleSearch" :disabled="!ticker.trim()" type="primary">查询</el-button>
    </div>

    <div v-if="searchTicker" class="timeline-card">
      <div v-if="isLoading" class="loading-state">加载中...</div>
      <div v-else-if="!data || !data.company_name" class="loading-state">未找到公司「{{ searchTicker }}」的研究记录</div>
      <div v-else-if="data.events.length === 0" class="loading-state">「{{ data.company_name }}」暂无研究活动</div>
      <template v-else>
        <div class="timeline-header"><span class="timeline-company">{{ data.company_name }}<span class="text-sm font-normal text-secondary ml-2">({{ data.ticker }})</span></span><span class="text-xs text-secondary">{{ data.events.length }} 条事件</span></div>
        <div class="timeline">
          <div class="timeline-line" />
          <div v-for="(event, i) in data.events" :key="`${event.date}-${i}`" class="timeline-item">
            <div class="timeline-dot">{{ typeIcons[event.type] || '📌' }}</div>
            <div class="timeline-content">
              <div class="timeline-meta">
                <span class="timeline-date">{{ event.date ? new Date(event.date).toLocaleDateString('zh-CN') : '' }}</span>
                <el-tag size="small">{{ typeLabels[event.type] || event.type }}</el-tag>
              </div>
              <div class="timeline-detail">{{ event.detail }}</div>
              <el-button v-if="event.session_id" text size="small" @click="router.push(`/research/${event.session_id}`)">查看研究 →</el-button>
              <div v-if="event.type === 'observation'" class="timeline-observation">{{ event.detail }}</div>
              <div v-if="event.thesis" class="timeline-thesis"><span class="text-primary">观点:</span> {{ event.thesis?.slice(0, 120) }}...</div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 700px; margin: 0 auto; display: flex; flex-direction: column; gap: 24px; }
.search-bar { display: flex; gap: 12px; }
.timeline-card { padding: 20px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); }
.loading-state { text-align: center; padding: 32px 0; color: var(--text-secondary); }
.timeline-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.timeline-company { font-size: 18px; font-weight: 600; color: var(--text-primary); }
.timeline { position: relative; }
.timeline-line { position: absolute; left: 15px; top: 8px; bottom: 8px; width: 2px; background: var(--border); }
.timeline-item { position: relative; display: flex; gap: 16px; padding-bottom: 16px; }
.timeline-dot { position: relative; z-index: 1; width: 32px; height: 32px; border-radius: 50%; background: var(--bg-tertiary); border: 2px solid var(--border); display: flex; align-items: center; justify-content: center; font-size: 14px; flex-shrink: 0; }
.timeline-content { flex: 1; min-width: 0; padding-top: 4px; }
.timeline-meta { display: flex; align-items: center; gap: 8px; }
.timeline-date { font-size: 12px; color: var(--text-secondary); }
.timeline-detail { font-size: 14px; color: var(--text-primary); margin-top: 4px; }
.timeline-observation { margin-top: 4px; padding: 8px; border-radius: 4px; background: rgba(251,191,36,0.05); border: 1px solid rgba(251,191,36,0.2); font-size: 12px; color: var(--warning); }
.timeline-thesis { margin-top: 4px; padding: 8px; border-radius: 4px; background: var(--bg-tertiary); font-size: 12px; color: var(--text-secondary); }
</style>
