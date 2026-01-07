<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/api'
import type { BacktestRun } from '@/types'
import BacktestForm from '@/components/BacktestForm.vue'
import MetricCard from '@/components/MetricCard.vue'
import SourceSelector from '@/components/SourceSelector.vue'
import TickerSelector from '@/components/TickerSelector.vue'
import { useSettingsStore } from '@/stores/settings'
import dayjs from 'dayjs'

const settings = useSettingsStore()

const formRef = ref<InstanceType<typeof BacktestForm> | null>(null)
const runs = ref<BacktestRun[]>([])
const currentResult = ref<BacktestRun | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

onMounted(async () => {
  await fetchRuns()
})

async function fetchRuns() {
  try {
    const res = await api.listBacktestRuns(20)
    runs.value = res.runs
  } catch (e) {
    console.error('获取回测列表失败:', e)
  }
}

async function handleRunBacktest(params: { start: string; end: string }) {
  loading.value = true
  error.value = null
  try {
    const res = await api.runBacktest(params.start, params.end, settings.currentSource, settings.currentTicker)
    // 获取详细结果
    const result = await api.getBacktestResult(res.run_id)
    currentResult.value = result.run
    await fetchRuns()
  } catch (e) {
    error.value = '回测运行失败'
    console.error(e)
  } finally {
    loading.value = false
    formRef.value?.setLoading(false)
  }
}

async function handleRunWalkForward(params: {
  start: string
  end: string
  trainWindow: number
  testWindow: number
  stepSize: number
}) {
  loading.value = true
  error.value = null
  try {
    const res = await api.runWalkForward(
      params.start,
      params.end,
      params.trainWindow,
      params.testWindow,
      params.stepSize
    )
    // 获取详细结果
    const result = await api.getBacktestResult(res.run_id)
    currentResult.value = result.run
    await fetchRuns()
  } catch (e) {
    error.value = '走步验证运行失败'
    console.error(e)
  } finally {
    loading.value = false
    formRef.value?.setLoading(false)
  }
}

async function loadResult(runId: number) {
  try {
    const result = await api.getBacktestResult(runId)
    currentResult.value = result.run
  } catch (e) {
    console.error('获取回测结果失败:', e)
  }
}

function formatDate(date: string): string {
  return dayjs(date).format('YYYY-MM-DD HH:mm')
}
</script>

<template>
  <div class="backtest-page">
    <!-- 数据源选择器 -->
    <div class="source-selector-row">
      <SourceSelector />
      <TickerSelector />
    </div>

    <div class="backtest-content">
      <!-- 左侧：配置和结果 -->
      <div class="main-section">
        <BacktestForm
          ref="formRef"
          @run-backtest="handleRunBacktest"
          @run-walk-forward="handleRunWalkForward"
        />

        <div v-if="error" class="error-message">
          {{ error }}
        </div>

        <!-- 回测结果 -->
        <div v-if="currentResult" class="result-section">
          <h3>回测结果</h3>

          <div class="result-metrics">
            <MetricCard
              title="总信号数"
              :value="currentResult.total_signals"
            />
            <MetricCard
              title="胜率"
              :value="currentResult.win_rate ? (currentResult.win_rate * 100).toFixed(1) : 0"
              unit="%"
              :trend="(currentResult.win_rate ?? 0) >= 0.5 ? 'up' : 'down'"
            />
            <MetricCard
              title="总盈亏"
              :value="currentResult.total_pnl_bps"
              unit="bps"
              :trend="(currentResult.total_pnl_bps ?? 0) >= 0 ? 'up' : 'down'"
            />
            <MetricCard
              title="最大回撤"
              :value="currentResult.max_drawdown_bps"
              unit="bps"
              trend="down"
            />
            <MetricCard
              title="夏普率"
              :value="currentResult.sharpe_ratio"
              :precision="2"
            />
          </div>

          <div class="result-details">
            <div class="detail-row">
              <span class="label">数据范围</span>
              <span class="value">
                {{ formatDate(currentResult.data_start) }} - {{ formatDate(currentResult.data_end) }}
              </span>
            </div>
            <div class="detail-row">
              <span class="label">盈利次数</span>
              <span class="value positive">{{ currentResult.win_count }}</span>
            </div>
            <div class="detail-row">
              <span class="label">亏损次数</span>
              <span class="value negative">{{ currentResult.loss_count }}</span>
            </div>
            <div class="detail-row">
              <span class="label">平均盈利</span>
              <span class="value positive">{{ currentResult.avg_win_bps?.toFixed(2) ?? '--' }} bps</span>
            </div>
            <div class="detail-row">
              <span class="label">平均亏损</span>
              <span class="value negative">{{ currentResult.avg_loss_bps?.toFixed(2) ?? '--' }} bps</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧：历史记录 -->
      <div class="history-section">
        <h3>历史回测</h3>
        <div class="history-list">
          <div
            v-for="run in runs"
            :key="run.id"
            class="history-item"
            :class="{ active: currentResult?.id === run.id }"
            @click="loadResult(run.id)"
          >
            <div class="history-time">{{ formatDate(run.started_at) }}</div>
            <div class="history-stats">
              <span class="win-rate">
                {{ run.win_rate ? (run.win_rate * 100).toFixed(1) : 0 }}%
              </span>
              <span class="signal-count">{{ run.total_signals }} 信号</span>
            </div>
            <div class="history-pnl" :class="(run.total_pnl_bps ?? 0) >= 0 ? 'positive' : 'negative'">
              {{ (run.total_pnl_bps ?? 0) >= 0 ? '+' : '' }}{{ run.total_pnl_bps?.toFixed(2) ?? 0 }} bps
            </div>
          </div>
          <div v-if="!runs.length" class="empty-state">
            暂无回测记录
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.backtest-page {
  padding: 20px;
}

.source-selector-row {
  display: flex;
  gap: 1rem;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.backtest-content {
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: 20px;
}

@media (max-width: 1024px) {
  .backtest-content {
    grid-template-columns: 1fr;
  }
}

.main-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.error-message {
  background: var(--danger-bg);
  color: var(--danger);
  padding: 14px 18px;
  border-radius: var(--radius-md);
  border: 1px solid rgba(239, 68, 68, 0.25);
  font-size: 14px;
}

.result-section {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  padding: 20px;
  border: 1px solid var(--border-card);
}

.result-section h3 {
  margin: 0 0 18px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.result-metrics {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

@media (min-width: 640px) {
  .result-metrics {
    grid-template-columns: repeat(4, 1fr);
  }
}

.result-details {
  display: flex;
  flex-direction: column;
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
  padding: 4px 0;
}

.detail-row {
  display: flex;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-card);
}

.detail-row:last-child {
  border-bottom: none;
}

.detail-row .label {
  color: var(--text-secondary);
  font-size: 13px;
}

.detail-row .value {
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.positive {
  color: var(--success);
}

.negative {
  color: var(--danger);
}

.history-section {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  padding: 20px;
  border: 1px solid var(--border-card);
  height: fit-content;
}

.history-section h3 {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 500px;
  overflow-y: auto;
}

.history-list::-webkit-scrollbar {
  width: 4px;
}

.history-list::-webkit-scrollbar-track {
  background: transparent;
}

.history-list::-webkit-scrollbar-thumb {
  background: var(--border-accent);
  border-radius: 2px;
}

.history-item {
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
  padding: 14px;
  cursor: pointer;
  border: 1px solid var(--border-card);
  transition: all 0.2s ease;
}

.history-item:hover {
  border-color: var(--border-accent);
}

.history-item.active {
  border-color: var(--accent-blue);
  background: rgba(74, 158, 255, 0.08);
}

.history-time {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
  font-variant-numeric: tabular-nums;
}

.history-stats {
  display: flex;
  gap: 14px;
  margin-bottom: 6px;
  align-items: baseline;
}

.win-rate {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}

.signal-count {
  font-size: 13px;
  color: var(--text-secondary);
}

.history-pnl {
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.empty-state {
  text-align: center;
  color: var(--text-muted);
  padding: 40px 20px;
  font-size: 14px;
}

@media (max-width: 768px) {
  .backtest-page {
    padding: 16px;
  }
  
  .result-section,
  .history-section {
    padding: 16px;
  }
  
  .result-section h3,
  .history-section h3 {
    font-size: 15px;
  }
}
</style>
