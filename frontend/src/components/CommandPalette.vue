<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'

interface Command {
  id: string
  label: string
  description: string
  icon: string
  route: string
  keywords: string[]
}

const router = useRouter()
const open = ref(false)
const query = ref('')
const selectedIndex = ref(0)
const inputRef = ref<HTMLInputElement | null>(null)

const commands: Command[] = [
  { id: 'quick-research', label: '快速研究', description: '一键发起 AI 研究', icon: '⚡', route: '/research/quick', keywords: ['研究', '分析', 'research', 'quick'] },
  { id: 'research', label: '研究中心', description: '查看所有研究会话', icon: '🔬', route: '/research', keywords: ['研究', '会话', 'research', 'session'] },
  { id: 'timeline', label: '研究时间线', description: '按公司查看研究历史', icon: '📋', route: '/research/timeline', keywords: ['时间线', 'timeline', 'history'] },
  { id: 'dashboard', label: '工作台', description: '每日投资工作台', icon: '🏠', route: '/', keywords: ['首页', '工作台', 'home', 'dashboard'] },
  { id: 'companies', label: '公司', description: '浏览所有公司', icon: '🏢', route: '/companies', keywords: ['公司', '企业', 'company', 'ticker'] },
  { id: 'documents', label: '上传文档', description: '上传 PDF、报告或会议纪要', icon: '📄', route: '/documents', keywords: ['文档', '上传', 'pdf', 'document'] },
  { id: 'knowledge', label: '知识库搜索', description: '混合 RAG 搜索全部文档', icon: '🧠', route: '/knowledge', keywords: ['知识库', '搜索', 'rag', 'knowledge'] },
  { id: 'market', label: '行情', description: '市场行情与 K 线', icon: '📊', route: '/market', keywords: ['行情', '市场', 'k线', 'market', 'stock'] },
  { id: 'ai', label: 'AI 中心', description: 'Prompt 模板与 AI 工具', icon: '⚡', route: '/ai', keywords: ['ai', 'prompt', '模板', '生成'] },
  { id: 'portfolio', label: '投资组合', description: '自选列表、持仓与研究日志', icon: '💼', route: '/portfolio', keywords: ['组合', '持仓', '自选', 'portfolio'] },
  { id: 'system', label: '系统状态', description: '调度器状态与执行记录', icon: '📡', route: '/system', keywords: ['系统', '状态', '调度', 'scheduler'] },
]

const filtered = computed(() => {
  if (!query.value.trim()) return commands
  const q = query.value.toLowerCase()
  return commands.filter((cmd) =>
    cmd.label.toLowerCase().includes(q) ||
    cmd.description.toLowerCase().includes(q) ||
    cmd.keywords.some((k) => k.toLowerCase().includes(q))
  )
})

watch(filtered, () => { selectedIndex.value = 0 })

function onKeydown(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault()
    open.value = !open.value
  }
  if (e.key === 'Escape') open.value = false
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => document.removeEventListener('keydown', onKeydown))

watch(open, async (v) => {
  if (v) {
    await nextTick()
    inputRef.value?.focus()
    query.value = ''
    selectedIndex.value = 0
  }
})

function execute(cmd: Command) {
  open.value = false
  router.push(cmd.route)
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') { e.preventDefault(); selectedIndex.value = Math.min(selectedIndex.value + 1, filtered.value.length - 1) }
  if (e.key === 'ArrowUp') { e.preventDefault(); selectedIndex.value = Math.max(selectedIndex.value - 1, 0) }
  if (e.key === 'Enter' && filtered.value[selectedIndex.value]) { e.preventDefault(); execute(filtered.value[selectedIndex.value]) }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="cp-backdrop" @click="open = false">
      <div class="cp-modal" @click.stop>
        <div class="cp-input-wrap">
          <span class="cp-search-icon">🔍</span>
          <input
            ref="inputRef"
            v-model="query"
            @keydown="handleKeydown"
            placeholder="搜索命令..."
            class="cp-input"
          />
          <kbd class="cp-kbd">ESC</kbd>
        </div>
        <div class="cp-results">
          <div v-if="filtered.length === 0" class="cp-empty">没有匹配的命令</div>
          <div v-else class="cp-list">
            <div
              v-for="(cmd, i) in filtered"
              :key="cmd.id"
              class="cp-item"
              :class="{ 'cp-item-active': i === selectedIndex }"
              @click="execute(cmd)"
              @mouseenter="selectedIndex = i"
            >
              <span class="cp-item-icon">{{ cmd.icon }}</span>
              <div class="cp-item-text">
                <div class="cp-item-label">{{ cmd.label }}</div>
                <div class="cp-item-desc">{{ cmd.description }}</div>
              </div>
            </div>
          </div>
        </div>
        <div class="cp-footer">
          <span>↑↓ 导航</span>
          <span>↵ 确认</span>
          <span class="cp-footer-shortcut">⌘K 切换</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.cp-backdrop {
  position: fixed; inset: 0; z-index: 1000;
  display: flex; justify-content: center; padding-top: 15vh;
  background: rgba(0,0,0,0.6);
}
.cp-modal {
  width: 100%; max-width: 500px; height: fit-content;
  background: var(--bg-secondary); border: 1px solid var(--border);
  border-radius: 12px; overflow: hidden;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
}
.cp-input-wrap {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 16px; border-bottom: 1px solid var(--border);
}
.cp-search-icon { font-size: 18px; }
.cp-input {
  flex: 1; background: transparent; border: none;
  color: var(--text-primary); font-size: 14px; outline: none;
}
.cp-input::placeholder { color: #6b7280; }
.cp-kbd {
  padding: 2px 6px; border-radius: 4px;
  background: var(--bg-tertiary); color: var(--text-secondary);
  font-size: 11px; border: 1px solid var(--border);
}
.cp-results { max-height: 320px; overflow-y: auto; padding: 8px; }
.cp-empty { padding: 16px; text-align: center; color: var(--text-secondary); font-size: 14px; }
.cp-list { display: flex; flex-direction: column; gap: 2px; }
.cp-item {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 12px; border-radius: 8px; cursor: pointer;
  transition: background 0.15s;
}
.cp-item-active, .cp-item:hover { background: rgba(79,140,255,0.1); }
.cp-item-icon { font-size: 20px; }
.cp-item-text { flex: 1; min-width: 0; }
.cp-item-label { font-size: 14px; font-weight: 500; color: var(--text-primary); }
.cp-item-desc { font-size: 12px; color: var(--text-secondary); }
.cp-footer {
  display: flex; gap: 12px; padding: 8px 16px;
  border-top: 1px solid var(--border); font-size: 12px; color: #6b7280;
}
.cp-footer-shortcut { margin-left: auto; }
</style>
