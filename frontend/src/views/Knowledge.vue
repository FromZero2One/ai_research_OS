<script setup lang="ts">
import { ref } from 'vue'
import { searchKnowledge, useAskKnowledge, type SearchResult } from '@/stores/api'

const query = ref('')
const docType = ref('')
const results = ref<SearchResult[]>([])
const loading = ref(false)
const searched = ref(false)
const expandedIdx = ref<number | null>(null)

const askQuestion = ref('')
const askResult = ref<{ answer: string; sources: { title: string; chunk_index: number; score: number; content: string }[] } | null>(null)
const askLoading = ref(false)
const ask = useAskKnowledge()

const docTypes = [
  { value: '', label: '全部' },
  { value: 'pdf', label: 'PDF' },
  { value: 'markdown', label: 'Markdown' },
  { value: 'text', label: 'TXT' },
  { value: 'report', label: '报告' },
]

async function handleSearch() {
  if (!query.value.trim()) return
  loading.value = true
  try { const data = await searchKnowledge(query.value, 10, docType.value || undefined); results.value = data.results; searched.value = true } finally { loading.value = false }
}

async function handleAsk() {
  if (!askQuestion.value.trim()) return
  askLoading.value = true
  askResult.value = null
  try {
    askResult.value = await ask.mutateAsync({ question: askQuestion.value.trim(), top_k: 5 })
  } catch (e: any) {
    askResult.value = { answer: `问答失败: ${e.message}`, sources: [] }
  } finally { askLoading.value = false }
}

function scoreColor(score: number) { return score > 0.7 ? '#34d399' : score > 0.4 ? '#fbbf24' : '#9aa0a6' }
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1 class="page-title">🧠 知识库</h1>
      <p class="page-desc">混合检索 RAG — 稠密向量 + BM25 + BGE Reranker 重排序</p>
    </div>

    <el-alert type="info" :closable="false" class="mode-alert">
      <template #title>搜索 vs 提问</template>
      <div class="mode-desc">
        <div><b>🔍 搜索</b> — 返回相关原文切片，可核对出处；适合浏览资料、确认数据</div>
        <div><b>💬 提问</b> — AI 综合多个片段生成带引用 [1][2] 的回答；适合快速获取结论</div>
        <div class="mode-note">⚠️ 重要数据请以「搜索」的原文为准</div>
      </div>
    </el-alert>

    <el-card shadow="never" class="ask-card">
      <template #header><span>💬 文档问答</span><span class="text-xs text-secondary ml-2">基于知识库内容生成带引用回答</span></template>
      <div class="ask-input-row">
        <el-input v-model="askQuestion" placeholder="例如：中国银行2025年营业收入是多少？" @keydown.enter="handleAsk" :disabled="askLoading" />
        <el-button @click="handleAsk" :disabled="askLoading || !askQuestion.trim()" type="primary">{{ askLoading ? '思考中...' : '提问' }}</el-button>
      </div>
      <div v-if="askResult" class="ask-result">
        <p class="ask-answer whitespace-pre-wrap">{{ askResult.answer }}</p>
        <div v-if="askResult.sources.length" class="ask-sources">
          <div class="text-xs text-secondary mb-1">来源</div>
          <div v-for="(s, i) in askResult.sources" :key="i" class="ask-source">
            <span class="ask-source-tag">[{{ i + 1 }}]</span>
            <span class="ask-source-title">{{ s.title }}</span>
            <span class="ask-source-meta">切片 {{ s.chunk_index }} · 得分 {{ s.score.toFixed(3) }}</span>
          </div>
        </div>
      </div>
    </el-card>

    <div class="search-bar">
      <el-input v-model="query" placeholder="搜索知识库..." clearable @keydown.enter="handleSearch">
        <template #append><el-button @click="handleSearch" :disabled="loading || !query.trim()" type="primary">{{ loading ? '搜索中...' : '搜索' }}</el-button></template>
      </el-input>
    </div>

    <el-radio-group v-model="docType" @change="handleSearch">
      <el-radio-button v-for="t in docTypes" :key="t.value" :value="t.value">{{ t.label }}</el-radio-button>
    </el-radio-group>

    <div v-if="loading" class="loading-state"><el-icon class="is-loading" :size="20"><i class="el-icon-loading"></i></el-icon>混合检索中...</div>

    <template v-else-if="results.length > 0">
      <div class="flex items-center justify-between mb-2">
        <span class="text-sm text-secondary">找到 {{ results.length }} 条结果</span>
        <el-button v-if="searched" text size="small" @click="results = []; searched = false; query = ''">清除</el-button>
      </div>
      <div v-for="(r, i) in results" :key="i" class="result-card">
        <div class="result-header">
          <div class="result-meta"><el-tag size="small">{{ r.doc_type }}</el-tag><span class="result-title">{{ r.title }}</span></div>
          <div class="score-bar"><div class="score-track"><div class="score-fill" :style="{ width: `${Math.min(r.score * 100, 100)}%`, backgroundColor: scoreColor(r.score) }" /></div><span class="score-text" :style="{ color: scoreColor(r.score) }">{{ r.score.toFixed(3) }}</span></div>
        </div>
        <p class="result-content" :class="{ 'line-clamp-3': expandedIdx !== i }">{{ r.content }}</p>
        <div class="result-footer">
          <el-button text size="small" @click="expandedIdx = expandedIdx === i ? null : i">{{ expandedIdx === i ? '收起' : '展开全部' }}</el-button>
          <span class="text-xs text-gray">文档ID: {{ r.document_id.slice(0, 8) }}...</span>
        </div>
      </div>
    </template>

    <el-empty v-else-if="searched" description="未找到结果"><p class="text-xs text-secondary mt-1">知识库中还没有匹配的内容。上传文档后会自动索引到 Qdrant。</p></el-empty>
    <el-empty v-else description="搜索全部已索引文档"><p class="text-xs text-secondary mt-1">稠密 + 稀疏混合检索 → RRF 融合 → BGE Reranker 重排序</p></el-empty>
  </div>
</template>

<style scoped>
.page { max-width: 800px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; }
.search-bar { margin-bottom: 4px; }
.loading-state { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 40px 0; color: var(--text-secondary); }
.result-card { padding: 16px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); transition: border-color 0.2s; }
.result-card:hover { border-color: rgba(79,140,255,0.2); }
.result-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.result-meta { display: flex; align-items: center; gap: 8px; min-width: 0; }
.result-title { font-size: 14px; font-weight: 500; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.score-bar { display: flex; align-items: center; gap: 6px; }
.score-track { width: 64px; height: 6px; border-radius: 3px; background: var(--border); overflow: hidden; }
.score-fill { height: 100%; border-radius: 3px; transition: width 0.3s; }
.score-text { font-size: 11px; }
.result-content { font-size: 13px; color: var(--text-secondary); line-height: 1.6; }
.result-content.line-clamp-3 { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.result-footer { display: flex; align-items: center; gap: 12px; margin-top: 8px; }
.ask-card { margin-bottom: 4px; }
.mode-alert { margin-bottom: 4px; }
.mode-desc { font-size: 13px; line-height: 1.7; color: var(--text-primary); }
.mode-note { font-size: 12px; color: var(--warning); margin-top: 2px; }
.ask-input-row { display: flex; gap: 8px; }
.ask-result { margin-top: 12px; padding: 12px; border-radius: 8px; background: var(--bg-tertiary); }
.ask-answer { font-size: 14px; line-height: 1.7; color: var(--text-primary); }
.ask-sources { margin-top: 12px; display: flex; flex-direction: column; gap: 6px; }
.ask-source { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.ask-source-tag { color: var(--accent); font-weight: 600; }
.ask-source-title { color: var(--text-primary); }
.ask-source-meta { color: var(--text-secondary); margin-left: auto; }
</style>
