<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useSignalsStore } from '@/stores/signals'
import { useSettingsStore } from '@/stores/settings'
import SignalCard from '@/components/SignalCard.vue'
import MetricCard from '@/components/MetricCard.vue'
import SourceSelector from '@/components/SourceSelector.vue'
import TickerSelector from '@/components/TickerSelector.vue'
import dayjs from 'dayjs'

const store = useSignalsStore()
const settings = useSettingsStore()

onMounted(async () => {
  await store.init()
})

onUnmounted(() => {
  store.disconnectWs()
})

function formatDate(date: string): string {
  return dayjs(date).format('YYYY-MM-DD HH:mm:ss')
}

async function handleFilter() {
  await store.applyFilter()
}

function clearFilter() {
  store.filter.status = ''
  store.filter.start = ''
  store.filter.end = ''
  store.fetchSignals({ limit: 100 })
}
</script>

<template>
  <div class="signals-page">
    <!-- 统计卡片 -->
    <div class="stats-row">
      <MetricCard
        title="总信号数"
        :value="store.stats?.total_signals ?? 0"
      />
      <MetricCard
        title="胜率"
        :value="store.winRate"
        unit="%"
        :trend="Number(store.winRate) >= 50 ? 'up' : 'down'"
      />
      <MetricCard
        title="盈利次数"
        :value="store.stats?.win_count ?? 0"
        trend="up"
      />
      <MetricCard
        title="亏损次数"
        :value="store.stats?.loss_count ?? 0"
        trend="down"
      />
      <MetricCard
        title="平均盈亏"
        :value="store.stats?.avg_pnl_bps ?? 0"
        unit="bps"
        :precision="2"
        :trend="(store.stats?.avg_pnl_bps ?? 0) >= 0 ? 'up' : 'down'"
      />
    </div>

    <!-- 数据源选择器 -->
    <div class="source-selector-row">
      <SourceSelector />
      <TickerSelector />
    </div>

    <!-- 筛选器 -->
    <div class="filter-section">
      <div class="filter-group">
        <label>状态</label>
        <select v-model="store.filter.status">
          <option value="">全部</option>
          <option value="PENDING">待处理</option>
          <option value="TP_HIT">止盈</option>
          <option value="SL_HIT">止损</option>
          <option value="EXPIRED">已过期</option>
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

    <!-- 信号列表 -->
    <div class="signals-table">
      <table>
        <thead>
          <tr>
            <th>时间</th>
            <th>方向</th>
            <th>入场价</th>
            <th>止盈</th>
            <th>止损</th>
            <th>状态</th>
            <th>盈亏</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="signal in store.signals" :key="signal.id">
            <td>{{ formatDate(signal.ts) }}</td>
            <td>
              <span class="side-badge" :class="signal.side.toLowerCase()">
                {{ signal.side === 'LONG' ? '做多' : '做空' }}
              </span>
            </td>
            <td>{{ signal.entry_price.toFixed(2) }}</td>
            <td class="tp">{{ signal.tp_price.toFixed(2) }}</td>
            <td class="sl">{{ signal.sl_price.toFixed(2) }}</td>
            <td>
              <span class="status-badge" :class="signal.status.toLowerCase().replace('_', '-')">
                {{ signal.status === 'TP_HIT' ? '止盈' : signal.status === 'SL_HIT' ? '止损' : signal.status === 'PENDING' ? '待处理' : '已过期' }}
              </span>
            </td>
            <td :class="signal.result_pnl_bps !== null ? (signal.result_pnl_bps >= 0 ? 'positive' : 'negative') : ''">
              {{ signal.result_pnl_bps !== null ? `${signal.result_pnl_bps >= 0 ? '+' : ''}${signal.result_pnl_bps.toFixed(2)} bps` : '--' }}
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!store.signals.length && !store.loading" class="empty-state">
        暂无信号数据
      </div>
      <div v-if="store.loading" class="loading-state">
        加载中...
      </div>
    </div>

    <!-- 信号卡片列表（移动端） -->
    <div class="signals-cards">
      <SignalCard
        v-for="signal in store.signals"
        :key="signal.id"
        :signal="signal"
      />
    </div>
  </div>
</template>

<style scoped>
.signals-page {
  padding: 20px;
}

.source-selector-row {
  display: flex;
  gap: 1rem;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

@media (min-width: 768px) {
  .stats-row {
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
  }
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

.signals-table {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 1px solid var(--border-card);
}

.signals-table table {
  width: 100%;
  border-collapse: collapse;
}

.signals-table th,
.signals-table td {
  padding: 14px 16px;
  text-align: left;
  border-bottom: 1px solid var(--border-card);
}

.signals-table th {
  background: var(--bg-secondary);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}

.signals-table td {
  font-size: 13px;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.signals-table tr:hover td {
  background: var(--bg-card-hover);
}

.side-badge {
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 600;
}

.side-badge.long {
  background: var(--success-bg);
  color: var(--success);
}

.side-badge.short {
  background: var(--danger-bg);
  color: var(--danger);
}

.status-badge {
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  font-weight: 500;
}

.status-badge.tp-hit {
  background: var(--success-bg);
  color: var(--success);
}

.status-badge.sl-hit {
  background: var(--danger-bg);
  color: var(--danger);
}

.status-badge.pending {
  background: rgba(245, 158, 11, 0.15);
  color: var(--warning);
}

.status-badge.expired {
  background: rgba(90, 106, 122, 0.15);
  color: var(--text-muted);
}

.tp { color: var(--success); }
.sl { color: var(--danger); }
.positive { color: var(--success); }
.negative { color: var(--danger); }

.empty-state,
.loading-state {
  text-align: center;
  color: var(--text-muted);
  padding: 60px 20px;
  font-size: 14px;
}

.signals-cards {
  display: none;
}

@media (max-width: 768px) {
  .signals-page {
    padding: 16px;
  }
  
  .filter-section {
    padding: 14px;
  }
  
  .signals-table {
    display: none;
  }

  .signals-cards {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
}
</style>
