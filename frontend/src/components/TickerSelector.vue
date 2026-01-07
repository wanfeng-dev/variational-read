<template>
  <div class="ticker-selector">
    <div class="selector-group">
      <label>标的</label>
      <div class="btn-group">
        <button
          v-for="ticker in tickers"
          :key="ticker.value"
          :class="['btn', { active: settings.currentTicker === ticker.value }]"
          @click="selectTicker(ticker.value)"
        >
          {{ ticker.label }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Ticker } from '@/types'
import { useSettingsStore } from '@/stores/settings'
import { useMarketStore } from '@/stores/market'
import { useSignalsStore } from '@/stores/signals'

const settings = useSettingsStore()
const market = useMarketStore()
const signals = useSignalsStore()

const tickers = [
  { value: 'BTC' as Ticker, label: 'BTC' },
  { value: 'ETH' as Ticker, label: 'ETH' },
]

function selectTicker(ticker: Ticker) {
  if (settings.currentTicker !== ticker) {
    market.switchSource(settings.currentSource, ticker)
    signals.switchSource(settings.currentSource, ticker)
  }
}
</script>

<style scoped>
.ticker-selector {
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
  padding: 0.375rem 0.75rem;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  cursor: pointer;
  font-weight: 500;
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
</style>
