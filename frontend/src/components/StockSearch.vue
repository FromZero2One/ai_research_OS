<script setup lang="ts">
/**
 * StockSearch — reusable stock ticker search with dropdown.
 *
 * Usage:
 *   <StockSearch v-model="ticker" @select="onSelect" />
 *
 *   <StockSearch @select="(s: { symbol: string; name: string }) => { ... }" />
 */
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useStockSearch } from '@/stores/api'

const props = withDefaults(defineProps<{
  modelValue?: string
  placeholder?: string
  size?: '' | 'large' | 'default' | 'small'
}>(), {
  modelValue: '',
  placeholder: '搜索股票代码或名称...',
  size: 'default',
})

const emit = defineEmits<{
  (e: 'update:modelValue', val: string): void
  (e: 'select', item: { symbol: string; name: string }): void
}>()

const searchQ = ref(props.modelValue)
const debouncedQ = ref(props.modelValue)
const showDrop = ref(false)
const highlightIdx = ref(-1)
const wrapRef = ref<HTMLDivElement | null>(null)
let debounceTimer: ReturnType<typeof setTimeout>

const { data: searchData } = useStockSearch(
  computed(() => showDrop.value ? debouncedQ.value : '')
)
const searchResults = computed(() => searchData.value?.results || [])

// Sync internal searchQ with external modelValue
watch(() => props.modelValue, (v) => { searchQ.value = v; debouncedQ.value = v })

// Debounce search: 300ms after last keystroke
watch(searchQ, (v) => {
  highlightIdx.value = -1
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => { debouncedQ.value = v }, 300)
})
watch(searchData, () => { highlightIdx.value = -1 })

function onInput(val: string) {
  searchQ.value = val
  showDrop.value = true
  emit('update:modelValue', val)
}

function handleSelect(symbol: string, name: string) {
  searchQ.value = symbol
  showDrop.value = false
  emit('update:modelValue', symbol)
  emit('select', { symbol, name })
}

function onKeydown(e: KeyboardEvent) {
  if (!showDrop.value) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    highlightIdx.value = Math.min(highlightIdx.value + 1, searchResults.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    highlightIdx.value = Math.max(highlightIdx.value - 1, 0)
  } else if (e.key === 'Enter' && highlightIdx.value >= 0) {
    e.preventDefault()
    const r = searchResults.value[highlightIdx.value]
    if (r) handleSelect(r.symbol, r.name)
  } else if (e.key === 'Escape') {
    showDrop.value = false
  }
}

function onClickOutside(e: MouseEvent) {
  if (wrapRef.value && !wrapRef.value.contains(e.target as Node)) {
    showDrop.value = false
  }
}

onMounted(() => document.addEventListener('mousedown', onClickOutside))
onUnmounted(() => document.removeEventListener('mousedown', onClickOutside))
</script>

<template>
  <div ref="wrapRef" class="stock-search-wrap" @keydown="onKeydown">
    <el-input
      :model-value="searchQ"
      @update:model-value="onInput"
      :placeholder="placeholder"
      :size="size"
      @focus="showDrop = true"
      clearable
    />
    <div v-if="showDrop && searchQ" class="stock-search-dropdown">
      <div v-if="!searchResults.length" class="stock-search-empty">无匹配结果</div>
      <button
        v-for="(r, i) in searchResults"
        :key="r.symbol"
        class="stock-search-item"
        :class="{ active: i === highlightIdx }"
        @click="handleSelect(r.symbol, r.name)"
        @mouseenter="highlightIdx = i"
      >
        <span class="stock-search-symbol">{{ r.symbol }}</span>
        <span v-if="r.name" class="stock-search-name">{{ r.name }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.stock-search-wrap {
  position: relative;
}
.stock-search-dropdown {
  position: absolute;
  z-index: 10;
  width: 100%;
  margin-top: 4px;
  border-radius: 8px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  max-height: 256px;
  overflow-y: auto;
}
.stock-search-empty {
  padding: 12px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 14px;
}
.stock-search-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 12px;
  text-align: left;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
}
.stock-search-item:hover,
.stock-search-item.active {
  background: var(--bg-tertiary);
}
.stock-search-symbol {
  font-family: monospace;
  color: var(--accent);
}
.stock-search-name {
  color: var(--text-primary);
}
</style>
