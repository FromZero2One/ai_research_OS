<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useCompanies, useUpdateCompany, useWatchCompany } from '@/stores/api'
import StockSearch from '@/components/StockSearch.vue'

const { data: watchedData, isLoading } = useCompanies(undefined, { active: true })
const watchCompany = useWatchCompany()
const targetCompanyId = ref<string | null>(null)
const updateCompany = useUpdateCompany(targetCompanyId)

const watched = computed(() => watchedData.value?.items || [])
const adding = ref(false)

async function onStockSelect(item: { symbol: string; name: string }) {
  try {
    await watchCompany.mutateAsync({ ticker: item.symbol, name: item.name })
    adding.value = false
    ElMessage.success(`${item.symbol} 已加入自选`)
  } catch (e: any) { ElMessage.error(e.message || '添加失败') }
}

async function handleRemove(companyId: string, ticker: string) {
  try {
    targetCompanyId.value = companyId
    await updateCompany.mutateAsync({ is_active: false })
    ElMessage.success(`${ticker} 已移除`)
  } catch (e: any) { ElMessage.error(e.message || '移除失败') }
}
</script>

<template>
  <div class="page">
    <div class="page-header"><h1 class="page-title">💼 自选列表</h1><p class="page-desc">关注的公司 — 晨报、观察与研究提醒的底座</p></div>

    <div v-if="isLoading" class="loading-state">加载中...</div>
    <div v-else class="wl-card">
      <div class="wl-header"><span class="text-xs text-secondary">{{ watched.length }} 只关注股票</span><el-button @click="adding = !adding" type="primary" size="small">{{ adding ? '取消' : '+ 添加股票' }}</el-button></div>
      <div v-show="adding" class="wl-search">
        <StockSearch size="small" @select="onStockSelect" />
      </div>
      <template v-if="watched.length">
        <div class="wl-items">
          <div v-for="c in watched" :key="c.id" class="wl-item">
            <div><span class="wl-ticker">{{ c.ticker }}</span><span class="wl-name">{{ c.name }}</span><span v-if="c.priority" class="wl-priority">P{{ c.priority }}</span></div>
            <el-button text size="small" @click="handleRemove(c.id, c.ticker)" style="color:var(--danger)">✕ 移除</el-button>
          </div>
        </div>
      </template>
      <div v-else class="wl-empty">点击「添加股票」开始关注</div>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 800px; margin: 0 auto; display: flex; flex-direction: column; gap: 24px; }
.loading-state { padding: 24px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); text-align: center; color: var(--text-secondary); font-size: 14px; }
.wl-card { padding: 16px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); }
.wl-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.wl-items { display: flex; flex-direction: column; gap: 6px; }
.wl-item { display: flex; align-items: center; justify-content: space-between; padding: 8px; border-radius: 6px; background: var(--bg-tertiary); }
.wl-ticker { font-size: 14px; color: var(--text-primary); font-family: monospace; }
.wl-name { font-size: 12px; color: var(--text-secondary); margin-left: 8px; }
.wl-priority { font-size: 11px; color: var(--accent); margin-left: 8px; }
.wl-empty { text-align: center; padding: 8px; font-size: 14px; color: var(--text-secondary); }
</style>
