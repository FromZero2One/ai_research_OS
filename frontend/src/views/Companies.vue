<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import {
  useCompanies,
  useCreateCompany,
  useDeleteCompany,
  useIngestFinancials,
  useIngestProfile,
  useUpdateCompany,
} from '@/stores/api'
import StockSearch from '@/components/StockSearch.vue'

const router = useRouter()
const query = ref('')
const { data, isLoading } = useCompanies(query)

const createCompany = useCreateCompany()
const deleteCompany = useDeleteCompany()
const ingestProfile = useIngestProfile()
const ingestFinancials = useIngestFinancials()

const showNew = ref(false)
const newName = ref('')
const newTicker = ref('')
const newExchange = ref('')
const newTags = ref('')
const editingId = ref<string | null>(null)
const editName = ref('')
const editTicker = ref('')
const editSector = ref('')
const editTags = ref('')
const deletingId = ref<string | null>(null)
const deleteDialogVisible = computed({ get: () => deletingId.value !== null, set: (v: boolean) => { if (!v) deletingId.value = null } })
const updateCompany = useUpdateCompany(editingId)

function onStockSelect(item: { symbol: string; name: string }) {
  newTicker.value = item.symbol; newName.value = item.name
  if (item.symbol.startsWith('6')) newExchange.value = 'SSE'
  else if (item.symbol.match(/^\d/)) newExchange.value = 'SZSE'
  else if (item.symbol.match(/^0\d{4}HK/)) newExchange.value = 'HKEX'
  else newExchange.value = ''
}

async function handleCreate() {
  if (!newName.value.trim() || !newTicker.value.trim()) return
  try {
    const ticker = newTicker.value.toUpperCase()
    const name = newName.value.trim()
    await createCompany.mutateAsync({
      name,
      ticker,
      exchange: newExchange.value,
      tags: newTags.value.split(',').map((t) => t.trim()).filter(Boolean),
    })
    showNew.value = false; newName.value = ''; newTicker.value = ''; newExchange.value = ''; newTags.value = ''
    // Fire-and-forget enrichment (profile + financials).
    ingestProfile.mutate(ticker)
    ingestFinancials.mutate(ticker)
    ElMessage.success(`${name} 创建成功`)
  } catch (e: any) {
    ElMessage.error((e.message || '').includes('already exists') ? `股票代码 ${newTicker.value.toUpperCase()} 已存在` : e.message || '创建失败')
  }
}

function startEdit(company: any) {
  editingId.value = company.id; editName.value = company.name || ''; editTicker.value = company.ticker || ''; editSector.value = company.sector || ''; editTags.value = (company.tags || []).map((t: any) => t.tag).join(', ')
}

async function handleEdit() {
  if (!editingId.value) return
  try {
    await updateCompany.mutateAsync({
      name: editName.value,
      ticker: editTicker.value.toUpperCase(),
      sector: editSector.value,
      tags: editTags.value.split(',').map((t) => t.trim()).filter(Boolean),
    })
    editingId.value = null
    ElMessage.success('更新成功')
  } catch (e: any) { ElMessage.error(e.message || '更新失败') }
}

async function handleDelete(id: string) {
  try { await deleteCompany.mutateAsync(id); deletingId.value = null; ElMessage.success('已删除') } catch (e: any) { ElMessage.error(e.message || '删除失败') }
}
</script>

<template>
  <div class="page">
    <div class="flex items-center justify-between">
      <div><h1 class="page-title">🏢 公司中心</h1><p class="page-desc">公司档案、行业分类与研究对象</p></div>
      <el-button @click="showNew = !showNew" type="primary" size="small">{{ showNew ? '取消' : '+ 新建' }}</el-button>
    </div>

    <div v-if="showNew" class="new-form">
      <StockSearch @select="onStockSelect" />
      <div v-if="newTicker" class="selected-stock"><span class="stock-code">{{ newTicker }}</span><span>{{ newName }}</span><el-button text size="small" @click="newTicker = ''; newName = ''" style="color:var(--danger);margin-left:auto">✕</el-button></div>
      <el-row :gutter="12">
        <el-col :span="12"><el-select v-model="newExchange" placeholder="选择交易所" style="width:100%"><el-option value="" label="交易所" disabled /><el-option value="SSE" label="SSE 上交所" /><el-option value="SZSE" label="SZSE 深交所" /><el-option value="NASDAQ" label="NASDAQ 纳斯达克" /><el-option value="NYSE" label="NYSE 纽交所" /><el-option value="HKEX" label="HKEX 港交所" /></el-select></el-col>
        <el-col :span="12"><el-input v-model="newTags" placeholder="标签(逗号分隔)" /></el-col>
      </el-row>
      <div class="flex gap-2"><el-button @click="handleCreate" :disabled="!newName.trim() || !newTicker.trim()" type="success" size="small">创建</el-button><el-button @click="showNew = false; newTicker = ''; newName = ''" size="small">取消</el-button></div>
    </div>

    <el-input v-model="query" placeholder="搜索公司名称或股票代码..." clearable :prefix-icon="Search" />

    <div v-if="isLoading" class="loading-state">加载中...</div>
    <div v-else class="company-grid">
      <div v-for="company in data?.items" :key="company.id" class="company-card">
        <div v-if="editingId === company.id" class="edit-form" @click.stop>
          <el-input v-model="editName" placeholder="名称" size="small" />
          <el-input v-model="editTicker" placeholder="代码" size="small" />
          <el-input v-model="editSector" placeholder="行业" size="small" />
          <el-input v-model="editTags" placeholder="标签(逗号分隔)" size="small" />
          <div class="flex gap-2"><el-button @click="handleEdit" type="primary" size="small">保存</el-button><el-button @click="editingId = null" size="small">取消</el-button></div>
        </div>
        <template v-else>
          <div class="company-actions">
            <el-button text size="small" @click="startEdit(company)">✎ 编辑</el-button>
            <el-button text size="small" @click="deletingId = company.id" style="color:var(--danger)">🗑 删除</el-button>
          </div>
          <div class="company-main" @click="router.push(`/companies/${company.id}`)">
            <div><span class="company-ticker">{{ company.ticker }}</span><span class="company-name">{{ company.name }}</span></div>
            <div v-if="company.sector" class="company-sector">{{ company.sector }}{{ company.industry ? ` · ${company.industry}` : '' }}</div>
            <div class="company-tags"><el-tag v-for="t in company.tags" :key="t.id" size="small">{{ t.tag }}</el-tag></div>
          </div>
        </template>
      </div>
    </div>

    <el-dialog v-model="deleteDialogVisible" title="确认删除" width="400px">
      <p class="text-sm text-secondary">删除后不可恢复，确定要删除这家公司吗？</p>
      <template #footer>
        <el-button @click="deletingId = null">取消</el-button>
        <el-button @click="handleDelete(deletingId!)" type="danger">确认删除</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page { max-width: 1000px; margin: 0 auto; display: flex; flex-direction: column; gap: 20px; }
.new-form { padding: 20px; border-radius: 12px; background: var(--bg-tertiary); border: 1px solid var(--border); display: flex; flex-direction: column; gap: 12px; }
.selected-stock { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 6px; background: var(--bg-secondary); font-size: 14px; }
.selected-stock .stock-code { font-family: monospace; color: var(--accent); }
.loading-state { text-align: center; padding: 48px 0; color: var(--text-secondary); }
.company-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.company-card { padding: 20px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); position: relative; }
.company-actions { position: absolute; top: 12px; right: 12px; display: flex; gap: 4px; opacity: 0; transition: opacity 0.2s; }
.company-card:hover .company-actions { opacity: 1; }
.company-main { cursor: pointer; }
.company-ticker { font-size: 18px; font-weight: 700; color: var(--text-primary); }
.company-name { font-size: 14px; color: var(--text-secondary); margin-left: 8px; }
.company-sector { font-size: 14px; color: var(--text-secondary); margin-top: 8px; }
.company-tags { display: flex; gap: 6px; margin-top: 12px; flex-wrap: wrap; }
.edit-form { display: flex; flex-direction: column; gap: 8px; }
</style>
