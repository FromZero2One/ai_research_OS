<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { HomeFilled, Lightning, Search, Timer, Briefcase, Document, Collection, TrendCharts, Cpu, Money, Monitor, Setting } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()

const navItems = [
  { label: '工作台', route: '/', icon: HomeFilled },
  { label: '快速研究', route: '/research/quick', icon: Lightning },
  { label: '研究中心', route: '/research', icon: Search },
  { label: '研究时间线', route: '/research/timeline', icon: Timer },
  { label: '公司', route: '/companies', icon: Briefcase },
  { label: '文档', route: '/documents', icon: Document },
  { label: '知识库', route: '/knowledge', icon: Collection },
  { label: '行情', route: '/market', icon: TrendCharts },
  { label: 'AI 中心', route: '/ai', icon: Cpu },
  { label: '投资组合', route: '/portfolio', icon: Money },
  { label: '系统状态', route: '/system', icon: Monitor },
]

const activeIndex = computed(() => {
  const idx = navItems.findIndex((item) => route.path.startsWith(item.route))
  return idx >= 0 ? String(idx) : '0'
})

function handleSelect(idx: string) {
  router.push(navItems[Number(idx)].route)
}
</script>

<template>
  <el-menu
    :default-active="activeIndex"
    @select="handleSelect"
    class="sidebar-menu"
    mode="vertical"
  >
    <div class="sidebar-logo">
      <span class="logo-icon">🧠</span>
      <span class="logo-text">AI 投研系统</span>
    </div>
    <el-menu-item v-for="(item, i) in navItems" :key="item.route" :index="String(i)">
      <el-icon><component :is="item.icon" /></el-icon>
      <span>{{ item.label }}</span>
    </el-menu-item>
  </el-menu>
</template>

<style scoped>
.sidebar-menu {
  width: 240px;
  height: 100vh;
  border-right: 1px solid var(--border);
  overflow-y: auto;
  padding-top: 0;
}
.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 20px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
}
.logo-icon {
  font-size: 24px;
}
.logo-text {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}
.sidebar-menu .el-menu-item {
  margin: 2px 8px;
  border-radius: 8px;
}
.sidebar-menu .el-menu-item.is-active {
  background-color: rgba(79, 140, 255, 0.1);
}
</style>
