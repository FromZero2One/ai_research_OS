<script setup lang="ts">
import { ref } from 'vue'
import { searchKnowledge, type SearchResult } from '@/stores/api'

const query = ref('')
const docType = ref('')
const results = ref<SearchResult[]>([])
const loading = ref(false)
const searched = ref(false)
const expandedIdx = ref<number | null>(null)

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

function scoreColor(score: number) { return score > 0.7 ? '#34d399' : score > 0.4 ? '#fbbf24' : '#9aa0a6' }
</script>

<template>
  <div class="page">
    <div class="page-header">
      <h1 class="page-title">🧠 知识库</h1>
      <p class="page-desc">混合检索 RAG — 稠密向量 + BM25 + BGE Reranker 重排序</p>
    </div>

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
</style>
