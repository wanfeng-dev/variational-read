<template>
  <div class="source-selector">
    <div class="selector-group">
      <label>数据源</label>
      <div class="btn-group">
        <button
          v-for="source in sources"
          :key="source.value"
          :class="['btn', { active: settings.currentSource === source.value }]"
          @click="selectSource(source.value)"
        >
          <span class="source-label">{{ source.label }}</span>
          <span v-if="sourceStatus[source.value]" class="latency" :class="getLatencyClass(sourceStatus[source.value].latency_ms)">
            {{ sourceStatus[source.value].latency_ms }}ms
          </span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { DataSource, SourceStatus } from '@/types'
import { useSettingsStore } from '@/stores/settings'
import { useMarketStore } from '@/stores/market'
import { useSignalsStore } from '@/stores/signals'
import { api } from '@/api'

const settings = useSettingsStore()
const market = useMarketStore()
const signals = useSignalsStore()

const sources = [
  { value: 'bybit' as DataSource, label: 'Bybit' },
  { value: 'variational' as DataSource, label: 'Variational' },
]

const sourceStatus = ref<Record<string, SourceStatus>>({})

async function fetchSourcesStatus() {
  try {
    const res = await api.getSourcesStatus()
    sourceStatus.value = res.sources
  } catch (e) {
    console.error('获取数据源状态失败:', e)
  }
}

function selectSource(source: DataSource) {
  if (settings.currentSource !== source) {
    market.switchSource(source, settings.currentTicker)
    signals.switchSource(source, settings.currentTicker)
  }
}

function getLatencyClass(latency: number): string {
  if (latency < 100) return 'good'
  if (latency < 500) return 'medium'
  return 'bad'
}

onMounted(() => {
  fetchSourcesStatus()
  // 定期更新状态
  setInterval(fetchSourcesStatus, 30000)
})
</script>

<style scoped>
.source-selector {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.selector-group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.selector-group label {
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.btn-group {
  display: flex;
  gap: 0.25rem;
}

.btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.375rem 0.75rem;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  cursor: pointer;
  transition: all 0.2s;
}

.btn:hover {
  background: var(--bg-hover);
}

.btn.active {
  background: var(--primary-color);
  border-color: var(--primary-color);
  color: white;
}

.latency {
  font-size: 0.75rem;
  padding: 0.125rem 0.375rem;
  border-radius: 3px;
}

.latency.good {
  background: rgba(16, 185, 129, 0.2);
  color: #10b981;
}

.latency.medium {
  background: rgba(245, 158, 11, 0.2);
  color: #f59e0b;
}

.latency.bad {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}
</style>
