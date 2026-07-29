<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

interface PromptTemplate { id: string; name: string; description: string | null; system_prompt: string | null; user_prompt_template: string | null; temperature: number | null; max_tokens: number | null; is_active: boolean }

const text = ref('')
const summary = ref('')
const loading = ref(false)
const templates = ref<PromptTemplate[]>([])
const showNew = ref(false)
const newTmpl = ref({ name: '', description: '', system_prompt: '', user_prompt_template: '' })
const editId = ref<string | null>(null)
const editTmpl = ref({ name: '', description: '', system_prompt: '', user_prompt_template: '' })
const execId = ref<string | null>(null)
const execDialogVisible = computed({ get: () => execId.value !== null, set: (v: boolean) => { if (!v) execId.value = null } })
const execVars = ref('')
const execResult = ref('')
const execLoading = ref(false)

onMounted(() => { fetch('/api/ai/templates').then((r) => r.json()).then((data) => { templates.value = data }).catch(() => {}) })

async function handleSummarize() {
  if (!text.value.trim()) return
  loading.value = true
  try { const resp = await fetch('/api/ai/summarize', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text.value, max_length: 300, format_: 'paragraph' }) }); const data = await resp.json(); summary.value = data.content || data.error || 'No response' } catch (e: any) { summary.value = 'Error: ' + e.message } finally { loading.value = false }
}

async function handleCreateTemplate() {
  if (!newTmpl.value.name.trim()) return
  try { const resp = await fetch('/api/ai/templates', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(newTmpl.value) }); if (resp.ok) { const created = await resp.json(); templates.value = [...templates.value, created]; showNew.value = false; newTmpl.value = { name: '', description: '', system_prompt: '', user_prompt_template: '' } } } catch (e) { console.error(e) }
}

async function handleUpdateTemplate(id: string) {
  try { const resp = await fetch(`/api/ai/templates/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(editTmpl.value) }); if (resp.ok) { const updated = await resp.json(); templates.value = templates.value.map((t) => (t.id === id ? updated : t)); editId.value = null } } catch (e) { console.error(e) }
}

async function handleDeleteTemplate(id: string) {
  try { await fetch(`/api/ai/templates/${id}`, { method: 'DELETE' }); templates.value = templates.value.filter((t) => t.id !== id) } catch (e) { console.error(e) }
}

async function handleExecute(id: string) {
  execLoading.value = true; execResult.value = ''
  try {
    const variables: Record<string, string> = {}
    execVars.value.split('\n').filter(Boolean).forEach((line) => { const idx = line.indexOf('='); if (idx > 0) variables[line.slice(0, idx).trim()] = line.slice(idx + 1).trim() })
    const resp = await fetch('/api/ai/generate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt_name: id, variables }) })
    const data = await resp.json(); execResult.value = data.content || data.error || 'No response'
  } catch (e: any) { execResult.value = 'Error: ' + e.message } finally { execLoading.value = false }
}
</script>

<template>
  <div class="page">
    <div class="page-header"><h1 class="page-title">⚡ AI 中心</h1><p class="page-desc">Prompt 管理 · LLM 编排 · 文本摘要 · 结构化提取</p></div>

    <el-row :gutter="16">
      <el-col v-for="c in [{ icon:'📝', title:'Prompt 模板', desc:'管理可复用的 System + User Prompt，支持变量注入' }, { icon:'🔄', title:'工作流', desc:'多步骤 LLM 管道（顺序执行，后续支持 LangGraph 有向图）' }, { icon:'🔧', title:'结构提取', desc:'基于 JSON Schema 验证的结构化数据提取' }]" :key="c.title" :span="8">
        <el-card shadow="never"><div class="text-2xl mb-2">{{ c.icon }}</div><div class="font-medium mb-1">{{ c.title }}</div><div class="text-sm text-secondary">{{ c.desc }}</div></el-card>
      </el-col>
    </el-row>

    <el-card shadow="never">
      <template #header><div class="flex items-center justify-between"><span>📝 Prompt 模板</span><el-button @click="showNew = !showNew" text>{{ showNew ? '取消' : '+ 新建' }}</el-button></div></template>

      <div v-if="showNew" class="new-form">
        <el-input v-model="newTmpl.name" placeholder="模板名称" size="small" />
        <el-input v-model="newTmpl.description" placeholder="描述（可选）" size="small" />
        <el-input v-model="newTmpl.system_prompt" placeholder="System Prompt" type="textarea" :rows="2" />
        <el-input v-model="newTmpl.user_prompt_template" placeholder="User Prompt 模板 (支持 {variable})" type="textarea" :rows="2" />
        <el-button @click="handleCreateTemplate" :disabled="!newTmpl.name.trim()" type="success" size="small">保存</el-button>
      </div>

      <div v-if="templates.length === 0" class="text-sm text-secondary">暂无模板，点击"新建"创建</div>
      <div v-else class="space-y-2">
        <div v-for="t in templates" :key="t.id">
          <div v-if="editId === t.id" class="edit-form">
            <el-input v-model="editTmpl.name" placeholder="名称" size="small" />
            <el-input v-model="editTmpl.description" placeholder="描述" size="small" />
            <el-input v-model="editTmpl.system_prompt" placeholder="System Prompt" type="textarea" :rows="2" />
            <el-input v-model="editTmpl.user_prompt_template" placeholder="User Prompt" type="textarea" :rows="2" />
            <div class="flex gap-2"><el-button @click="handleUpdateTemplate(t.id)" type="success" size="small">保存</el-button><el-button @click="editId = null" size="small">取消</el-button></div>
          </div>
          <div v-else class="template-row">
            <div><div class="template-name">{{ t.name }}</div><div class="template-desc">{{ t.description || '无描述' }}</div></div>
            <div class="template-actions">
              <el-button text size="small" @click="editId = t.id; editTmpl = { name: t.name || '', description: t.description || '', system_prompt: t.system_prompt || '', user_prompt_template: t.user_prompt_template || '' }">编辑</el-button>
              <el-button text size="small" @click="execId = t.id; execVars = ''; execResult = ''">执行</el-button>
              <el-button text size="small" @click="handleDeleteTemplate(t.id)" style="color: var(--danger)">删除</el-button>
            </div>
          </div>
        </div>
      </div>

      <el-dialog v-model="execDialogVisible" title="执行模板" width="500px">
        <div class="space-y-3">
          <el-input v-model="execVars" placeholder="每行一个变量，格式 key=value&#10;例如:&#10;company=工商银行&#10;topic=估值分析" type="textarea" :rows="4" />
          <el-button @click="handleExecute(execId!)" :disabled="execLoading" type="primary" class="w-full">{{ execLoading ? '执行中...' : '执行' }}</el-button>
          <div v-if="execResult" class="exec-result"><div class="text-xs text-secondary mb-1">结果</div><p class="text-sm whitespace-pre-wrap">{{ execResult }}</p></div>
        </div>
      </el-dialog>
    </el-card>

    <el-card shadow="never">
      <template #header>摘要功能演示</template>
      <el-input v-model="text" placeholder="粘贴要摘要的文本..." type="textarea" :rows="4" />
      <el-button @click="handleSummarize" :disabled="loading || !text.trim()" type="primary" class="mt-3">{{ loading ? '摘要中...' : '生成摘要' }}</el-button>
      <div v-if="summary" class="summary-result"><div class="text-xs text-secondary mb-2">摘要结果</div><p class="text-sm leading-relaxed whitespace-pre-wrap">{{ summary }}</p></div>
    </el-card>
  </div>
</template>

<style scoped>
.page { max-width: 1000px; margin: 0 auto; display: flex; flex-direction: column; gap: 24px; }
.new-form, .edit-form { display: flex; flex-direction: column; gap: 8px; padding: 16px; border-radius: 8px; background: var(--bg-tertiary); border: 1px solid var(--border); margin-bottom: 12px; }
.template-row { display: flex; align-items: center; justify-content: space-between; padding: 12px; border-radius: 8px; background: var(--bg-tertiary); border: 1px solid var(--border); margin-bottom: 8px; }
.template-name { font-size: 14px; font-weight: 500; color: var(--text-primary); }
.template-desc { font-size: 12px; color: var(--text-secondary); }
.template-actions { display: flex; gap: 8px; align-items: center; }
.exec-result { padding: 12px; border-radius: 8px; background: var(--bg-tertiary); border: 1px solid var(--border); max-height: 240px; overflow: auto; }
.summary-result { margin-top: 16px; padding: 16px; border-radius: 8px; background: var(--bg-tertiary); border: 1px solid var(--border); }
</style>
