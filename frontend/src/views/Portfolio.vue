<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useAddHolding,
  useAddWatchlistItem,
  useCompanies,
  useHoldings,
  useRemoveWatchlistItem,
  useWatchlists,
} from '@/stores/api'
import StockSearch from '@/components/StockSearch.vue'

const { data: watchlists, isLoading: wlLoading } = useWatchlists()
const { data: holdings, isLoading: hdLoading } = useHoldings()
const { data: companiesData } = useCompanies()

const addHolding = useAddHolding()
const removeWatchlistItem = useRemoveWatchlistItem()
const activeWL = computed(() => (Array.isArray(watchlists.value) ? watchlists.value.find((w: any) => w.items?.length > 0) || watchlists.value[0] : null) as any)
const addWatchlistItem = useAddWatchlistItem(computed(() => activeWL.value?.id || ''))

// Company names for watchlist tickers — one query instead of N name lookups.
const names = computed<Record<string, string>>(() => {
  const m: Record<string, string> = {}
  for (const c of companiesData.value?.items || []) m[c.ticker.toUpperCase()] = c.name
  return m
})

const showNewHD = ref(false)
const hdTicker = ref('')
const hdShares = ref('')
const hdCost = ref('')
const adding = ref(false)

async function handleCreateHolding() {
  if (!hdTicker.value.trim() || !hdShares.value) return
  try {
    const ticker = hdTicker.value.toUpperCase()
    await addHolding.mutateAsync({
      ticker,
      shares: parseFloat(hdShares.value),
      avg_cost_basis: hdCost.value ? parseFloat(hdCost.value) : null,
    })
    showNewHD.value = false; hdTicker.value = ''; hdShares.value = ''; hdCost.value = ''
    ElMessage.success(`持仓 ${ticker} 添加成功`)
  } catch (e: any) { ElMessage.error(e.message || '添加失败') }
}

async function onStockSelect(item: { symbol: string; name: string }) {
  if (!activeWL.value) return
  try {
    await addWatchlistItem.mutateAsync({ ticker: item.symbol })
    adding.value = false
    ElMessage.success(`${item.symbol} 已添加`)
  } catch (e: any) { ElMessage.error(e.message || '添加失败') }
}

async function handleRemove(itemId: string, ticker: string) {
  try {
    await removeWatchlistItem.mutateAsync(itemId)
    ElMessage.success(`${ticker} 已移除`)
  } catch (e: any) { ElMessage.error(e.message || '移除失败') }
}
</script>

<template>
  <div class="page">
    <div class="page-header"><h1 class="page-title">💼 投资组合</h1><p class="page-desc">自选列表 · 持仓</p></div>

    <el-row :gutter="24">
      <el-col :span="12">
        <h2 class="section-title">自选列表</h2>
        <div v-if="wlLoading" class="loading-state">加载中...</div>
        <div v-else-if="activeWL" class="wl-card">
          <div class="wl-header"><span class="text-xs text-secondary">{{ activeWL.items?.length || 0 }} 只关注股票</span><el-button @click="adding = !adding" type="primary" size="small">{{ adding ? '取消' : '+ 添加股票' }}</el-button></div>
          <div v-show="adding" class="wl-search">
            <StockSearch size="small" @select="onStockSelect" />
          </div>
          <template v-if="activeWL.items?.length">
            <div class="wl-items">
              <div v-for="item in activeWL.items" :key="item.id" class="wl-item">
                <div><span class="wl-ticker">{{ item.ticker }}</span><span v-if="names[item.ticker]" class="wl-name">{{ names[item.ticker] }}</span></div>
                <el-button text size="small" @click="handleRemove(item.id, item.ticker)" style="color:var(--danger)">✕ 移除</el-button>
              </div>
            </div>
          </template>
          <div v-else class="wl-empty">点击「添加股票」开始关注</div>
        </div>
        <el-empty v-else description="暂无自选列表" />
      </el-col>
      <el-col :span="12">
        <div class="flex items-center justify-between mb-3"><h2 class="section-title" style="margin-bottom:0">持仓</h2><el-button @click="showNewHD = !showNewHD" type="primary" size="small">{{ showNewHD ? '取消' : '+ 添加' }}</el-button></div>
        <div v-if="showNewHD" class="new-form">
          <el-input v-model="hdTicker" placeholder="股票代码" size="small" />
          <el-input v-model="hdShares" placeholder="持股数量" type="number" size="small" />
          <el-input v-model="hdCost" placeholder="平均成本（可选）" type="number" size="small" />
          <el-button @click="handleCreateHolding" :disabled="!hdTicker.trim() || !hdShares" type="success" size="small">添加</el-button>
        </div>
        <div v-if="hdLoading" class="loading-state">加载中...</div>
        <div v-else-if="!holdings || !holdings.length" class="empty-state-sm">暂无持仓</div>
        <div v-else class="space-y-3">
          <div v-for="h in holdings" :key="h.id" class="holding-item">
            <div><span class="holding-ticker">{{ h.ticker }}</span><span class="holding-shares">{{ h.shares }} 股</span></div>
            <div v-if="h.avg_cost_basis" class="holding-cost">成本: ¥{{ h.avg_cost_basis.toFixed(2) }}</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <div><h2 class="section-title">研究日志</h2><el-empty description="日志将显示在此处。通过研究流程自动记录。" /></div>
  </div>
</template>

<style scoped>
.page { max-width: 1000px; margin: 0 auto; display: flex; flex-direction: column; gap: 24px; }
.section-title { font-size: 18px; font-weight: 600; color: var(--text-primary); margin-bottom: 12px; }
.loading-state { padding: 24px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); text-align: center; color: var(--text-secondary); font-size: 14px; }
.empty-state-sm { padding: 24px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); text-align: center; color: var(--text-secondary); }
.new-form { padding: 16px; border-radius: 12px; background: var(--bg-tertiary); border: 1px solid var(--border); display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.holding-item { padding: 16px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); }
.holding-ticker { font-size: 18px; font-weight: 700; color: var(--text-primary); margin-right: 8px; }
.holding-shares { font-size: 14px; color: var(--text-secondary); }
.holding-cost { font-size: 14px; color: var(--text-secondary); margin-top: 4px; }
.wl-card { padding: 16px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); }
.wl-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.wl-items { display: flex; flex-direction: column; gap: 6px; }
.wl-item { display: flex; align-items: center; justify-content: space-between; padding: 8px; border-radius: 6px; background: var(--bg-tertiary); }
.wl-item:hover .wl-item button { opacity: 1; }
.wl-ticker { font-size: 14px; color: var(--text-primary); font-family: monospace; }
.wl-name { font-size: 12px; color: var(--text-secondary); margin-left: 8px; }
.wl-empty { text-align: center; padding: 8px; font-size: 14px; color: var(--text-secondary); }
</style>
