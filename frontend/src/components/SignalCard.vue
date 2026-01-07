<script setup lang="ts">
import type { Signal } from '@/types'
import dayjs from 'dayjs'

defineProps<{
  signal: Signal
  compact?: boolean
}>()

function formatPrice(price: number | null): string {
  if (price === null) return '--'
  return price.toFixed(2)
}

function formatTime(ts: string): string {
  return dayjs(ts).format('HH:mm:ss')
}

function formatDate(ts: string): string {
  return dayjs(ts).format('MM-DD HH:mm')
}

function getStatusClass(status: string): string {
  switch (status) {
    case 'TP_HIT':
      return 'status-win'
    case 'SL_HIT':
      return 'status-loss'
    case 'PENDING':
      return 'status-pending'
    default:
      return 'status-expired'
  }
}

function getStatusText(status: string): string {
  switch (status) {
    case 'TP_HIT':
      return '止盈'
    case 'SL_HIT':
      return '止损'
    case 'PENDING':
      return '待处理'
    case 'EXPIRED':
      return '已过期'
    default:
      return status
  }
}
</script>

<template>
  <div class="signal-card" :class="{ compact }">
    <div class="signal-header">
      <span class="signal-side" :class="signal.side.toLowerCase()">
        {{ signal.side === 'LONG' ? '做多' : '做空' }}
      </span>
      <span class="signal-time">{{ compact ? formatTime(signal.ts) : formatDate(signal.ts) }}</span>
      <span class="signal-status" :class="getStatusClass(signal.status)">
        {{ getStatusText(signal.status) }}
      </span>
    </div>

    <div class="signal-prices">
      <div class="price-item">
        <span class="label">入场</span>
        <span class="value">{{ formatPrice(signal.entry_price) }}</span>
      </div>
      <div class="price-item tp">
        <span class="label">TP</span>
        <span class="value">{{ formatPrice(signal.tp_price) }}</span>
      </div>
      <div class="price-item sl">
        <span class="label">SL</span>
        <span class="value">{{ formatPrice(signal.sl_price) }}</span>
      </div>
    </div>

    <div v-if="!compact && signal.rationale" class="signal-rationale">
      {{ signal.rationale }}
    </div>

    <div v-if="signal.result_pnl_bps !== null" class="signal-pnl" :class="signal.result_pnl_bps >= 0 ? 'positive' : 'negative'">
      {{ signal.result_pnl_bps >= 0 ? '+' : '' }}{{ signal.result_pnl_bps.toFixed(2) }} bps
    </div>
  </div>
</template>

<style scoped>
.signal-card {
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  padding: 14px 16px;
  border: 1px solid var(--border-card);
  transition: all 0.2s ease;
}

.signal-card:hover {
  border-color: var(--border-accent);
}

.signal-card.compact {
  padding: 12px 14px;
}

.signal-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.signal-side {
  font-weight: 600;
  padding: 5px 12px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.signal-side.long {
  background: var(--success-bg);
  color: var(--success);
}

.signal-side.short {
  background: var(--danger-bg);
  color: var(--danger);
}

.signal-time {
  font-size: 12px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.signal-status {
  margin-left: auto;
  font-size: 11px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
}

.status-win {
  background: var(--success-bg);
  color: var(--success);
}

.status-loss {
  background: var(--danger-bg);
  color: var(--danger);
}

.status-pending {
  background: rgba(245, 158, 11, 0.15);
  color: var(--warning);
}

.status-expired {
  background: rgba(144, 144, 160, 0.1);
  color: var(--text-muted);
}

.signal-prices {
  display: flex;
  gap: 20px;
}

.price-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.price-item .label {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-muted);
}

.price-item .value {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.price-item.tp .value {
  color: var(--success);
}

.price-item.sl .value {
  color: var(--danger);
}

.signal-rationale {
  margin-top: 10px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.signal-pnl {
  margin-top: 10px;
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.signal-pnl.positive {
  color: var(--success);
}

.signal-pnl.negative {
  color: var(--danger);
}

@media (max-width: 768px) {
  .signal-card {
    padding: 12px;
  }
  
  .signal-prices {
    gap: 16px;
  }
  
  .price-item .value {
    font-size: 14px;
  }
}
</style>
