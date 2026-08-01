<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  useCompany,
  useCompanyWorkspace,
  useDeleteCompany,
  useDocuments,
  useFinancialMetrics,
  useIngestFinancials,
  useIngestPrices,
  useIngestProfile,
  useMarketPrices,
  useResearchSessions,
  useUpdateCompany,
  useUpdateThesis,
} from '@/stores/api'
import FinancialBars from '@/components/FinancialBars.vue'
import StockChart from '@/components/StockChart.vue'

const route = useRoute(); const router = useRouter()
const id = route.params.id as string
const { data: company, isLoading } = useCompany(id)

const ingestPrices = useIngestPrices()
const ingestFinancials = useIngestFinancials()
const ingestProfile = useIngestProfile()
const deleteCompany = useDeleteCompany()
const updateCompany = useUpdateCompany(id)

const activeTab = ref('概览')
const { data: docsData } = useDocuments(); const { data: sessions } = useResearchSessions()
const { data: priceData } = useMarketPrices(company.value?.ticker || '', 260)
const { data: finData } = useFinancialMetrics(company.value?.ticker || '')
const { data: workspace } = useCompanyWorkspace(company.value?.ticker || '')
const updateThesis = useUpdateThesis()

const prices = computed(() => priceData.value?.prices || [])
const financials = computed(() => finData.value?.metrics || [])
const revenueData = computed(() => financials.value.filter((m) => m.metric_name === 'revenue').reverse())
const incomeData = computed(() => financials.value.filter((m) => m.metric_name === 'net_income').reverse())

const editingThesis = ref(false); const thesisText = ref(''); const thesisDecision = ref('watch'); const thesisConfidence = ref(0.6)
const editingCompany = ref(false); const editName = ref(''); const editSector = ref(''); const editIndustry = ref(''); const editDesc = ref(''); const editTags = ref('')
const ingesting = ref(false); const showDeleteConfirm = ref(false); const deleting = ref(false)
const currentThesis = computed(() => workspace.value?.thesis || null)
const evidenceCounts = computed(() => workspace.value?.evidence_summary || { supporting: 0, opposing: 0, neutral: 0 })
const relatedSessions = computed(() => sessions.value?.filter((s: any) => s.company_id === id) || [])
const relatedDocs = computed(() => docsData.value?.items?.filter((d: any) => d.company_id === id) || [])

async function handleRefreshData() {
  if (!company.value?.ticker || ingesting.value) return
  ingesting.value = true
  try {
    await ingestPrices.mutateAsync(company.value.ticker)
    ingestFinancials.mutate(company.value.ticker)
    ingestProfile.mutate(company.value.ticker)
    ElMessage.success('数据已刷新')
  } catch (e: any) { ElMessage.error(e.message || '刷新失败') } finally { ingesting.value = false }
}

async function handleDeleteCompany() {
  if (!id || deleting.value) return; deleting.value = true
  try { await deleteCompany.mutateAsync(id); router.push('/companies') } catch (e: any) { ElMessage.error(e.message || '删除失败'); deleting.value = false; showDeleteConfirm.value = false }
}

async function handleSaveThesis() {
  if (!thesisText.value.trim() || !company.value) return
  await updateThesis.mutateAsync({ ticker: company.value.ticker, thesis: thesisText.value.trim(), decision: thesisDecision.value, confidence: thesisConfidence.value })
  editingThesis.value = false
}

async function handleSaveCompany() {
  try {
    await updateCompany.mutateAsync({
      name: editName.value,
      sector: editSector.value || null,
      industry: editIndustry.value || null,
      description: editDesc.value || null,
      tags: editTags.value.split(',').map((t) => t.trim()).filter(Boolean),
    })
    editingCompany.value = false
    ElMessage.success('公司信息已更新')
  } catch (e: any) { ElMessage.error(e.message || '更新失败') }
}

</script>

<template>
  <div v-if="isLoading" class="loading-state">加载中...</div>
  <div v-else-if="!company" class="loading-state" style="color:var(--danger)">公司未找到</div>
  <div v-else class="page">
    <div><el-button text @click="router.push('/companies')">← 公司列表</el-button>
      <div class="flex items-center gap-4 mt-3">
        <div><h1 style="font-size:30px;font-weight:700;color:var(--text-primary)">{{ company.ticker }}</h1><p class="text-lg text-secondary mt-0.5">{{ company.name }}</p></div>
        <div class="ml-auto flex items-center gap-2">
          <el-tag v-if="currentThesis?.thesis" type="primary" size="small" effect="plain">有观点</el-tag>
          <el-button @click="editName=company.name; editSector=company.sector||''; editIndustry=company.industry||''; editDesc=company.description||''; editTags=company.tags.map((t:any)=>t.tag).join(', '); editingCompany=true">编辑</el-button>
          <el-button @click="showDeleteConfirm=true" style="background:var(--danger);color:#fff">🗑 删除</el-button>
          <el-button @click="router.push(`/research/quick?ticker=${company.ticker}`)" type="primary">⚡ 快速研究</el-button>
        </div>
      </div>
    </div>

    <div class="flex gap-1.5 flex-wrap"><el-tag v-for="t in company.tags" :key="t.id" size="small">{{ t.tag }}</el-tag></div>
    <div v-if="currentThesis?.thesis && !editingThesis" class="thesis-bar">
      <div class="flex-1 min-w-0"><div class="text-xs text-secondary mb-1">当前观点</div><p class="text-sm line-clamp-2" style="color:var(--text-primary)">{{ currentThesis.thesis }}</p></div>
      <div class="flex items-center gap-3 ml-4 shrink-0">
        <el-tag v-if="currentThesis.decision" :type="currentThesis.decision==='buy'?'success':currentThesis.decision==='sell'?'danger':'warning'" size="small" effect="dark">{{ currentThesis.decision.toUpperCase() }}</el-tag>
        <span v-if="currentThesis.confidence!=null" class="text-xs text-secondary">{{ Math.round(currentThesis.confidence*100) }}%</span>
        <el-button text size="small" @click="thesisText=currentThesis.thesis||''; thesisDecision=currentThesis.decision||'watch'; thesisConfidence=currentThesis.confidence||0.6; editingThesis=true">编辑</el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="概览" name="概览">
        <div class="space-y-6">
          <el-row :gutter="12">
            <el-col v-for="s in [{label:'行业板块',value:company.sector},{label:'细分行业',value:company.industry},{label:'总部',value:company.headquarters},{label:'网站',value:company.website||'—'}]" :key="s.label" :span="6">
              <el-card shadow="never"><div class="text-xs text-secondary mb-1">{{ s.label }}</div><div class="font-medium truncate">{{ s.value||'—' }}</div></el-card>
            </el-col>
          </el-row>
          <el-card v-if="company.description" shadow="never"><template #header>公司简介</template><p class="text-sm leading-relaxed">{{ company.description }}</p></el-card>
          <el-card v-if="evidenceCounts.supporting>0||evidenceCounts.opposing>0" shadow="never">
            <template #header>证据总览</template>
            <div class="flex gap-4 text-sm"><span style="color:var(--success)">✅ {{ evidenceCounts.supporting }} 支持</span><span style="color:var(--danger)">⚠️ {{ evidenceCounts.opposing }} 反对</span><span class="text-secondary">📊 {{ evidenceCounts.neutral }} 中性</span></div>
          </el-card>
        </div>
      </el-tab-pane>

      <el-tab-pane label="投资观点" name="投资观点">
        <div class="space-y-6">
          <el-card shadow="never">
            <template #header>🎯 当前观点</template>
            <div v-if="editingThesis" class="space-y-3">
              <el-input v-model="thesisText" type="textarea" :rows="4" placeholder="输入投资观点..." />
              <div class="flex gap-3"><el-select v-model="thesisDecision" style="width:120px"><el-option value="buy" label="买入"/><el-option value="sell" label="卖出"/><el-option value="hold" label="持有"/><el-option value="watch" label="关注"/><el-option value="pass" label="跳过"/></el-select><div class="flex items-center gap-2"><span class="text-sm text-secondary">置信度:</span><el-slider v-model="thesisConfidence" :min="0" :max="1" :step="0.01" style="width:120px"/><span class="text-sm" style="width:32px">{{ Math.round(thesisConfidence*100) }}%</span></div></div>
              <div class="flex gap-2"><el-button @click="handleSaveThesis" :disabled="!thesisText.trim()||updateThesis.isPending.value" type="success">{{ updateThesis.isPending.value?'保存中...':'保存观点' }}</el-button><el-button @click="editingThesis=false">取消</el-button></div>
            </div>
            <div v-else-if="currentThesis?.thesis">
              <p class="leading-relaxed">{{ currentThesis.thesis }}</p>
              <div class="flex items-center gap-3 mt-3">
                <el-tag v-if="currentThesis.decision" :type="currentThesis.decision==='buy'?'success':currentThesis.decision==='sell'?'danger':'warning'" size="small" effect="dark">{{ currentThesis.decision.toUpperCase() }}</el-tag>
                <span v-if="currentThesis.confidence!=null" class="text-sm text-secondary">置信度: {{ Math.round(currentThesis.confidence*100) }}%</span>
                <span v-if="currentThesis.updated_at" class="text-xs text-secondary">更新于 {{ new Date(currentThesis.updated_at).toLocaleDateString('zh-CN') }}</span>
                <el-button text size="small" class="ml-auto" @click="thesisText=currentThesis.thesis||''; thesisDecision=currentThesis.decision||'watch'; thesisConfidence=currentThesis.confidence||0.6; editingThesis=true">编辑</el-button>
              </div>
              <div v-if="currentThesis.structured_thesis" class="grid grid-cols-2 gap-3 mt-4">
                <div v-if="currentThesis.structured_thesis.bull_case?.length" class="thesis-block" style="background:rgba(52,211,153,0.05);border:1px solid rgba(52,211,153,0.2)"><div style="color:var(--success);font-size:12px;font-weight:600;margin-bottom:6px">📈 看多逻辑</div><ul><li v-for="(item,i) in currentThesis.structured_thesis.bull_case" :key="i" style="font-size:12px;color:var(--text-primary);padding:2px 0">• {{ item }}</li></ul></div>
                <div v-if="currentThesis.structured_thesis.bear_case?.length" class="thesis-block" style="background:rgba(248,113,113,0.05);border:1px solid rgba(248,113,113,0.2)"><div style="color:var(--danger);font-size:12px;font-weight:600;margin-bottom:6px">📉 看空逻辑</div><ul><li v-for="(item,i) in currentThesis.structured_thesis.bear_case" :key="i" style="font-size:12px;color:var(--text-primary);padding:2px 0">• {{ item }}</li></ul></div>
                <div v-if="currentThesis.structured_thesis.key_drivers?.length" class="thesis-block" style="background:rgba(79,140,255,0.05);border:1px solid rgba(79,140,255,0.2)"><div style="color:var(--accent);font-size:12px;font-weight:600;margin-bottom:6px">🎯 关键驱动</div><ul><li v-for="(item,i) in currentThesis.structured_thesis.key_drivers" :key="i" style="font-size:12px;color:var(--text-primary);padding:2px 0">• {{ item }}</li></ul></div>
                <div v-if="currentThesis.structured_thesis.risks?.length" class="thesis-block" style="background:rgba(251,191,36,0.05);border:1px solid rgba(251,191,36,0.2)"><div style="color:var(--warning);font-size:12px;font-weight:600;margin-bottom:6px">⚠️ 风险因素</div><ul><li v-for="(item,i) in currentThesis.structured_thesis.risks" :key="i" style="font-size:12px;color:var(--text-primary);padding:2px 0">• {{ item }}</li></ul></div>
              </div>
            </div>
            <div v-else class="text-center py-6"><p class="text-sm text-secondary mb-3">还没有投资观点</p><el-button @click="thesisText=''; editingThesis=true" type="primary">✏️ 创建观点</el-button></div>
          </el-card>
          <el-card v-if="evidenceCounts.supporting>0||evidenceCounts.opposing>0" shadow="never">
            <template #header>📊 证据统计</template>
            <el-row :gutter="16"><el-col :span="8"><div class="evidence-stat" style="background:rgba(52,211,153,0.05);border:1px solid rgba(52,211,153,0.2)"><div class="evidence-count" style="color:var(--success)">{{ evidenceCounts.supporting }}</div><div class="text-xs text-secondary mt-1">支持</div></div></el-col><el-col :span="8"><div class="evidence-stat" style="background:rgba(248,113,113,0.05);border:1px solid rgba(248,113,113,0.2)"><div class="evidence-count" style="color:var(--danger)">{{ evidenceCounts.opposing }}</div><div class="text-xs text-secondary mt-1">反对</div></div></el-col><el-col :span="8"><div class="evidence-stat" style="background:rgba(154,160,166,0.05);border:1px solid var(--border)"><div class="evidence-count" style="color:var(--text-secondary)">{{ evidenceCounts.neutral }}</div><div class="text-xs text-secondary mt-1">中性</div></div></el-col></el-row>
          </el-card>
          <el-card v-if="workspace?.recent_research?.length" shadow="never">
            <template #header>📋 近期研究</template>
            <div v-for="s in workspace.recent_research" :key="s.id" class="research-item" @click="router.push(`/research/${s.id}`)">
              <div><div class="text-sm">{{ s.title }}</div><div class="text-xs text-secondary mt-0.5">{{ s.created_at?new Date(s.created_at).toLocaleDateString('zh-CN'):'' }}</div></div>
              <div class="flex items-center gap-2"><el-tag v-if="s.decision" size="small" type="success">{{ s.decision.toUpperCase() }}</el-tag><span class="text-xs text-secondary">{{ s.status }}</span></div>
            </div>
          </el-card>
        </div>
      </el-tab-pane>

      <el-tab-pane label="财务数据" name="财务数据">
        <div class="space-y-6">
          <div class="flex items-center justify-between"><span class="text-sm text-secondary">akshare 行情（MySQL→本地→云端）</span><el-button @click="handleRefreshData" :disabled="ingesting" size="small">{{ ingesting?'↻ 刷新中...':'↻ 刷新' }}</el-button></div>
          <StockChart :prices="prices" :height="350" />
          <el-row :gutter="16">
            <el-col v-if="revenueData.length" :span="12">
              <el-card shadow="never"><template #header>营收趋势</template>
                <FinancialBars :data="revenueData" color="#4f8cff" />
              </el-card>
            </el-col>
            <el-col v-if="incomeData.length" :span="12">
              <el-card shadow="never"><template #header>净利润趋势</template>
                <FinancialBars :data="incomeData" color="#34d399" />
              </el-card>
            </el-col>
          </el-row>
        </div>
      </el-tab-pane>

      <el-tab-pane label="研究" name="研究">
        <div class="space-y-4">
          <div class="flex items-center justify-between"><span class="text-sm text-secondary">研究会话列表</span><el-button @click="router.push(`/research/quick?ticker=${company.ticker}`)" type="primary" size="small">+ 新建研究会话</el-button></div>
          <div v-if="!relatedSessions.length" class="empty-card"><div class="text-3xl mb-3">🔬</div><div class="font-medium">暂无研究</div><div class="text-sm text-secondary mt-1">点击上方 "新建研究会话" 开始研究</div></div>
          <div v-else v-for="s in relatedSessions" :key="s.id" class="session-card" @click="router.push(`/research/${s.id}`)">
            <div><div class="font-medium text-primary">{{ s.title }}</div><div class="text-sm text-secondary mt-1 line-clamp-1">{{ s.question }}</div></div>
            <div class="flex items-center gap-2 ml-3"><el-tag v-if="s.decision" :type="s.decision==='buy'?'success':s.decision==='sell'?'danger':'warning'" size="small" effect="dark">{{ s.decision.toUpperCase() }}</el-tag><el-tag size="small">{{ s.status }}</el-tag></div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="文档" name="文档">
        <div class="space-y-4">
          <div class="flex items-center justify-between"><span class="text-sm text-secondary">已上传文档</span><el-button @click="router.push('/documents')" type="primary" size="small">+ 上传文档</el-button></div>
          <div v-if="!relatedDocs.length" class="empty-card"><div class="text-3xl mb-3">📄</div><div class="font-medium">暂无关联文档</div><div class="text-sm text-secondary mt-1">上传相关财报或研究报告，上传后会自动索引到知识库</div></div>
          <div v-else v-for="doc in relatedDocs" :key="doc.id" class="doc-card"><div class="font-medium">{{ doc.title }}</div><div class="flex gap-3 text-xs text-secondary mt-1"><span>{{ doc.doc_type?.toUpperCase() }}</span><span :class="doc.is_indexed?'text-success':'text-warning'">{{ doc.is_indexed?'✅ 已索引':'⏳ 未索引' }}</span><span v-if="doc.chunk_count!=null">{{ doc.chunk_count }} 切片</span></div></div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="editingCompany" title="编辑公司" width="500px">
      <div class="space-y-3"><el-input v-model="editName" placeholder="公司名称"/><el-input v-model="editSector" placeholder="行业板块"/><el-input v-model="editIndustry" placeholder="细分行业"/><el-input v-model="editDesc" placeholder="公司简介" type="textarea" :rows="3"/><el-input v-model="editTags" placeholder="标签(逗号分隔)"/></div>
      <template #footer><el-button @click="editingCompany=false">取消</el-button><el-button @click="handleSaveCompany" type="success">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="showDeleteConfirm" title="确认删除" width="400px">
      <p class="text-sm text-secondary">确定要删除 <span class="font-medium text-primary">{{ company.ticker }} {{ company.name }}</span> 吗？关联的研究和行情数据不会被删除。</p>
      <template #footer><el-button @click="showDeleteConfirm=false" :disabled="deleting">取消</el-button><el-button @click="handleDeleteCompany" :disabled="deleting" type="danger">{{ deleting?'删除中...':'确认删除' }}</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.loading-state { text-align: center; padding: 48px 0; color: var(--text-secondary); font-size: 16px; }
.page { max-width: 1000px; margin: 0 auto; display: flex; flex-direction: column; gap: 20px; }
.thesis-bar { display: flex; align-items: center; padding: 16px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); border-left: 4px solid var(--accent); }
.thesis-block { padding: 12px; border-radius: 8px; }
.evidence-stat { padding: 16px; border-radius: 8px; text-align: center; }
.evidence-count { font-size: 24px; font-weight: 700; }
.research-item { display: flex; align-items: center; justify-content: space-between; padding: 12px; border-radius: 8px; background: var(--bg-tertiary); cursor: pointer; margin-bottom: 8px; }
.research-item:hover { background: var(--border); }
.empty-card { padding: 32px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); text-align: center; }
.session-card { display: flex; align-items: center; justify-content: space-between; padding: 20px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); cursor: pointer; margin-bottom: 12px; }
.session-card:hover { border-color: rgba(79,140,255,0.3); }
.doc-card { padding: 16px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); margin-bottom: 8px; }
.text-success { color: var(--success); }
.text-warning { color: var(--warning); }
</style>
