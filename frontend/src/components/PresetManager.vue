<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useCreateScreenerPreset,
  useDeleteScreenerPreset,
  useScreenerMetrics,
  useScreenerPresets,
  useUpdateScreenerPreset,
  type ScreenerPreset,
} from '@/stores/api'

const emit = defineEmits<{ (e: 'close'): void }>()

const { data: presetsData, isLoading } = useScreenerPresets()
const presets = computed(() => presetsData.value?.presets || [])

const { data: metricsData } = useScreenerMetrics()
const metrics = computed(() => metricsData.value?.metrics || [])
const metricOptions = computed(() =>
  metrics.value.map((m) => ({
    value: m.key,
    label: `${m.name_cn}（${m.data_source}）`,
    category: m.category,
  })),
)

const _OPS = ['>', '>=', '<', '<=']
const _POLICIES = [
  { value: 'exclude', label: '缺数据排除' },
  { value: 'include', label: '缺数据放行' },
]
const _POOLS = [
  { value: 'all', label: '全市场' },
  { value: 'main', label: '主板' },
  { value: 'chinext', label: '创业板' },
  { value: 'star', label: '科创板' },
]

// ── 编辑抽屉 ──
const drawerVisible = ref(false)
const editingId = ref<string | null>(null)
const form = ref<_PresetForm>(emptyForm())

interface _PresetForm {
  name: string
  description: string
  style_tag: string
  suggested_pool: string
  quant_rules: { metric: string; op: string; value: number | null; missing_data_policy: string }[]
  qualitative: string[]
}

function emptyForm(): _PresetForm {
  return {
    name: '',
    description: '',
    style_tag: 'custom',
    suggested_pool: 'all',
    quant_rules: [{ metric: '', op: '>', value: null, missing_data_policy: 'exclude' }],
    qualitative: [],
  }
}

function openCreate() {
  editingId.value = null
  form.value = emptyForm()
  drawerVisible.value = true
}

function openEdit(p: ScreenerPreset) {
  editingId.value = p.id
  form.value = {
    name: p.name,
    description: p.description || '',
    style_tag: p.style_tag || 'custom',
    suggested_pool: p.suggested_pool || 'all',
    quant_rules: p.quant_rules.map((r) => ({ ...r })),
    qualitative: [...p.qualitative],
  }
  drawerVisible.value = true
}

const createPreset = useCreateScreenerPreset()
const updatePreset = useUpdateScreenerPreset(computed(() => editingId.value || ''))

async function handleSave() {
  const f = form.value
  const rules = f.quant_rules.filter((r) => r.metric && r.value !== null)
  if (!f.name.trim()) { ElMessage.warning('请填写预设名称'); return }
  if (!rules.length) { ElMessage.warning('至少一条完整量化规则（指标 + 阈值）'); return }
  const body = {
    name: f.name.trim(),
    description: f.description.trim() || null,
    style_tag: f.style_tag || 'custom',
    suggested_pool: f.suggested_pool,
    quant_rules: rules.map((r) => ({ metric: r.metric, op: r.op, value: r.value, missing_data_policy: r.missing_data_policy })),
    qualitative: f.qualitative.filter((q) => q.trim()),
  }
  try {
    if (editingId.value) {
      await updatePreset.mutateAsync(body)
      ElMessage.success('预设已更新')
    } else {
      await createPreset.mutateAsync(body)
      ElMessage.success('预设已创建')
    }
    drawerVisible.value = false
  } catch (e: any) { ElMessage.error(e.message || '保存失败') }
}

const deletePreset = useDeleteScreenerPreset()
async function handleDelete(p: ScreenerPreset) {
  try {
    await ElMessageBox.confirm(`确定删除预设「${p.name}」？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await deletePreset.mutateAsync(`/screener/presets/${p.id}`)
    ElMessage.success('已删除')
  } catch (e: any) { ElMessage.error(e.message || '删除失败') }
}

async function handleToggleActive(p: ScreenerPreset) {
  try {
    await updatePreset.mutateAsync({ is_active: !p.is_active })
  } catch (e: any) { ElMessage.error(e.message || '操作失败') }
}

function ruleSummary(p: ScreenerPreset): string {
  const nameByKey = new Map(metrics.value.map((m) => [m.key, m.name_cn]))
  const parts = p.quant_rules.slice(0, 3).map(
    (r) => `${nameByKey.get(r.metric) || r.metric} ${r.op} ${r.value}`,
  )
  if (p.quant_rules.length > 3) parts.push(`…共 ${p.quant_rules.length} 条`)
  return parts.join('，')
}

const styleLabels: Record<string, string> = {
  core: '核心资产', growth: '高成长', value: '深度价值',
  garp: 'GARP', cycle: '周期反转', custom: '自定义', quality: '质量',
}

watch(drawerVisible, (v) => { if (!v) editingId.value = null })
</script>

<template>
  <div class="preset-manager">
    <div class="pm-toolbar">
      <el-button type="primary" size="small" @click="openCreate">+ 新建预设</el-button>
    </div>

    <div v-loading="isLoading" class="pm-list">
      <el-empty v-if="!isLoading && !presets.length" description="暂无预设" />
      <el-card v-for="p in presets" :key="p.id" class="pm-card" shadow="never">
        <div class="pm-row">
          <div class="pm-main">
            <div class="pm-title">
              <span class="pm-name">{{ p.name }}</span>
              <el-tag v-if="p.is_builtin" size="small" type="warning">内置</el-tag>
              <el-tag v-else size="small" type="info">自建</el-tag>
              <el-tag v-if="p.style_tag" size="small">{{ styleLabels[p.style_tag] || p.style_tag }}</el-tag>
            </div>
            <div class="pm-desc text-secondary">{{ p.description || '—' }}</div>
            <div class="pm-rules text-secondary">{{ ruleSummary(p) }}</div>
          </div>
          <div class="pm-actions">
            <el-switch
              :model-value="p.is_active"
              size="small"
              @change="handleToggleActive(p)"
            />
            <el-button
              size="small" link type="primary"
              :disabled="p.is_builtin" :title="p.is_builtin ? '内置预设不可修改' : ''"
              @click="openEdit(p)"
            >编辑</el-button>
            <el-button
              size="small" link type="danger"
              :disabled="p.is_builtin" :title="p.is_builtin ? '内置预设不可删除' : ''"
              @click="handleDelete(p)"
            >删除</el-button>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 新建/编辑抽屉 -->
    <el-drawer v-model="drawerVisible" :title="editingId ? '编辑预设' : '新建预设'" size="560px">
      <el-form label-width="90px" label-position="left">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如：低负债高现金流" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="预设的投资逻辑（可选）" />
        </el-form-item>
        <el-form-item label="风格标签">
          <el-select v-model="form.style_tag" style="width: 100%">
            <el-option v-for="(label, key) in styleLabels" :key="key" :value="key" :label="label" />
          </el-select>
        </el-form-item>
        <el-form-item label="建议股票池">
          <el-select v-model="form.suggested_pool" style="width: 100%">
            <el-option v-for="p in _POOLS" :key="p.value" :value="p.value" :label="p.label" />
          </el-select>
        </el-form-item>

        <el-divider content-position="left">量化规则（全部 AND）</el-divider>
        <div v-for="(r, i) in form.quant_rules" :key="i" class="rule-row">
          <el-select v-model="r.metric" filterable placeholder="指标" class="rule-metric">
            <el-option-group v-for="cat in [...new Set(metricOptions.map((m) => m.category))]" :key="cat" :label="cat">
              <el-option v-for="m in metricOptions.filter((x) => x.category === cat)" :key="m.value" :value="m.value" :label="m.label" />
            </el-option-group>
          </el-select>
          <el-select v-model="r.op" class="rule-op">
            <el-option v-for="op in _OPS" :key="op" :value="op" :label="op" />
          </el-select>
          <el-input-number v-model="r.value" :controls="false" class="rule-value" placeholder="阈值" />
          <el-select v-model="r.missing_data_policy" class="rule-policy">
            <el-option v-for="pl in _POLICIES" :key="pl.value" :value="pl.value" :label="pl.label" />
          </el-select>
          <el-button size="small" link type="danger" :disabled="form.quant_rules.length <= 1" @click="form.quant_rules.splice(i, 1)">✕</el-button>
        </div>
        <el-button size="small" link type="primary" @click="form.quant_rules.push({ metric: '', op: '>', value: null, missing_data_policy: 'exclude' })">+ 添加规则</el-button>

        <el-divider content-position="left">定性条目（LLM 深判用）</el-divider>
        <div v-for="(q, i) in form.qualitative" :key="i" class="qual-row">
          <el-input v-model="form.qualitative[i]" placeholder="定性判断条目" />
          <el-button size="small" link type="danger" @click="form.qualitative.splice(i, 1)">✕</el-button>
        </div>
        <el-button size="small" link type="primary" @click="form.qualitative.push('')">+ 添加定性条目</el-button>
      </el-form>
      <template #footer>
        <el-button @click="drawerVisible = false">取消</el-button>
        <el-button type="primary" :loading="createPreset.isPending.value || updatePreset.isPending.value" @click="handleSave">保存</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.pm-toolbar { display: flex; justify-content: flex-end; margin-bottom: 8px; }
.pm-list { display: flex; flex-direction: column; gap: 8px; }
.pm-card :deep(.el-card__body) { padding: 12px 16px; }
.pm-row { display: flex; justify-content: space-between; gap: 12px; }
.pm-title { display: flex; align-items: center; gap: 8px; }
.pm-name { font-weight: 600; }
.pm-desc { font-size: 12px; margin-top: 2px; }
.pm-rules { font-size: 12px; margin-top: 4px; }
.pm-actions { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.rule-row, .qual-row { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }
.rule-metric { flex: 1; min-width: 0; }
.rule-op { width: 72px; }
.rule-value { width: 110px; }
.rule-policy { width: 118px; }
.qual-row { margin-bottom: 8px; }
</style>
