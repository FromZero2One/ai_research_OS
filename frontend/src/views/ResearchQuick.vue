<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuickResearch, subscribeResearchStream, useStockSearch, type ResearchProgress } from '@/stores/api'

const route = useRoute()
const router = useRouter()
const initialTicker = (route.query.ticker as string) || ''

const tickerModel = ref(initialTicker)
const question = ref('')
const sessionId = ref<string | null>(null)
const searchQ = ref(initialTicker)
const showDrop = ref(false)
const searchRef = ref<HTMLDivElement | null>(null)
const progress = ref<ResearchProgress | null>(null)
const error = ref<string | null>(null)
const abortRef = ref<(() => void) | null>(null)

const { data: searchData } = useStockSearch(searchQ)
const searchResults = computed(() => searchData.value?.results || [])
const quickResearch = useQuickResearch()

const stepLabels: Record<string, string> = {
  starting: '准备开始...', planning: 'AI 正在生成研究计划...',
  searching: '正在搜索知识库和市场数据...', generating: 'AI 正在生成研究报告...',
  completed: '研究完成！', error: '研究出错',
}

function onClick(e: MouseEvent) { if (searchRef.value && !searchRef.value.contains(e.target as Node)) showDrop.value = false }
onMounted(() => document.addEventListener('mousedown', onClick))
onUnmounted(() => { document.removeEventListener('mousedown', onClick); abortRef.value?.() })

const progressPct = computed(() => {
  if (!progress.value) return 0
  if (progress.value.step === 'completed') return 100
  if (progress.value.step === 'generating') return 75
  if (progress.value.step === 'searching') return 50
  if (progress.value.step === 'planning') return 25
  return 0
})

async function handleStart() {
  if (!tickerModel.value.trim() || !question.value.trim()) return
  error.value = null; progress.value = null
  try {
    const result = await quickResearch.mutateAsync({ ticker: tickerModel.value.toUpperCase(), question: question.value.trim() })
    sessionId.value = result.session_id
    const cleanup = subscribeResearchStream(result.session_id, (p) => progress.value = p, (p) => progress.value = p, (err) => error.value = err)
    abortRef.value = cleanup
  } catch (e) { error.value = e instanceof Error ? e.message : '启动研究失败' }
}
</script>

<template>
  <div class="page">
    <div class="page-header"><h1 class="page-title">一键研究</h1><p class="page-desc">输入公司和问题，AI 自动完成研究</p></div>

    <template v-if="!sessionId">
      <div class="form-card">
        <label class="form-label">公司代码</label>
        <div ref="searchRef" class="search-wrap">
          <el-input v-model="searchQ" placeholder="搜索股票代码或名称..." @focus="showDrop = true" @input="showDrop = true" />
          <div v-if="showDrop && searchQ" class="search-dropdown">
            <div v-if="!searchResults.length" class="search-empty">无匹配结果</div>
            <button v-for="r in searchResults" :key="r.symbol" class="search-item" @click="tickerModel = r.symbol; searchQ = r.symbol; showDrop = false">
              <span class="search-symbol">{{ r.symbol }}</span><span v-if="r.name" class="search-name">{{ r.name }}</span>
            </button>
          </div>
        </div>

        <label class="form-label">研究问题<span class="text-xs text-secondary ml-2">({{ question.length }}/1000，至少 10 字)</span></label>
        <el-input v-model="question" type="textarea" :rows="4" placeholder="例如：未来两年的增长逻辑是什么？" :maxlength="1000" />

        <div v-if="error" class="error-msg">{{ error }}</div>

        <el-button @click="handleStart" :disabled="!tickerModel.trim() || !question.trim() || quickResearch.isPending.value" type="primary" class="w-full" size="large">
          {{ quickResearch.isPending.value ? '启动中...' : '🚀 开始研究' }}
        </el-button>
      </div>
    </template>

    <template v-else>
      <div class="progress-card">
        <div class="progress-header">
          <span class="progress-step-text">{{ progress ? stepLabels[progress.step] || progress.message : '正在启动...' }}</span>
          <span class="progress-pct">{{ progressPct }}%</span>
        </div>
        <el-progress :percentage="progressPct" :status="progress?.step === 'completed' ? 'success' : progress?.step === 'error' ? 'exception' : undefined" :stroke-width="8" />

        <div class="step-list">
          <div v-for="step in ['starting', 'planning', 'searching', 'generating', 'completed']" :key="step" class="step-item">
            <span v-if="['completed', 'error'].includes(progress?.step || '') || ['planning', 'searching', 'generating', 'completed'].indexOf(step) < ['planning', 'searching', 'generating', 'completed'].indexOf(progress?.step || 'starting')" class="step-done">✅</span>
            <span v-else-if="step === progress?.step" class="step-active">⏳</span>
            <span v-else class="step-pending">⬜</span>
            <span :class="['step-label', { 'step-done-text': ['completed', 'error'].includes(progress?.step || '') || ['planning', 'searching', 'generating', 'completed'].indexOf(step) < ['planning', 'searching', 'generating', 'completed'].indexOf(progress?.step || 'starting'), 'step-active-text': step === progress?.step, 'step-pending-text': step !== progress?.step && !(['completed', 'error'].includes(progress?.step || '') || ['planning', 'searching', 'generating', 'completed'].indexOf(step) < ['planning', 'searching', 'generating', 'completed'].indexOf(progress?.step || 'starting')) }]">{{ stepLabels[step] }}</span>
          </div>
        </div>

        <div v-if="progress?.step === 'error' && progress?.error" class="error-msg">{{ progress.error }}</div>

        <div v-if="progress?.step === 'completed' && sessionId" class="actions">
          <el-button @click="router.push(`/research/${sessionId}`)" type="primary" class="w-full">📖 查看研究报告</el-button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 500px; margin: 0 auto; display: flex; flex-direction: column; gap: 24px; }
.form-card { display: flex; flex-direction: column; gap: 16px; }
.form-label { font-size: 14px; font-weight: 500; color: var(--text-primary); }
.search-wrap { position: relative; }
.search-dropdown { position: absolute; z-index: 10; width: 100%; margin-top: 4px; border-radius: 8px; background: var(--bg-secondary); border: 1px solid var(--border); box-shadow: 0 4px 12px rgba(0,0,0,0.3); max-height: 192px; overflow-y: auto; }
.search-empty { padding: 8px; font-size: 14px; color: var(--text-secondary); text-align: center; }
.search-item { display: flex; align-items: center; gap: 12px; width: 100%; padding: 8px 12px; text-align: left; background: none; border: none; cursor: pointer; font-size: 14px; }
.search-item:hover { background: var(--bg-tertiary); }
.search-symbol { font-family: monospace; color: var(--accent); }
.search-name { color: var(--text-primary); }
.error-msg { padding: 12px; border-radius: 8px; background: rgba(248,113,113,0.1); border: 1px solid rgba(248,113,113,0.2); font-size: 14px; color: var(--danger); }
.progress-card { padding: 24px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); display: flex; flex-direction: column; gap: 16px; }
.progress-header { display: flex; align-items: center; justify-content: space-between; font-size: 14px; }
.progress-step-text { color: var(--text-primary); }
.progress-pct { color: var(--text-secondary); }
.step-list { display: flex; flex-direction: column; gap: 8px; }
.step-item { display: flex; align-items: center; gap: 8px; font-size: 14px; }
.step-done, .step-done-text { color: var(--success); }
.step-active { color: var(--accent); animation: pulse 1.5s infinite; }
.step-active-text { color: var(--text-primary); }
.step-pending, .step-pending-text { color: #4a4d59; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
.actions { padding-top: 8px; }
</style>
