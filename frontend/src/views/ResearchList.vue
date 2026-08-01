<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { DECISION_LABELS, RESEARCH_STATUS_LABELS, useResearchSessions, useCreateResearch, useCompanies } from '@/stores/api'

const status = ref('all')
const { data: sessions, isLoading } = useResearchSessions(status.value === 'all' ? undefined : status.value)
const createResearch = useCreateResearch()
const { data: companiesData } = useCompanies()
const router = useRouter()

const showNew = ref(false)
const newTitle = ref('')
const newQuestion = ref('')
const newCompanyId = ref('')

const statusOptions = [
  { value: 'all', label: '全部' },
  { value: 'draft', label: '草稿' },
  { value: 'researching', label: '研究中' },
  { value: 'reviewing', label: '评审中' },
  { value: 'completed', label: '已完成' },
]

const filteredSessions = computed(() => {
  if (!sessions.value) return []
  if (status.value === 'all') return sessions.value
  return sessions.value.filter((s: any) => s.status === status.value)
})

async function handleCreate() {
  if (!newTitle.value.trim() || !newQuestion.value.trim()) return
  const body: Record<string, any> = { title: newTitle.value, question: newQuestion.value }
  if (newCompanyId.value) body.company_id = newCompanyId.value
  const result = await createResearch.mutateAsync(body as any)
  showNew.value = false
  newTitle.value = ''
  newQuestion.value = ''
  newCompanyId.value = ''
}

function getStatusType(s: string) {
  if (s === 'completed') return 'success'
  if (s === 'researching') return 'warning'
  if (s === 'draft') return 'info'
  return 'primary'
}
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div><h1 class="page-title">🔬 研究中心</h1><p class="page-desc">问题 → 证据 → 报告 → 决策</p></div>
      <el-button @click="showNew = !showNew" type="primary">+ 新建研究</el-button>
    </div>

    <div v-if="showNew" class="new-form">
      <el-input v-model="newTitle" placeholder="研究标题..." />
      <el-input v-model="newQuestion" placeholder="你要研究什么问题？..." type="textarea" :rows="3" />
      <el-select v-model="newCompanyId" placeholder="不关联公司（可选）" clearable filterable style="width:100%">
        <el-option v-for="c in companiesData?.items || []" :key="c.id" :label="`${c.ticker} — ${c.name}`" :value="c.id" />
      </el-select>
      <div class="flex gap-2">
        <el-button @click="handleCreate" :disabled="!newTitle.trim() || !newQuestion.trim() || createResearch.isPending.value" type="primary">{{ createResearch.isPending.value ? '创建中...' : '开始研究' }}</el-button>
        <el-button @click="showNew = false">取消</el-button>
      </div>
    </div>

    <el-radio-group v-model="status" class="filter-bar">
      <el-radio-button v-for="s in statusOptions" :key="s.value" :value="s.value">{{ s.label }}</el-radio-button>
    </el-radio-group>

    <div v-if="isLoading" class="loading-state">加载中...</div>
    <div v-else-if="!filteredSessions.length" class="empty-state">
      <div class="text-3xl mb-2">🔬</div>
      <div class="font-medium">还没有研究会话</div>
      <div class="text-sm text-secondary mt-1">提出一个研究问题开始分析</div>
    </div>
    <div v-else class="session-list">
      <div v-for="session in filteredSessions" :key="session.id" class="session-card" @click="router.push(`/research/${session.id}`)">
        <div class="session-main">
          <div class="session-title">{{ session.title }}</div>
          <div class="session-question">{{ session.question }}</div>
          <div v-if="session.thesis" class="session-thesis">论点: {{ session.thesis }}</div>
        </div>
        <div class="session-meta">
          <el-tag v-if="session.decision" :type="session.decision === 'buy' ? 'success' : session.decision === 'sell' ? 'danger' : 'warning'" size="small" effect="dark">{{ DECISION_LABELS[session.decision] || session.decision }}</el-tag>
          <el-tag :type="getStatusType(session.status)" size="small">{{ RESEARCH_STATUS_LABELS[session.status] || session.status }}</el-tag>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1000px; margin: 0 auto; display: flex; flex-direction: column; gap: 20px; }
.page-header { display: flex; align-items: center; justify-content: space-between; }
.new-form { display: flex; flex-direction: column; gap: 12px; padding: 20px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); }
.filter-bar { display: flex; gap: 4px; }
.loading-state, .empty-state { text-align: center; padding: 48px 0; color: var(--text-secondary); }
.session-list { display: flex; flex-direction: column; gap: 12px; }
.session-card { display: flex; align-items: flex-start; justify-content: space-between; padding: 20px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); cursor: pointer; transition: border-color 0.2s; }
.session-card:hover { border-color: rgba(79,140,255,0.3); }
.session-main { flex: 1; min-width: 0; }
.session-title { font-size: 18px; font-weight: 500; color: var(--text-primary); }
.session-question { font-size: 14px; color: var(--text-secondary); margin-top: 4px; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.session-thesis { font-size: 14px; color: var(--text-secondary); margin-top: 8px; font-style: italic; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.session-meta { display: flex; align-items: center; gap: 12px; margin-left: 16px; flex-shrink: 0; }
</style>
