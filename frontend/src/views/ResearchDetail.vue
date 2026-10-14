<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  DECISION_LABELS,
  RESEARCH_STATUS_LABELS,
  useResearchSession,
  useGeneratePlan,
  useAutoGatherEvidence,
  useGenerateReport,
  useFinalizeResearch,
  useSessionTimeline,
} from '@/stores/api'
import ReportCharts from '@/components/ReportCharts.vue'

const route = useRoute(); const router = useRouter()
const id = route.params.id as string
const { data: session, isLoading } = useResearchSession(id)
const { data: timeline } = useSessionTimeline(id)
const generatePlan = useGeneratePlan()
const gatherEvidence = useAutoGatherEvidence()
const generateReport = useGenerateReport()
const finalize = useFinalizeResearch()

const showFinalize = ref(false)
const thesis = ref('')
const decision = ref('buy')
const confidence = ref(0.7)
const expandedReport = ref<string | null>(null)
const diffVersion = ref<number | null>(null)
const showTimeline = ref(false)
const expandedEvidence = ref<Set<string>>(new Set())

// ── 报告引用回溯：解析 [ev:<uuid>] 内联标注 → 可点击锚点 ──
const EV_REF_RE = /\[ev:([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\]/g

interface ReportSegment { type: 'text' | 'ev'; text?: string; id?: string }

function parseEvRefs(content: string): ReportSegment[] {
  const parts: ReportSegment[] = []
  let last = 0
  for (const m of content.matchAll(EV_REF_RE)) {
    const idx = m.index ?? 0
    if (idx > last) parts.push({ type: 'text', text: content.slice(last, idx) })
    parts.push({ type: 'ev', id: m[1] })
    last = idx + m[0].length
  }
  if (last < content.length) parts.push({ type: 'text', text: content.slice(last) })
  return parts
}

function evExists(eid: string) {
  return (session.value?.evidences || []).some((e: any) => e.id === eid)
}

function jumpToEvidence(eid: string) {
  const el = document.getElementById('ev-' + eid)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  el.classList.add('ev-flash')
  setTimeout(() => el.classList.remove('ev-flash'), 1600)
}

const plan = computed(() => session.value?.plan || null)
const isCompleted = computed(() => session.value?.status === 'completed')
const hasPlan = computed(() => !!plan.value)
const supporting = computed(() => (session.value?.evidences || []).filter((e: any) => e.evidence_type === 'supporting'))
const opposing = computed(() => (session.value?.evidences || []).filter((e: any) => e.evidence_type === 'opposing'))
const neutral = computed(() => (session.value?.evidences || []).filter((e: any) => e.evidence_type === 'neutral'))

function statusType(s: string) { if (s === 'completed') return 'success'; if (s === 'researching') return 'warning'; if (s === 'reviewing') return 'primary'; if (s === 'draft') return 'info'; return 'info' }
function decisionType(d: string) { if (d === 'buy') return 'success'; if (d === 'sell') return 'danger'; if (d === 'hold' || d === 'watch') return 'warning'; return 'info' }
function evidenceTypeStyle(t: string) { if (t === 'supporting') return { bg: 'rgba(52,211,153,0.05)', border: 'rgba(52,211,153,0.2)', label: '支持', icon: '✅' }; if (t === 'opposing') return { bg: 'rgba(248,113,113,0.05)', border: 'rgba(248,113,113,0.2)', label: '反对', icon: '⚠️' }; return { bg: 'rgba(154,160,166,0.05)', border: 'var(--border)', label: '中性', icon: '📊' } }
function sourceIcon(s: string) { const m: Record<string, string> = { document: '📄', market_data: '📈', web: '🌐', ai_generated: '🤖', analyst_note: '📝' }; return m[s] || '📄' }
function scoreColor(s: number) { return s >= 0.7 ? 'var(--success)' : s >= 0.4 ? 'var(--warning)' : 'var(--danger)' }

async function handleFinalize() {
  if (!thesis.value.trim()) return
  await finalize.mutateAsync({ sessionId: id, thesis: thesis.value.trim(), decision: decision.value, confidence: confidence.value })
  showFinalize.value = false
}

function toggleEvidence(id: string) { const s = new Set(expandedEvidence.value); if (s.has(id)) s.delete(id); else s.add(id); expandedEvidence.value = s }
</script>

<template>
  <div v-if="isLoading" class="loading-state">加载中...</div>
  <div v-else-if="!session" class="loading-state" style="color:var(--danger)">研究会话不存在</div>
  <div v-else class="page">
    <div><el-button text @click="router.push('/research')">← 研究中心</el-button>
      <h1 class="page-title mt-2">{{ session.title }}</h1>
      <div class="flex items-center gap-3 mt-2">
        <el-tag :type="statusType(session.status)" size="small">{{ RESEARCH_STATUS_LABELS[session.status] || session.status }}</el-tag>
        <el-tag v-if="session.decision" :type="decisionType(session.decision)" size="small" effect="dark">{{ DECISION_LABELS[session.decision] || session.decision }}</el-tag>
        <span v-if="session.confidence != null" class="text-sm text-secondary">置信度: {{ Math.round(session.confidence * 100) }}%</span>
      </div>
    </div>

    <el-card shadow="never"><template #header><span class="text-sm text-secondary">研究问题</span></template><p class="text-lg leading-relaxed" style="color:var(--text-primary)">{{ session.question }}</p></el-card>

    <div v-if="!isCompleted" class="flex gap-3 flex-wrap">
      <el-button v-if="!hasPlan" @click="generatePlan.mutateAsync(id)" :disabled="generatePlan.isPending.value" type="primary">{{ generatePlan.isPending.value ? '生成中...' : '🎯 生成研究计划' }}</el-button>
      <el-button @click="gatherEvidence.mutateAsync(id)" :disabled="gatherEvidence.isPending.value">{{ gatherEvidence.isPending.value ? '收集中...' : '📚 收集证据' }}</el-button>
      <el-button @click="generateReport.mutateAsync({ sessionId: id, isFinal: false })" :disabled="generateReport.isPending.value">{{ generateReport.isPending.value ? '生成中...' : '📝 生成报告' }}</el-button>
      <el-button @click="showTimeline = !showTimeline">{{ showTimeline ? '隐藏时间线' : '📋 查看时间线' }}</el-button>
    </div>

    <el-card v-if="showTimeline && timeline" shadow="never">
      <template #header>📋 研究时间线</template>
      <div v-for="(event, i) in timeline.events" :key="i" class="tl-item"><span class="tl-date">{{ event.date ? new Date(event.date).toLocaleDateString('zh-CN') : '' }}</span><span class="tl-detail">{{ event.detail }}</span></div>
    </el-card>

    <div v-if="plan" class="plan-card">
      <h2 class="plan-title">📋 研究计划</h2>
      <div class="mb-3"><div class="text-sm text-secondary mb-1">目标</div><p class="text-sm" style="color:var(--text-primary)">{{ plan.research_goal }}</p></div>
      <div v-if="plan.sub_questions?.length" class="mb-3"><div class="text-sm text-secondary mb-1">子问题</div><ul><li v-for="(q, i) in plan.sub_questions" :key="i" class="flex gap-2 text-sm mb-1 items-center" style="color:var(--text-primary)"><span style="color:var(--accent)">{{ i + 1 }}.</span><span>{{ typeof q === 'string' ? q : q.text }}</span><el-tag v-if="typeof q === 'object' && q.priority === 'high'" type="danger" size="small" effect="plain">高优先级</el-tag><el-tag v-if="typeof q === 'object' && q.status === 'completed'" type="success" size="small" effect="plain">✓ 已完成</el-tag></li></ul></div>
      <div class="flex flex-wrap gap-2"><el-tag v-for="d in plan.analysis_dimensions || []" :key="d" size="small">{{ d }}</el-tag></div>
    </div>

    <div><h2 class="section-title">证据 <span class="text-sm font-normal text-secondary">({{ supporting.length }} 支持 · {{ opposing.length }} 反对 · {{ neutral.length }} 中性)</span></h2>
      <div v-if="!session.evidences?.length" class="empty-card">尚未收集证据，点击上方"收集证据"按钮</div>
      <div v-else class="space-y-3">
        <template v-for="(group, grpType) in { opposing, supporting, neutral }" :key="grpType">
          <div v-if="group.length">
            <div class="text-sm font-medium mb-2" :style="{ color: grpType === 'opposing' ? 'var(--danger)' : grpType === 'supporting' ? 'var(--success)' : 'var(--text-secondary)' }">{{ evidenceTypeStyle(grpType).icon }} {{ evidenceTypeStyle(grpType).label }}证据</div>
            <div v-for="ev in group" :key="ev.id" :id="'ev-' + ev.id" class="evidence-card" :style="{ background: evidenceTypeStyle(ev.evidence_type).bg, borderColor: evidenceTypeStyle(ev.evidence_type).border }">
              <div class="flex items-center gap-2 mb-2 flex-wrap">
                <span>{{ sourceIcon(ev.source_type) }}</span>
                <el-tag size="small">{{ ev.source_type }}</el-tag>
                <el-tag v-if="ev.content_nature === 'quantitative'" size="small" effect="plain" type="warning">🔢 定量</el-tag>
                <el-tag v-else-if="ev.content_nature === 'qualitative'" size="small" effect="plain">💬 定性</el-tag>
                <span v-if="ev.source_title" class="text-xs text-secondary truncate" style="max-width:200px">{{ ev.source_title }}</span>
                <span v-if="ev.citation_quality" class="text-xs" style="color:var(--text-secondary)">🔗 {{ ev.citation_quality }}</span>
                <el-tag v-if="ev.classification_source === 'llm'" size="small" effect="plain" :type="ev.classification_confidence != null && ev.classification_confidence < 0.6 ? 'warning' : 'info'">🤖 AI分类</el-tag>
                <span v-if="ev.reliability != null" class="text-xs"><span :style="{ color: scoreColor(ev.reliability) }">可靠: {{ Math.round(ev.reliability * 100) }}%</span></span>
                <span v-if="ev.data_freshness != null" class="text-xs" :style="{ color: ev.data_freshness > 2160 ? 'var(--warning)' : 'var(--text-secondary)' }">🕐 {{ ev.data_freshness >= 24 ? Math.round(ev.data_freshness / 24) + '天前' : ev.data_freshness + '小时前' }}</span>
                <span v-if="ev.relevance_score != null" class="text-xs ml-auto"><span :style="{ color: scoreColor(ev.relevance_score) }">可信度: {{ Math.round(ev.relevance_score * 100) }}%</span></span>
                <el-button text size="small" @click="toggleEvidence(ev.id)">{{ expandedEvidence.has(ev.id) ? '收起' : '展开' }}</el-button>
              </div>
              <p class="text-sm leading-relaxed" :class="{ 'line-clamp-3': !expandedEvidence.has(ev.id) }" style="color:var(--text-primary)">{{ ev.content }}</p>
              <div v-if="ev.source_id" class="mt-2 text-xs" style="color:var(--accent)">来源: {{ ev.source_id }}</div>
            </div>
          </div>
        </template>
      </div>
    </div>

    <el-card v-if="session.evidences?.length" shadow="never">
      <template #header>📊 数据可视化</template>
      <ReportCharts :evidences="session.evidences" />
    </el-card>

    <div v-if="session.reports?.length">
      <h2 class="section-title">研究报告 <span class="text-sm font-normal text-secondary">({{ session.reports.length }} 个版本)</span></h2>
      <div v-for="r in session.reports" :key="r.id" class="report-card">
        <div class="report-header" @click="expandedReport = expandedReport === r.id ? null : r.id">
          <div class="flex items-center gap-3"><span class="font-medium" style="color:var(--text-primary)">{{ r.title }}</span><span class="text-xs text-secondary">v{{ r.version }}</span><el-tag v-if="r.is_final" type="success" size="small" effect="dark">终稿</el-tag></div>
          <span class="text-sm text-secondary">{{ expandedReport === r.id ? '收起 ▲' : '展开 ▼' }}</span>
        </div>
        <div v-if="expandedReport === r.id" class="report-body">
          <div v-if="r.version > 1" class="flex gap-2 mb-2">
            <el-button @click.stop="diffVersion = diffVersion === r.version ? null : r.version - 1" size="small">{{ diffVersion === r.version ? '隐藏对比' : `📊 对比 v${r.version - 1}` }}</el-button>
          </div>
          <pre class="report-content"><template v-for="(seg, i) in parseEvRefs(r.content)" :key="i"><template v-if="seg.type === 'text'">{{ seg.text }}</template><a v-else-if="evExists(seg.id!)" class="ev-ref" title="回跳证据原文" @click.prevent="jumpToEvidence(seg.id!)">📎证据</a><span v-else class="ev-ref-missing">[ev:{{ seg.id!.slice(0, 8) }}]</span></template></pre>
        </div>
      </div>
    </div>

    <div v-if="session.thesis" class="thesis-card"><div class="text-sm text-secondary mb-2">投资论点</div><p class="leading-relaxed" style="color:var(--text-primary)">{{ session.thesis }}</p></div>

    <div v-if="!isCompleted" class="border-t pt-6" style="border-color:var(--border)">
      <div v-if="!showFinalize"><el-button @click="showFinalize = true" type="success" plain>🏁 完结研究</el-button></div>
      <div v-else class="finalize-card">
        <h3 class="font-medium mb-3" style="color:var(--text-primary)">完结研究</h3>
        <el-input v-model="thesis" type="textarea" :rows="3" placeholder="输入投资论点..." />
        <div class="flex gap-3 mt-3"><el-select v-model="decision" style="width:120px"><el-option value="buy" label="买入"/><el-option value="sell" label="卖出"/><el-option value="hold" label="持有"/><el-option value="watch" label="关注"/><el-option value="pass" label="跳过"/></el-select><div class="flex items-center gap-2"><span class="text-sm text-secondary">置信度:</span><el-slider v-model="confidence" :min="0" :max="1" :step="0.01" style="width:100px"/><span class="text-sm" style="width:32px">{{ Math.round(confidence * 100) }}%</span></div></div>
        <div class="flex gap-2 mt-3"><el-button @click="handleFinalize" :disabled="!thesis.trim() || finalize.isPending.value" type="success">{{ finalize.isPending.value ? '提交中...' : '确认完结' }}</el-button><el-button @click="showFinalize = false">取消</el-button></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.loading-state { text-align: center; padding: 48px 0; color: var(--text-secondary); }
.page { max-width: 800px; margin: 0 auto; display: flex; flex-direction: column; gap: 24px; }
.tl-item { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 8px; }
.tl-date { color: var(--text-secondary); width: 64px; flex-shrink: 0; font-size: 12px; }
.tl-detail { font-size: 14px; color: var(--text-primary); }
.plan-card { padding: 20px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); border-left: 4px solid var(--accent); }
.plan-title { font-size: 18px; font-weight: 600; color: var(--text-primary); margin-bottom: 12px; }
.section-title { font-size: 18px; font-weight: 600; color: var(--text-primary); margin-bottom: 12px; }
.empty-card { padding: 24px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); text-align: center; color: var(--text-secondary); font-size: 14px; }
.evidence-card { padding: 16px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); margin-bottom: 12px; }
.evidence-card p.line-clamp-3 { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.report-card { border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); overflow: hidden; margin-bottom: 12px; }
.report-header { display: flex; align-items: center; justify-content: space-between; padding: 16px; cursor: pointer; }
.report-header:hover { background: var(--bg-tertiary); }
.report-body { padding: 0 16px 16px; }
.report-content { padding: 16px; border-radius: 8px; background: #0d1117; font-size: 14px; line-height: 1.6; white-space: pre-wrap; font-family: monospace; max-height: 600px; overflow-y: auto; color: var(--text-primary); }
.ev-ref { color: var(--accent); cursor: pointer; text-decoration: none; border-bottom: 1px dashed var(--accent); font-size: 12px; }
.ev-ref:hover { opacity: 0.8; }
.ev-ref-missing { color: var(--text-secondary); font-size: 12px; }
.evidence-card.ev-flash { animation: ev-flash 1.6s ease; }
@keyframes ev-flash { 0%, 60% { box-shadow: 0 0 0 3px var(--accent); } 100% { box-shadow: none; } }
.thesis-card { padding: 20px; border-radius: 12px; background: var(--bg-secondary); border-left: 4px solid var(--accent); }
.finalize-card { padding: 20px; border-radius: 12px; background: var(--bg-secondary); border: 1px solid var(--border); }
</style>
