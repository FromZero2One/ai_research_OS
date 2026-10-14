<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useCreateTemplate,
  useDeleteTemplate,
  useExecuteTemplate,
  useListTemplates,
  useUpdateTemplate,
} from '@/stores/api'

const { data: templates } = useListTemplates()
const showNew = ref(false)
const newTmpl = ref({ name: '', description: '', system_prompt: '', user_prompt_template: '' })
const editId = ref<string | null>(null)
const editTmpl = ref({ name: '', description: '', system_prompt: '', user_prompt_template: '' })
const execId = ref<string | null>(null)
const execDialogVisible = computed({ get: () => execId.value !== null, set: (v: boolean) => { if (!v) execId.value = null } })
const execVars = ref('')
const execResult = ref('')
const execLoading = ref(false)

const createTemplate = useCreateTemplate()
const updateTemplate = useUpdateTemplate(computed(() => editId.value || ''))
const deleteTemplate = useDeleteTemplate()
const executeTemplate = useExecuteTemplate()

async function handleCreateTemplate() {
  if (!newTmpl.value.name.trim()) return
  try {
    await createTemplate.mutateAsync({ ...newTmpl.value })
    showNew.value = false
    newTmpl.value = { name: '', description: '', system_prompt: '', user_prompt_template: '' }
    ElMessage.success('模板已创建')
  } catch (e) { ElMessage.error((e as Error).message || '创建失败') }
}

async function handleUpdateTemplate(id: string) {
  editId.value = id
  try {
    await updateTemplate.mutateAsync({ ...editTmpl.value })
    editId.value = null
    ElMessage.success('模板已更新')
  } catch (e) { ElMessage.error((e as Error).message || '更新失败') }
}

async function handleDeleteTemplate(id: string) {
  try {
    await deleteTemplate.mutateAsync(id)
    ElMessage.success('模板已删除')
  } catch (e) { ElMessage.error((e as Error).message || '删除失败') }
}

async function handleExecute(id: string) {
  execLoading.value = true; execResult.value = ''
  try {
    const variables: Record<string, string> = {}
    execVars.value.split('\n').filter(Boolean).forEach((line) => { const idx = line.indexOf('='); if (idx > 0) variables[line.slice(0, idx).trim()] = line.slice(idx + 1).trim() })
    const data = await executeTemplate.mutateAsync({ prompt_name: id, variables })
    execResult.value = data.content || data.error || 'No response'
  } catch (e: any) { execResult.value = 'Error: ' + e.message } finally { execLoading.value = false }
}
</script>

<template>
  <div class="page">
    <div class="page-header"><h1 class="page-title">⚡ AI 中心</h1><p class="page-desc">Prompt 模板管理 · 模板执行 · Token 用量（AI 能力已内嵌研究与知识流程）</p></div>

    <el-card shadow="never">
      <template #header><div class="flex items-center justify-between"><span>📝 Prompt 模板</span><el-button @click="showNew = !showNew" text>{{ showNew ? '取消' : '+ 新建' }}</el-button></div></template>

      <div v-if="showNew" class="new-form">
        <el-input v-model="newTmpl.name" placeholder="模板名称" size="small" />
        <el-input v-model="newTmpl.description" placeholder="描述（可选）" size="small" />
        <el-input v-model="newTmpl.system_prompt" placeholder="System Prompt" type="textarea" :rows="2" />
        <el-input v-model="newTmpl.user_prompt_template" placeholder="User Prompt 模板 (支持 {variable})" type="textarea" :rows="2" />
        <el-button @click="handleCreateTemplate" :disabled="!newTmpl.name.trim()" type="success" size="small">保存</el-button>
      </div>

      <div v-if="!templates?.length" class="text-sm text-secondary">暂无模板，点击"新建"创建</div>
      <div v-else class="space-y-2">
        <div v-for="t in templates || []" :key="t.id">
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
</style>
