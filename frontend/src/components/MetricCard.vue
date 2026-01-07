<script setup lang="ts">
defineProps<{
  title: string
  value: string | number | null
  unit?: string
  trend?: 'up' | 'down' | 'neutral'
  precision?: number
  highlight?: boolean
  badge?: string | number
  badgeColor?: 'success' | 'danger' | 'warning'
}>()

function formatValue(val: string | number | null, precision = 2): string {
  if (val === null || val === undefined) return '--'
  if (typeof val === 'string') return val
  if (Math.abs(val) >= 1000000) {
    return (val / 1000000).toFixed(2) + 'M'
  }
  if (Math.abs(val) >= 1000) {
    return (val / 1000).toFixed(2) + 'K'
  }
  return val.toFixed(precision)
}
</script>

<template>
  <div class="metric-card" :class="{ highlight }">
    <div class="metric-value" :class="trend">
      {{ formatValue(value, precision) }}
    </div>
    <div class="metric-title">
      <span class="title-text">{{ title }}</span>
      <span v-if="unit" class="unit">({{ unit }})</span>
      <svg class="info-icon" viewBox="0 0 16 16" fill="currentColor">
        <circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="1" fill="none" opacity="0.4"/>
        <text x="8" y="11" text-anchor="middle" font-size="9" font-weight="500">i</text>
      </svg>
    </div>
    <div v-if="badge" class="badge" :class="badgeColor">
      {{ badge }}
    </div>
    <span v-if="trend === 'up'" class="trend-icon up">↑</span>
    <span v-else-if="trend === 'down'" class="trend-icon down">↓</span>
  </div>
</template>

<style scoped>
.metric-card {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  padding: 20px;
  min-width: 140px;
  border: 1px solid var(--border-card);
  transition: all 0.2s ease;
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.metric-card:hover {
  border-color: var(--border-accent);
}

.metric-card.highlight {
  border-color: var(--accent-blue);
}

.metric-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}

.metric-value.up {
  color: var(--success);
}

.metric-value.down {
  color: var(--danger);
}

.metric-title {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: var(--text-secondary);
}

.title-text {
  font-weight: 400;
}

.unit {
  color: var(--text-muted);
  font-size: 12px;
}

.info-icon {
  width: 14px;
  height: 14px;
  color: var(--text-muted);
  opacity: 0.6;
  margin-left: 2px;
  flex-shrink: 0;
}

.badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 600;
  width: fit-content;
  margin-top: 4px;
}

.badge.success {
  background: var(--success-bg);
  color: var(--success);
}

.badge.danger {
  background: var(--danger-bg);
  color: var(--danger);
}

.badge.warning {
  background: rgba(245, 158, 11, 0.15);
  color: var(--warning);
}

.trend-icon {
  position: absolute;
  top: 12px;
  right: 12px;
  font-size: 14px;
  font-weight: 600;
}

.trend-icon.up {
  color: var(--success);
}

.trend-icon.down {
  color: var(--danger);
}

@media (max-width: 768px) {
  .metric-card {
    padding: 16px;
  }
  
  .metric-value {
    font-size: 24px;
  }
  
  .metric-title {
    font-size: 12px;
  }
}
</style>
