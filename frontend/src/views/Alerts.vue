<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useAlertsStore } from '@/stores/alerts'
import AlertItem from '@/components/AlertItem.vue'

const store = useAlertsStore()

onMounted(async () => {
  await store.init()
})

onUnmounted(() => {
  store.disconnectWs()
})

function handleAcknowledge(id: number) {
  store.acknowledgeAlert(id)
}

async function handleFilter() {
  await store.applyFilter()
}

function clearFilter() {
  store.filter.type = ''
  store.filter.priority = ''
  store.filter.start = ''
  store.filter.end = ''
  store.fetchAlerts({ limit: 100 })
}
</script>

<template>
  <div class="alerts-page">
    <!-- 头部 -->
    <div class="page-header">
      <h2>
        预警中心
        <span v-if="store.unacknowledgedCount" class="badge">
          {{ store.unacknowledgedCount }} 条未确认
        </span>
      </h2>
      <button
        v-if="store.unacknowledgedCount"
        class="btn-acknowledge-all"
        @click="store.acknowledgeAll"
      >
        全部标记已读
      </button>
    </div>

    <!-- 筛选器 -->
    <div class="filter-section">
      <div class="filter-group">
        <label>类型</label>
        <select v-model="store.filter.type">
          <option value="">全部</option>
          <option value="SIGNAL_NEW">新信号</option>
          <option value="SIGNAL_TP_HIT">止盈</option>
          <option value="SIGNAL_SL_HIT">止损</option>
          <option value="PRICE_SPIKE">价格异动</option>
          <option value="SPREAD_HIGH">点差过高</option>
          <option value="QUOTE_STALE">报价过旧</option>
          <option value="DATA_ERROR">数据异常</option>
        </select>
      </div>
      <div class="filter-group">
        <label>优先级</label>
        <select v-model="store.filter.priority">
          <option value="">全部</option>
          <option value="HIGH">高</option>
          <option value="MEDIUM">中</option>
          <option value="LOW">低</option>
        </select>
      </div>
      <div class="filter-group">
        <label>开始时间</label>
        <input type="datetime-local" v-model="store.filter.start" />
      </div>
      <div class="filter-group">
        <label>结束时间</label>
        <input type="datetime-local" v-model="store.filter.end" />
      </div>
      <div class="filter-actions">
        <button class="btn-primary" @click="handleFilter">筛选</button>
        <button class="btn-secondary" @click="clearFilter">清空</button>
      </div>
    </div>

    <!-- 预警列表 -->
    <div class="alerts-list">
      <template v-if="store.alerts.length">
        <AlertItem
          v-for="alert in store.alerts"
          :key="alert.id"
          :alert="alert"
          @acknowledge="handleAcknowledge"
        />
      </template>
      <div v-else-if="!store.loading" class="empty-state">
        暂无预警数据
      </div>
      <div v-if="store.loading" class="loading-state">
        加载中...
      </div>
    </div>
  </div>
</template>

<style scoped>
.alerts-page {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 12px;
}

.badge {
  background: var(--danger);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  padding: 4px 12px;
  border-radius: var(--radius-full);
}

.btn-acknowledge-all {
  padding: 10px 18px;
  background: var(--success-bg);
  color: var(--success);
  border: 1px solid rgba(34, 197, 94, 0.3);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.2s ease;
}

.btn-acknowledge-all:hover {
  background: rgba(34, 197, 94, 0.25);
  border-color: rgba(34, 197, 94, 0.5);
}

.filter-section {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
  align-items: flex-end;
  background: var(--bg-card);
  padding: 16px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-card);
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.filter-group label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}

.filter-group select,
.filter-group input {
  padding: 10px 14px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-card);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 13px;
  transition: border-color 0.2s ease;
}

.filter-group select:focus,
.filter-group input:focus {
  outline: none;
  border-color: var(--accent-blue);
}

.filter-actions {
  display: flex;
  gap: 8px;
}

.btn-primary,
.btn-secondary {
  padding: 10px 18px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.2s ease;
}

.btn-primary {
  background: var(--accent-blue);
  color: #fff;
}

.btn-primary:hover {
  background: #3d8ee6;
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-secondary);
  border: 1px solid var(--border-card);
}

.btn-secondary:hover {
  border-color: var(--border-accent);
  color: var(--text-primary);
}

.alerts-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.empty-state,
.loading-state {
  text-align: center;
  color: var(--text-muted);
  padding: 60px 20px;
  background: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-card);
  font-size: 14px;
}

@media (max-width: 768px) {
  .alerts-page {
    padding: 16px;
  }
  
  .page-header h2 {
    font-size: 18px;
  }
  
  .filter-section {
    padding: 14px;
  }
}
</style>
