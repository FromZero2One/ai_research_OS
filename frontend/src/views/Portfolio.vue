<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { useWatchlists, useHoldings, useStockSearch } from '@/stores/api'

const queryClient = useQueryClient()
const { data: watchlists, isLoading: wlLoading } = useWatchlists()
const refresh = () => queryClient.invalidateQueries({ queryKey: [] })
const { data: holdings, isLoading: hdLoading } = useHoldings()

const showNewHD = ref(false)
const hdTicker = ref('')
const hdShares = ref('')
const hdCost = ref('')
const msg = ref<{ type: 'success' | 'error'; text: string } | null>(null)

function showMsg(type: 'success' | 'error', text: string) { msg.value = { type, text }; setTimeout(() => msg.value = null, 4000) }

const activeWL = computed(() => (Array.isArray(watchlists.value) ? watchlists.value.find((w: any) => w.items?.length > 0) || watchlists.value[0] : null) as any)

async function handleCreateHolding() {
  if (!hdTicker.value.trim() || !hdShares.value) return
  try {
    const resp = await fetch('/api/portfolio/holdings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ticker: hdTicker.value.toUpperCase(), shares: parseFloat(hdShares.value), avg_cost_basis: hdCost.value ? parseFloat(hdCost.value) : null }) })
    if (!resp.ok) throw new Error(await resp.text())
    showNewHD.value = false; hdTicker.value = ''; hdShares.value = ''; hdCost.value = ''
    showMsg('success', `持仓 ${hdTicker.value.toUpperCase()} 添加成功`)
  } catch (e: any) { showMsg('error', e.message || '添加失败') }
}

// WatchlistCard component
const adding = ref(false)
const searchQ = ref('')
const showDrop = ref(false)
const names = ref<Record<string, string>>({})
const searchRef = ref<HTMLDivElement | null>(null)
const { data: searchData } = useStockSearch(searchQ)
const searchResults = computed(() => searchData.value?.results || [])

function onClick(e: MouseEvent) { if (searchRef.value && !searchRef.value.contains(e.target as Node)) showDrop.value = false }
onMounted(() => document.addEventListener('mousedown', onClick))
onUnmounted(() => document.removeEventListener('mousedown', onClick))

watch(activeWL, async (wl: any) => {
  if (!wl?.items?.length) return
  const tickers = wl.items.map((i: any) => i.ticker).filter((t: string) => !names.value[t])
  if (!tickers.length) return
  for (const t of tickers) {
    try { const resp = await fetch(`/api/market/search?query=${encodeURIComponent(t)}&limit=3`); const data = await resp.json(); const match = data.results?.find((r: any) => r.symbol.toUpperCase() === t.toUpperCase()); if (match?.name) names.value = { ...names.value, [t]: match.name } } catch {}
  }
}, { immediate: true })

async function handleSelect(symbol: string) {
  const wl = activeWL.value
  if (!wl) return
  try { const resp = await fetch(`/api/portfolio/watchlists/${wl.id}/items`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ticker: symbol }) }); if (!resp.ok) throw new Error(await resp.text()); searchQ.value = ''; showDrop.value = false; adding.value = false; refresh(); showMsg('success', `${symbol} 已添加`) } catch (e: any) { showMsg('error', e.message || '添加失败') }
}

async function handleRemove(itemId: string, ticker: string) {
  try { const resp = await fetch(`/api/portfolio/watchlists/items/${itemId}`, { method: 'DELETE' }); if (!resp.ok) throw new Error(await resp.text()); refresh(); showMsg('success', `${ticker} 已移除`) } catch (e: any) { showMsg('error', e.message || '移除失败') }
}
</script>

<template>
  <div class="page">
    <div class="page-header"><h1 class="page-title">💼 投资组合</h1><p class="page-desc">自选列表 · 持仓</p></div>

    <div v-if="msg" class="msg-toast" :class="msg.type === 'success' ? 'msg-success' : 'msg-error'">{{ msg.text }}</div>

    <el-row :gutter="24">
      <el-col :span="12">
        <h2 class="section-title">自选列表</h2>
        <div v-if="wlLoading" class="loading-state">加载中...</div>
        <div v-else-if="activeWL" class="wl-card">
          <div class="wl-header"><span class="text-xs text-secondary">{{ activeWL.items?.length || 0 }} 只关注股票</span><el-button @click="adding = !adding" type="primary" size="small">{{ adding ? '取消' : '+ 添加股票' }}</el-button></div>
          <div v-if="adding" ref="searchRef" class="wl-search">
            <el-input v-model="searchQ" placeholder="搜索股票代码或名称..." size="small" @focus="showDrop = true" @input="showDrop = true" />
            <div v-if="showDrop && searchQ" class="search-dropdown">
              <div v-if="!searchResults.length" class="search-empty">无匹配结果</div>
              <button v-for="r in searchResults" :key="r.symbol" class="search-item" @click="handleSelect(r.symbol)">
                <span class="search-symbol">{{ r.symbol }}</span>
                <span v-if="r.name" class="search-name">{{ r.name }}</span>
              </button>
            </div>
          </div>
          <div v-if="activeWL.items?.length" class="wl-items">
            <div v-for="item in activeWL.items" :key="item.id" class="wl-item">
              <div><span class="wl-ticker">{{ item.ticker }}</span><span v-if="names[item.ticker]" class="wl-name">{{ names[item.ticker] }}</span></div>
              <el-button text size="small" @click="handleRemove(item.id, item.ticker)" style="color:var(--danger)">✕ 移除</el-button>
            </div>
          </div>
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
.msg-toast { padding: 12px 16px; border-radius: 12px; font-size: 14px; }
.msg-success { background: rgba(52,211,153,0.1); color: var(--success); border: 1px solid rgba(52,211,153,0.2); }
.msg-error { background: rgba(248,113,113,0.1); color: var(--danger); border: 1px solid rgba(248,113,113,0.2); }
.new-form { padding: 16px; border-radius: 12px; background: var(--bg-tertiary); border: 1px solid var(--border); display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.holding-item { padding: 16px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); }
.holding-ticker { font-size: 18px; font-weight: 700; color: var(--text-primary); margin-right: 8px; }
.holding-shares { font-size: 14px; color: var(--text-secondary); }
.holding-cost { font-size: 14px; color: var(--text-secondary); margin-top: 4px; }
.wl-card { padding: 16px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); }
.wl-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.wl-search { position: relative; margin-bottom: 12px; }
.search-dropdown { position: absolute; z-index: 10; width: 100%; margin-top: 4px; border-radius: 8px; background: var(--bg-secondary); border: 1px solid var(--border); box-shadow: 0 4px 12px rgba(0,0,0,0.3); max-height: 192px; overflow-y: auto; }
.search-empty { padding: 8px; font-size: 14px; color: var(--text-secondary); text-align: center; }
.search-item { display: flex; align-items: center; gap: 12px; width: 100%; padding: 8px 12px; text-align: left; background: none; border: none; cursor: pointer; font-size: 14px; }
.search-item:hover { background: var(--bg-tertiary); }
.search-symbol { font-family: monospace; color: var(--accent); }
.search-name { color: var(--text-primary); }
.wl-items { display: flex; flex-direction: column; gap: 6px; }
.wl-item { display: flex; align-items: center; justify-content: space-between; padding: 8px; border-radius: 6px; background: var(--bg-tertiary); }
.wl-item:hover .wl-item button { opacity: 1; }
.wl-ticker { font-size: 14px; color: var(--text-primary); font-family: monospace; }
.wl-name { font-size: 12px; color: var(--text-secondary); margin-left: 8px; }
.wl-empty { text-align: center; padding: 8px; font-size: 14px; color: var(--text-secondary); }
</style>
