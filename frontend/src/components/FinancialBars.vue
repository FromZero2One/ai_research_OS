<script setup lang="ts">
import { computed } from 'vue'

interface BarItem { label: string; value: number }

const props = withDefaults(defineProps<{
  data: { fiscal_period: string; metric_value: number }[]
  color?: string
  format?: 'num' | 'pct'
}>(), {
  color: '#4f8cff',
  format: 'num',
})

const bars = computed<BarItem[]>(() =>
  props.data.slice(-8).map((d) => ({ label: d.fiscal_period, value: d.metric_value })),
)
const maxValue = computed(() => Math.max(...bars.value.map((b) => b.value), 1))

function formatValue(v: number): string {
  if (props.format === 'pct') return `${(v * 100).toFixed(1)}%`
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`
  return `$${v.toFixed(0)}`
}
</script>

<template>
  <div v-for="b in bars" :key="b.label" class="bar-row">
    <span class="bar-label">{{ b.label }}</span>
    <div class="bar-track">
      <div class="bar-fill" :style="{ width: `${(b.value / maxValue) * 100}%`, backgroundColor: color }" />
    </div>
    <span class="bar-value">{{ formatValue(b.value) }}</span>
  </div>
</template>

<style scoped>
.bar-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; font-size: 12px; }
.bar-label { color: var(--text-secondary); width: 64px; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bar-track { flex: 1; height: 16px; border-radius: 4px; background: var(--bg-tertiary); overflow: hidden; }
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.bar-value { color: var(--text-primary); width: 80px; text-align: right; font-family: monospace; font-size: 11px; }
</style>
