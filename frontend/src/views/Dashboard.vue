<script setup lang="ts">
import { onMounted, onUnmounted, computed, watch, ref } from 'vue'
import { useMarketStore } from '@/stores/market'
import { useSignalsStore } from '@/stores/signals'
import { useAlertsStore } from '@/stores/alerts'
import { useSettingsStore } from '@/stores/settings'
import MetricCard from '@/components/MetricCard.vue'
import PriceChart from '@/components/PriceChart.vue'
import SignalCard from '@/components/SignalCard.vue'
import AlertItem from '@/components/AlertItem.vue'
import SourceSelector from '@/components/SourceSelector.vue'
import TickerSelector from '@/components/TickerSelector.vue'

const marketStore = useMarketStore()
const signalsStore = useSignalsStore()
const alertsStore = useAlertsStore()
const settings = useSettingsStore()

// K线周期选项
const intervals = [
  { label: '1m', value: '1' },
  { label: '5m', value: '5' },
  { label: '15m', value: '15' },
  { label: '1H', value: '60' },
  { label: '4H', value: '240' },
]
const selectedInterval = ref('1')

// 统计数据
const stats = computed(() => ({
  totalSignals: signalsStore.signals.length,
  winRate: signalsStore.winRate,
  avgPnl: signalsStore.avgPnl,
  bestSignal: signalsStore.signals.find(s => s.status === 'TP_HIT'),
}))

onMounted(async () => {
  await Promise.all([
    marketStore.init(),
    signalsStore.init(),
    alertsStore.init(),
  ])
  await marketStore.fetchSnapshots(200)
  // Bybit 源加载 K 线数据
  if (settings.currentSource === 'bybit') {
    await marketStore.fetchKlines(settings.currentTicker, selectedInterval.value)
  }
})

// 监听数据源切换
watch(() => settings.currentSource, async (source) => {
  if (source === 'bybit') {
    await marketStore.fetchKlines(settings.currentTicker, selectedInterval.value)
  }
})

// 切换周期
async function changeInterval(interval: string) {
  selectedInterval.value = interval
  if (settings.currentSource === 'bybit') {
    await marketStore.fetchKlines(settings.currentTicker, interval)
  }
}

onUnmounted(() => {
  marketStore.disconnectWs()
  signalsStore.disconnectWs()
  alertsStore.disconnectWs()
})

function handleAcknowledge(id: number) {
  alertsStore.acknowledgeAlert(id)
}

function refresh() {
  marketStore.fetchSnapshots(200)
  signalsStore.fetchSignals()
  alertsStore.fetchAlerts()
}
</script>

<template>
  <div class="dashboard">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-text">
        <h1>{{ settings.currentSource.toUpperCase() }} {{ settings.currentTicker }} Trading</h1>
        <p>高胜率交易信号系统，实时监控多个数据源</p>
      </div>
    </div>

    <!-- 指标卡片网格 -->
    <div class="metrics-grid">
      <MetricCard
        title="当前价格"
        :value="marketStore.currentPrice"
        unit="USD"
        :precision="2"
      />
      <MetricCard
        title="信号数量"
        :value="stats.totalSignals"
        highlight
      />
      <MetricCard
        title="胜率"
        :value="stats.winRate ? stats.winRate * 100 : null"
        unit="%"
        :precision="2"
        :badge="stats.winRate && stats.winRate > 0.6 ? '高胜率' : undefined"
        badge-color="success"
      />
      <MetricCard
        title="最佳机会"
        :value="stats.bestSignal?.side === 'LONG' ? 'ETH-LONG' : (stats.bestSignal?.side === 'SHORT' ? 'ETH-SHORT' : 'ETH-PERP')"
        :badge="stats.avgPnl ? `${stats.avgPnl > 0 ? '+' : ''}${(stats.avgPnl).toFixed(1)}%` : undefined"
        :badge-color="stats.avgPnl && stats.avgPnl > 0 ? 'success' : 'danger'"
      />
    </div>

    <!-- 数据源选择器 -->
    <div class="source-tags">
      <SourceSelector />
      <TickerSelector />
      <button class="refresh-btn" @click="refresh">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
        </svg>
        Refresh
      </button>
    </div>

    <!-- 图表区域 -->
    <div class="chart-section">
      <div class="section-header">
        <h2>{{ settings.currentTicker }} 价格走势</h2>
        <div class="time-filters" v-if="settings.currentSource === 'bybit'">
          <button 
            v-for="i in intervals" 
            :key="i.value"
            class="time-btn" 
            :class="{ active: selectedInterval === i.value }"
            @click="changeInterval(i.value)"
          >
            {{ i.label }}
          </button>
        </div>
        <div class="time-filters" v-else>
          <button class="time-btn active">10s</button>
        </div>
      </div>
      <PriceChart
        :snapshots="marketStore.snapshots"
        :klines="marketStore.klines"
        :signals="signalsStore.pendingSignals"
        :height="320"
        :ticker="settings.currentTicker"
        :source="settings.currentSource"
        :interval="selectedInterval"
      />
    </div>

    <!-- 下半部分：信号和预警 -->
    <div class="bottom-grid">
      <!-- 最新信号 -->
      <div class="panel">
        <div class="panel-header">
          <h3>最新信号</h3>
          <router-link to="/signals" class="view-all">查看全部 →</router-link>
        </div>
        <div class="panel-content">
          <template v-if="signalsStore.signals.length">
            <SignalCard
              v-for="signal in signalsStore.signals.slice(0, 4)"
              :key="signal.id"
              :signal="signal"
              compact
            />
          </template>
          <div v-else class="empty-state">
            <span>📈</span>
            <p>暂无信号</p>
          </div>
        </div>
      </div>

      <!-- 最新预警 -->
      <div class="panel">
        <div class="panel-header">
          <h3>
            最新预警
            <span v-if="alertsStore.unacknowledgedCount" class="count-badge">
              {{ alertsStore.unacknowledgedCount }}
            </span>
          </h3>
          <router-link to="/alerts" class="view-all">查看全部 →</router-link>
        </div>
        <div class="panel-content">
          <template v-if="alertsStore.recentAlerts.length">
            <AlertItem
              v-for="alert in alertsStore.recentAlerts.slice(0, 4)"
              :key="alert.id"
              :alert="alert"
              @acknowledge="handleAcknowledge"
            />
          </template>
          <div v-else class="empty-state">
            <span>🔔</span>
            <p>暂无预警</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard {
  padding: 20px;
}

/* 页面标题 */
.page-header {
  margin-bottom: 24px;
}

.header-text h1 {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 6px;
}

.header-text p {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
}

/* 指标卡片网格 - 2x2 布局 */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

@media (min-width: 768px) {
  .metrics-grid {
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
  }
}

/* 数据源标签 */
.source-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 20px;
  align-items: center;
}

.tag {
  padding: 10px 16px;
  border-radius: var(--radius-full);
  font-size: 13px;
  font-weight: 500;
  background: var(--bg-card);
  color: var(--text-secondary);
  border: 1px solid var(--border-card);
  cursor: pointer;
  transition: all 0.2s ease;
}

.tag:hover {
  border-color: var(--border-accent);
  color: var(--text-primary);
}

.tag.active {
  background: var(--accent-blue);
  border-color: var(--accent-blue);
  color: #fff;
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-radius: var(--radius-full);
  font-size: 13px;
  font-weight: 500;
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-card);
  cursor: pointer;
  transition: all 0.2s ease;
  margin-left: auto;
}

.refresh-btn:hover {
  border-color: var(--border-accent);
  color: var(--text-primary);
}

.refresh-btn svg {
  width: 16px;
  height: 16px;
}

/* 图表区域 */
.chart-section {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-card);
  padding: 20px;
  margin-bottom: 20px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header h2 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.time-filters {
  display: flex;
  gap: 4px;
}

.time-btn {
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 500;
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-card);
  cursor: pointer;
  transition: all 0.2s ease;
}

.time-btn:hover {
  border-color: var(--border-accent);
  color: var(--text-primary);
}

.time-btn.active {
  background: var(--accent-blue);
  border-color: var(--accent-blue);
  color: #fff;
}

/* 下半部分网格 */
.bottom-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}

@media (min-width: 768px) {
  .bottom-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* 面板 */
.panel {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-card);
  padding: 16px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.panel-header h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.count-badge {
  background: var(--danger);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  min-width: 20px;
  text-align: center;
}

.view-all {
  color: var(--accent-blue);
  font-size: 13px;
  font-weight: 500;
  transition: opacity 0.2s ease;
}

.view-all:hover {
  opacity: 0.8;
}

.panel-content {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: var(--text-muted);
}

.empty-state span {
  font-size: 32px;
  margin-bottom: 12px;
  opacity: 0.5;
}

.empty-state p {
  font-size: 14px;
  margin: 0;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .dashboard {
    padding: 16px;
  }
  
  .page-header {
    margin-bottom: 20px;
  }
  
  .header-text h1 {
    font-size: 20px;
  }
  
  .header-text p {
    font-size: 13px;
  }
  
  .source-tags {
    gap: 6px;
  }
  
  .tag {
    padding: 8px 12px;
    font-size: 12px;
  }
  
  .refresh-btn {
    padding: 8px 12px;
    font-size: 12px;
  }
  
  .chart-section {
    padding: 16px;
  }
  
  .section-header h2 {
    font-size: 14px;
  }
}
</style>
