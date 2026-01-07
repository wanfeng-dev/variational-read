import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Signal, SignalStats, DataSource, Ticker } from '@/types'
import { api } from '@/api'
import { signalWs } from '@/utils/websocket'
import { useSettingsStore } from './settings'

export const useSignalsStore = defineStore('signals', () => {
  const settings = useSettingsStore()

  // 状态
  const signals = ref<Signal[]>([])
  const latestSignal = ref<Signal | null>(null)
  const stats = ref<SignalStats | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const wsConnected = ref(false)
  const total = ref(0)

  // 筛选条件 - 增加 source 和 ticker
  const filter = ref({
    status: '' as string,
    start: '' as string,
    end: '' as string,
    source: '' as DataSource | '',
    ticker: '' as Ticker | '',
  })

  // 计算属性
  const pendingSignals = computed(() =>
    signals.value.filter((s) => s.status === 'PENDING')
  )
  const winRate = computed(() =>
    stats.value ? (stats.value.win_rate * 100).toFixed(1) : '0'
  )
  const todayPnl = computed(() => stats.value?.avg_pnl_bps ?? 0)

  // 操作
  async function fetchLatestSignal(source?: DataSource, ticker?: Ticker) {
    const s = source ?? settings.currentSource
    const t = ticker ?? settings.currentTicker
    try {
      const res = await api.getLatestSignal(s, t)
      latestSignal.value = res.signal
    } catch (e) {
      error.value = '获取最新信号失败'
      console.error(e)
    }
  }

  async function fetchSignals(params?: {
    start?: string
    end?: string
    status?: string
    limit?: number
    source?: DataSource
    ticker?: Ticker
  }) {
    loading.value = true
    const s = params?.source ?? settings.currentSource
    const t = params?.ticker ?? settings.currentTicker
    try {
      const res = await api.getSignalHistory({ ...params, source: s, ticker: t })
      signals.value = res.signals
      total.value = res.total
    } catch (e) {
      error.value = '获取信号列表失败'
      console.error(e)
    } finally {
      loading.value = false
    }
  }

  async function fetchStats(start?: string, end?: string, source?: DataSource, ticker?: Ticker) {
    const s = source ?? settings.currentSource
    const t = ticker ?? settings.currentTicker
    try {
      stats.value = await api.getSignalStats(start, end, s, t)
    } catch (e) {
      error.value = '获取信号统计失败'
      console.error(e)
    }
  }

  // WebSocket 连接
  async function connectWs(source?: DataSource, ticker?: Ticker) {
    const s = source ?? settings.currentSource
    const t = ticker ?? settings.currentTicker
    try {
      await signalWs.connect()
      wsConnected.value = true

      // 订阅新信号
      signalWs.on<Signal>('signal', (data) => {
        // 只显示当前选中的 source/ticker 的信号
        if (data.source === settings.currentSource && data.ticker === settings.currentTicker) {
          latestSignal.value = data
          signals.value = [data, ...signals.value]
          total.value++
        }
      })

      // 订阅信号关闭
      signalWs.on<Signal>('signal_close', (data) => {
        // 更新信号状态
        const idx = signals.value.findIndex((sig) => sig.id === data.id)
        if (idx !== -1) {
          signals.value[idx] = data
        }
        if (latestSignal.value?.id === data.id) {
          latestSignal.value = data
        }
      })

      signalWs.subscribe('signals', t, s)
    } catch (e) {
      console.error('信号 WebSocket 连接失败:', e)
      wsConnected.value = false
    }
  }

  function disconnectWs() {
    signalWs.disconnect()
    wsConnected.value = false
  }

  // 应用筛选
  async function applyFilter() {
    await fetchSignals({
      status: filter.value.status || undefined,
      start: filter.value.start || undefined,
      end: filter.value.end || undefined,
      source: filter.value.source || undefined,
      ticker: filter.value.ticker || undefined,
      limit: 100,
    })
  }

  // 切换数据源时重新加载
  async function switchSource(source: DataSource, ticker: Ticker) {
    settings.setSource(source)
    settings.setTicker(ticker)
    await Promise.all([fetchLatestSignal(source, ticker), fetchSignals({ source, ticker, limit: 50 }), fetchStats(undefined, undefined, source, ticker)])
    signalWs.subscribe('signals', ticker, source)
  }

  // 初始化
  async function init() {
    await Promise.all([fetchLatestSignal(), fetchSignals({ limit: 50 }), fetchStats()])
    await connectWs()
  }

  return {
    // 状态
    signals,
    latestSignal,
    stats,
    loading,
    error,
    wsConnected,
    total,
    filter,
    // 计算属性
    pendingSignals,
    winRate,
    todayPnl,
    // 操作
    fetchLatestSignal,
    fetchSignals,
    fetchStats,
    connectWs,
    disconnectWs,
    applyFilter,
    switchSource,
    init,
  }
})
