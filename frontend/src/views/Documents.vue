<script setup lang="ts">
import { ref, useTemplateRef, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { useDocumentStatus, useDocuments, useUploadDocument } from '@/stores/api'

const queryClient = useQueryClient()
const docType = ref('all')
const isDragOver = ref(false)
const uploading = ref(false)
const uploadMsg = ref<{ type: 'success' | 'error'; text: string } | null>(null)
const indexingId = ref<string | null>(null)
const fileInputRef = useTemplateRef<HTMLInputElement>('fileInput')

const { data, isLoading } = useDocuments(docType.value === 'all' ? undefined : docType.value)
const uploadDoc = useUploadDocument()
const { data: indexingStatus } = useDocumentStatus(indexingId)

const docTypes = ['all', 'pdf', 'markdown', 'text', 'report', 'transcript']

async function handleFile(file: File) {
  if (file.size > 50 * 1024 * 1024) { uploadMsg.value = { type: 'error', text: `文件过大 (${(file.size / 1024 / 1024).toFixed(1)}MB)，最大 50MB` }; return }
  uploading.value = true; uploadMsg.value = null
  try {
    const result = await uploadDoc.mutateAsync(file)
    indexingId.value = result.id
    uploadMsg.value = { type: 'success', text: `"${result.title}" 上传成功，正在后台索引...` }
  } catch (e: any) { uploadMsg.value = { type: 'error', text: e.message || '上传失败' } } finally { uploading.value = false }
}

// Poll the background indexing task; refresh the list when it finishes/fails.
watch(indexingStatus, (st) => {
  if (!st || !indexingId.value) return
  if (st.is_indexed || st.error) {
    indexingId.value = null
    queryClient.invalidateQueries({ queryKey: ['documents'] })
    uploadMsg.value = st.error
      ? { type: 'error', text: st.message || '索引失败' }
      : { type: 'success', text: `索引完成 — ${st.chunk_count ?? 0} 个切片` }
  }
})

function onDrop(e: DragEvent) { e.preventDefault(); isDragOver.value = false; const file = e.dataTransfer?.files?.[0]; if (file) handleFile(file) }
function onSelect(e: Event) { const file = (e.target as HTMLInputElement).files?.[0]; if (file) handleFile(file); if (fileInputRef.value) fileInputRef.value.value = '' }
</script>

<template>
  <div class="page">
    <div class="page-header"><h1 class="page-title">📄 文档中心</h1><p class="page-desc">导入 → 解析 → 分块 → 嵌入 → 索引 — 完整知识处理管道</p></div>

    <div class="upload-zone" :class="{ 'drag-over': isDragOver, uploading }" @dragover.prevent="isDragOver = true" @dragleave="isDragOver = false" @drop="onDrop" @click="fileInputRef?.click()">
      <input ref="fileInput" type="file" accept=".pdf,.md,.txt,.html,.htm" class="hidden" @change="onSelect" />
      <div v-if="uploading"><div class="text-3xl mb-2 animate-pulse">⏳</div><div class="font-medium">上传中...</div><div class="text-sm text-secondary mt-1">正在解析并索引文档</div></div>
      <div v-else><div class="text-3xl mb-2">📤</div><div class="font-medium">点击或拖拽文件到此处上传</div><div class="text-sm text-secondary mt-1">PDF · Markdown · TXT · HTML — 最大 50MB</div></div>
    </div>

    <div v-if="uploadMsg" class="msg-toast" :class="uploadMsg.type === 'success' ? 'msg-success' : 'msg-error'">{{ uploadMsg.text }}</div>

    <el-radio-group v-model="docType">
      <el-radio-button v-for="t in docTypes" :key="t" :value="t">{{ t.charAt(0).toUpperCase() + t.slice(1) }}</el-radio-button>
    </el-radio-group>

    <div v-if="isLoading" class="loading-state">加载中...</div>
    <div v-else-if="!data || !data.items.length" class="empty-state">
      <div class="text-3xl mb-3">📄</div>
      <div class="font-medium">暂无文档</div>
      <div class="text-sm text-secondary mt-1">上传第一个 PDF 或研究报告</div>
    </div>
    <div v-else class="doc-list">
      <div v-for="doc in data.items" :key="doc.id" class="doc-item">
        <div class="doc-info"><div class="doc-title">{{ doc.title }}</div><div class="doc-meta"><span>{{ doc.doc_type }}</span><span>·</span><span>{{ doc.chunk_count || 0 }} 切片</span><span v-if="doc.source">· {{ doc.source }}</span></div></div>
        <el-tag :type="doc.is_indexed ? 'success' : 'warning'" size="small">{{ doc.is_indexed ? '已索引' : '索引中...' }}</el-tag>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1000px; margin: 0 auto; display: flex; flex-direction: column; gap: 20px; }
.upload-zone { padding: 32px; border: 2px dashed var(--border); border-radius: 12px; text-align: center; cursor: pointer; transition: all 0.2s; background: var(--bg-secondary); }
.upload-zone.drag-over { background: rgba(79,140,255,0.05); border-color: var(--accent); }
.upload-zone.uploading { border-color: var(--warning); }
.hidden { display: none; }
.msg-toast { padding: 12px 16px; border-radius: 12px; font-size: 14px; }
.msg-success { background: rgba(52,211,153,0.1); color: var(--success); border: 1px solid rgba(52,211,153,0.2); }
.msg-error { background: rgba(248,113,113,0.1); color: var(--danger); border: 1px solid rgba(248,113,113,0.2); }
.loading-state, .empty-state { text-align: center; padding: 48px 0; color: var(--text-secondary); }
.doc-list { display: flex; flex-direction: column; gap: 8px; }
.doc-item { display: flex; align-items: center; justify-content: space-between; padding: 16px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); }
.doc-title { font-weight: 500; color: var(--text-primary); }
.doc-meta { font-size: 12px; color: var(--text-secondary); margin-top: 4px; display: flex; gap: 4px; }
</style>
