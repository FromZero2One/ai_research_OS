<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useQueryClient } from '@tanstack/vue-query'
import { useDashboard } from '@/stores/api'

const queryClient = useQueryClient()
const { data, isLoading } = useDashboard()
const router = useRouter()
const generating = ref(false)

const statusLabel: Record<string, { label: string; type: string }> = {
  normal: { label: '正常', type: 'success' },
  attention: { label: '关注', type: 'warning' },
  need_research: { label: '需研究', type: 'danger' },
}

async function handleGenerateBrief() {
  generating.value = true
  await fetch('/api/dashboard/generate-brief', { method: 'POST' })
  queryClient.invalidateQueries({ queryKey: ['dashboard'] })
  generating.value = false
}

const today = new Date().toLocaleDateString('zh-CN', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })

function renderMarkdown(content: string) {
  const lines = content.split('\n')
  const els: any[] = []
  let key = 0
  for (const line of lines) {
    const t = line.trim()
    if (t.startsWith('## ')) { els.push({ type: 'h2', text: t.slice(3), key: key++ }) }
    else if (t.startsWith('### ')) { els.push({ type: 'h3', text: t.slice(4), key: key++ }) }
    else if (t.startsWith('- ')) { els.push({ type: 'li', text: inlineMd(t.slice(2)), key: key++ }) }
    else if (/^\d+\.\s/.test(t)) { els.push({ type: 'li', text: inlineMd(t.replace(/^\d+\.\s/, '')), key: key++ }) }
    else if (!t) { els.push({ type: 'spacer', key: key++ }) }
    else { els.push({ type: 'p', text: inlineMd(t), key: key++ }) }
  }
  return els
}

function inlineMd(text: string) { return text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>') }
</script>

<template>
  <div class="page">
    <div class="flex items-center justify-between">
      <div><h1 class="page-title">☀️ Daily Workspace</h1><p class="page-desc mt-1">{{ today }}</p></div>
      <div class="flex items-center gap-2 text-sm text-secondary"><span class="status-dot" />系统运行中</div>
    </div>

    <div v-if="isLoading" class="loading-state">加载中...</div>

    <template v-else>
      <el-row :gutter="12">
        <el-col v-for="action in [{ label:'快速研究', route:'/research/quick', icon:'⚡', desc:'一键 AI 研究' }, { label:'研究中心', route:'/research', icon:'🔬', desc:'查看研究会话' }, { label:'公司', route:'/companies', icon:'🏢', desc:'管理关注公司' }, { label:'行情', route:'/market', icon:'📊', desc:'市场行情与 K 线' }, { label:'上传文档', route:'/documents', icon:'📄', desc:'添加报告或纪要' }]" :key="action.label" :span="24/5">
          <el-card shadow="never" class="action-card" @click="router.push(action.route)">
            <div class="action-icon">{{ action.icon }}</div>
            <div class="action-label">{{ action.label }}</div>
            <div class="action-desc">{{ action.desc }}</div>
          </el-card>
        </el-col>
      </el-row>

      <el-row :gutter="24">
        <el-col :span="16">
          <el-card shadow="never" class="section-card">
            <template #header>
              <div class="flex items-center justify-between">
                <span>📋 晨间简报</span>
                <div class="flex items-center gap-2">
                  <span v-if="data?.morning_brief?.generated_at" class="text-xs text-secondary">{{ new Date(data.morning_brief.generated_at).toLocaleString('zh-CN') }}</span>
                  <el-button @click="handleGenerateBrief" :disabled="generating" size="small">{{ generating ? '生成中...' : '🔄 生成' }}</el-button>
                </div>
              </div>
            </template>
            <div v-if="data?.morning_brief?.content" class="brief-content">
              <template v-for="el in renderMarkdown(data.morning_brief.content)" :key="el.key">
                <h2 v-if="el.type === 'h2'" class="brief-h2">{{ el.text }}</h2>
                <h3 v-else-if="el.type === 'h3'" class="brief-h3">{{ el.text }}</h3>
                <p v-else-if="el.type === 'p'" class="brief-p" v-html="el.text" />
                <li v-else-if="el.type === 'li'" class="brief-li" v-html="el.text" />
                <div v-else-if="el.type === 'spacer'" class="h-1" />
              </template>
            </div>
            <el-empty v-else description="暂无简报。点击「生成」或系统将在工作日 6am 自动生成。" />
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="never" class="section-card">
            <template #header>⏰ 研究提醒</template>
            <div v-if="data?.research_reminders?.length" class="reminder-list">
              <div v-for="r in data.research_reminders.slice(0, 5)" :key="r.ticker" class="reminder-item">
                <div class="flex items-center justify-between">
                  <span class="reminder-name">{{ r.company_name }}</span>
                  <span class="reminder-days">{{ r.days_since_research }} 天</span>
                </div>
                <el-button text size="small" @click="router.push(`/research/quick?ticker=${r.ticker}`)">开始研究 →</el-button>
              </div>
            </div>
            <el-empty v-else description="没有待处理的研究提醒。" />
          </el-card>
        </el-col>
      </el-row>

      <el-card v-if="data?.watchlist?.length" shadow="never" class="section-card">
        <template #header>
          <div class="flex items-center justify-between">
            <span>👁️ 关注列表</span>
            <el-button text size="small" @click="router.push('/portfolio')">管理 →</el-button>
          </div>
        </template>
        <div v-for="wl in data.watchlist" :key="wl.watchlist_id">
          <div v-if="wl.items.length === 0" class="text-sm text-secondary py-2">关注列表为空</div>
          <el-table v-else :data="wl.items" stripe>
            <el-table-column label="公司" min-width="160">
              <template #default="{ row }">
                <el-button text @click="router.push(`/companies/${row.ticker}`)"><span class="font-medium">{{ row.company_name }}</span></el-button>
                <div class="text-xs text-secondary">{{ row.ticker }}</div>
              </template>
            </el-table-column>
            <el-table-column label="价格" prop="latest_price" align="right" width="100">
              <template #default="{ row }">{{ row.latest_price?.toFixed(2) ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="涨跌" align="right" width="100">
              <template #default="{ row }">
                <span v-if="row.price_change !== null" :class="row.price_change >= 0 ? 'text-success' : 'text-danger'">{{ row.price_change >= 0 ? '+' : '' }}{{ row.price_change }}%</span>
                <span v-else class="text-secondary">-</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" align="center" width="80">
              <template #default="{ row }">
                <el-tag :type="statusLabel[row.status]?.type || 'info'" size="small">{{ statusLabel[row.status]?.label || row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="观点" min-width="120">
              <template #default="{ row }"><span class="text-secondary truncate block">{{ row.thesis ?? '-' }}</span></template>
            </el-table-column>
          </el-table>
        </div>
      </el-card>

      <el-card v-if="data?.market_overview?.length" shadow="never" class="section-card">
        <template #header>
          <div class="flex items-center justify-between">
            <span>📈 行情概览</span>
            <el-button text size="small" @click="router.push('/market')">详细 →</el-button>
          </div>
        </template>
        <el-table :data="data.market_overview" stripe>
          <el-table-column label="公司" min-width="160">
            <template #default="{ row }">
              <el-button text @click="router.push(`/companies/${row.ticker}`)"><span class="font-medium">{{ row.company_name }}</span></el-button>
              <div class="text-xs text-secondary">{{ row.ticker }}</div>
            </template>
          </el-table-column>
          <el-table-column label="最新价" align="right" width="100">
            <template #default="{ row }">{{ row.latest_price?.toFixed(2) ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="涨跌幅" align="right" width="100">
            <template #default="{ row }">
              <span v-if="row.change_pct !== null" :class="row.change_pct >= 0 ? 'text-success' : 'text-danger'">{{ row.change_pct >= 0 ? '+' : '' }}{{ row.change_pct }}%</span>
              <span v-else class="text-secondary">-</span>
            </template>
          </el-table-column>
          <el-table-column label="行业" prop="sector" min-width="120" />
        </el-table>
      </el-card>

      <el-card v-if="data?.recent_research?.length" shadow="never" class="section-card">
        <template #header>
          <div class="flex items-center justify-between">
            <span>📋 最近研究</span>
            <el-button text size="small" @click="router.push('/research')">查看全部 →</el-button>
          </div>
        </template>
        <div v-for="s in data.recent_research" :key="s.id" class="research-item" @click="router.push(`/research/${s.id}`)">
          <div><div class="research-title">{{ s.title }}</div><div class="research-question">{{ s.question }}</div></div>
          <div class="flex items-center gap-2 shrink-0">
            <el-tag v-if="s.thesis" size="small" type="success">有观点</el-tag>
            <el-tag :type="s.status === 'completed' ? 'success' : s.status === 'researching' ? 'warning' : 'info'" size="small">{{ s.status }}</el-tag>
          </div>
        </div>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 1100px; margin: 0 auto; display: flex; flex-direction: column; gap: 24px; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success); }
.loading-state { text-align: center; padding: 80px 0; color: var(--text-secondary); }
.action-card { text-align: center; cursor: pointer; transition: border-color 0.2s; }
.action-card:hover { border-color: rgba(79,140,255,0.4); }
.action-icon { font-size: 24px; margin-bottom: 4px; }
.action-label { font-size: 14px; font-weight: 500; color: var(--text-primary); }
.action-desc { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }
.brief-content { max-height: 384px; overflow-y: auto; }
.brief-h2 { font-size: 18px; font-weight: 600; color: var(--text-primary); margin-top: 16px; margin-bottom: 8px; }
.brief-h3 { font-size: 16px; font-weight: 600; color: var(--text-primary); margin-top: 12px; margin-bottom: 4px; }
.brief-p { font-size: 14px; color: var(--text-primary); line-height: 1.6; margin-bottom: 4px; }
.brief-li { font-size: 14px; color: var(--text-primary); margin-left: 16px; }
.reminder-item { padding: 8px; border-radius: 8px; background: var(--bg-tertiary); margin-bottom: 8px; }
.reminder-name { font-size: 14px; font-weight: 500; color: var(--text-primary); }
.reminder-days { font-size: 12px; color: var(--danger); }
.research-item { display: flex; align-items: flex-start; justify-content: space-between; padding: 12px; border-radius: 8px; background: var(--bg-tertiary); margin-bottom: 8px; cursor: pointer; }
.research-item:hover { background: var(--border); }
.research-title { font-size: 14px; font-weight: 500; }
.research-question { font-size: 12px; color: var(--text-secondary); margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
