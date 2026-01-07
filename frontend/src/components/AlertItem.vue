<script setup lang="ts">
import type { Alert } from '@/types'
import dayjs from 'dayjs'

const props = defineProps<{
  alert: Alert
}>()

const emit = defineEmits<{
  acknowledge: [id: number]
}>()

function formatTime(ts: string): string {
  return dayjs(ts).format('MM-DD HH:mm:ss')
}

function getPriorityClass(priority: string): string {
  switch (priority) {
    case 'HIGH':
      return 'priority-high'
    case 'MEDIUM':
      return 'priority-medium'
    case 'LOW':
      return 'priority-low'
    default:
      return ''
  }
}

function getTypeIcon(type: string): string {
  if (type.startsWith('SIGNAL')) return '📊'
  if (type.startsWith('PRICE')) return '💹'
  if (type.startsWith('SPREAD')) return '📈'
  if (type.startsWith('DATA')) return '⚠️'
  if (type.startsWith('QUOTE')) return '⏱️'
  return '🔔'
}

function handleAcknowledge() {
  emit('acknowledge', props.alert.id)
}
</script>

<template>
  <div class="alert-item" :class="[getPriorityClass(alert.priority), { acknowledged: alert.acknowledged }]">
    <div class="alert-icon">{{ getTypeIcon(alert.type) }}</div>
    <div class="alert-content">
      <div class="alert-header">
        <span class="alert-type">{{ alert.type }}</span>
        <span class="alert-priority" :class="getPriorityClass(alert.priority)">
          {{ alert.priority }}
        </span>
        <span class="alert-time">{{ formatTime(alert.ts) }}</span>
      </div>
      <div class="alert-message">{{ alert.message }}</div>
    </div>
    <button
      v-if="!alert.acknowledged"
      class="btn-acknowledge"
      @click="handleAcknowledge"
      title="确认"
    >
      ✓
    </button>
    <span v-else class="acknowledged-badge">已确认</span>
  </div>
</template>

<style scoped>
.alert-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 14px;
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-card);
  transition: all 0.2s ease;
}

.alert-item:hover {
  border-color: var(--border-accent);
}

.alert-item.acknowledged {
  opacity: 0.5;
}

.alert-item.priority-high {
  border-left: 3px solid var(--danger);
}

.alert-item.priority-medium {
  border-left: 3px solid var(--warning);
}

.alert-item.priority-low {
  border-left: 3px solid var(--accent-blue);
}

.alert-icon {
  font-size: 18px;
  flex-shrink: 0;
  margin-top: 2px;
}

.alert-content {
  flex: 1;
  min-width: 0;
}

.alert-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.alert-type {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.alert-priority {
  font-size: 10px;
  font-weight: 500;
  padding: 3px 8px;
  border-radius: var(--radius-sm);
}

.alert-priority.priority-high {
  background: var(--danger-bg);
  color: var(--danger);
}

.alert-priority.priority-medium {
  background: rgba(245, 158, 11, 0.15);
  color: var(--warning);
}

.alert-priority.priority-low {
  background: rgba(74, 158, 255, 0.15);
  color: var(--accent-blue);
}

.alert-time {
  font-size: 11px;
  color: var(--text-muted);
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}

.alert-message {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.btn-acknowledge {
  background: var(--success-bg);
  color: var(--success);
  border: none;
  border-radius: var(--radius-sm);
  width: 30px;
  height: 30px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.15s ease;
  font-size: 14px;
}

.btn-acknowledge:hover {
  background: rgba(34, 197, 94, 0.25);
  transform: scale(1.05);
}

.acknowledged-badge {
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}

@media (max-width: 768px) {
  .alert-item {
    padding: 10px 12px;
  }
  
  .alert-type {
    font-size: 12px;
  }
  
  .alert-message {
    font-size: 12px;
  }
}
</style>
