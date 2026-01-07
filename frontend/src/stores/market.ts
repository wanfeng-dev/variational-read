import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Snapshot, Feature, DataSource, Ticker } from '@/types'
import { api, type KlineData } from '@/api'
import { snapshotWs } from '@/utils/websocket'
import { useSettingsStore } from './settings'

export const useMarketStore = defineStore('market', () => {
  const settings = useSettingsStore()

  // 状态 - 按 source-ticker 键存储
  const latestSnapshots = ref<Map<string, Snapshot>>(new Map())
  const latestFeatures = ref<Map<string, Feature>>(new Map())
  const snapshotsMap = ref<Map<string, Snapshot[]>>(new Map())
  const featuresMap = ref<Map<string, Feature[]>>(new Map())
  
  // K线数据 - 按 ticker-interval 键存储
  const klinesMap = ref<Map<string, KlineData[]>>(new Map())
  const currentInterval = ref<string>('1')
  
  const loading = ref(false)
  const error = ref<string | null>(null)
  const wsConnected = ref(false)

  // 辅助函数
  function getKey(source: DataSource, ticker: Ticker): string {
    return `${source}-${ticker}`
  }

  // 当前选中的数据
  const latestSnapshot = computed(() => {
    const key = settings.getCurrentKey()
    return latestSnapshots.value.get(key) ?? null
  })

  const latestFeature = computed(() => {
    const key = settings.getCurrentKey()
    return latestFeatures.value.get(key) ?? null
  })

  const snapshots = computed(() => {
    const key = settings.getCurrentKey()
    return snapshotsMap.value.get(key) ?? []
  })

  const features = computed(() => {
    const key = settings.getCurrentKey()
    return featuresMap.value.get(key) ?? []
  })

  // K线数据
  const klines = computed(() => {
    const key = `${settings.currentTicker}-${currentInterval.value}`
    return klinesMap.value.get(key) ?? []
  })

  // 计算属性
  const currentPrice = computed(() => latestSnapshot.value?.mid ?? null)
  const spreadBps = computed(() => latestSnapshot.value?.spread_bps ?? null)
  const fundingRate = computed(() => latestSnapshot.value?.funding_rate ?? null)
  const volume24h = computed(() => latestSnapshot.value?.volume_24h ?? null)
  const longShortRatio = computed(() => {
    const snap = latestSnapshot.value
    if (!snap?.long_oi || !snap?.short_oi) return null
    return snap.long_oi / snap.short_oi
  })
  const rsi = computed(() => latestFeature.value?.rsi_14 ?? null)
  const rangeHigh = computed(() => latestFeature.value?.range_high_20m ?? null)
  const rangeLow = computed(() => latestFeature.value?.range_low_20m ?? null)

  // 操作
  async function fetchLatestSnapshot(source?: DataSource, ticker?: Ticker) {
    const s = source ?? settings.currentSource
    const t = ticker ?? settings.currentTicker
    const key = getKey(s, t)
    try {
      const res = await api.getLatestSnapshot(s, t)
      if (res.snapshot) {
        latestSnapshots.value.set(key, res.snapshot)
      }
    } catch (e) {
      error.value = '获取最新快照失败'
      console.error(e)
    }
  }

  async function fetchLatestFeature(source?: DataSource, ticker?: Ticker) {
    const s = source ?? settings.currentSource
    const t = ticker ?? settings.currentTicker
    const key = getKey(s, t)
    try {
      const res = await api.getLatestFeature(s, t)
      if (res.feature) {
        latestFeatures.value.set(key, res.feature)
      }
    } catch (e) {
      error.value = '获取最新特征失败'
      console.error(e)
    }
  }

  async function fetchSnapshots(limit = 100, source?: DataSource, ticker?: Ticker) {
    const s = source ?? settings.currentSource
    const t = ticker ?? settings.currentTicker
    const key = getKey(s, t)
    loading.value = true
    try {
      const res = await api.getSnapshots(limit, s, t)
      snapshotsMap.value.set(key, res.snapshots)
    } catch (e) {
      error.value = '获取快照列表失败'
      console.error(e)
    } finally {
      loading.value = false
    }
  }

  async function fetchFeatures(limit = 100, start?: string, end?: string, source?: DataSource, ticker?: Ticker) {
    const s = source ?? settings.currentSource
    const t = ticker ?? settings.currentTicker
    const key = getKey(s, t)
    loading.value = true
    try {
      const res = await api.getFeatureHistory(t, start, end, limit, s)
      featuresMap.value.set(key, res.features)
    } catch (e) {
      error.value = '获取特征历史失败'
      console.error(e)
    } finally {
      loading.value = false
    }
  }

  // 获取 K 线数据 (Bybit)
  async function fetchKlines(ticker?: Ticker, interval: string = '1', limit: number = 200) {
    const t = ticker ?? settings.currentTicker
    const key = `${t}-${interval}`
    loading.value = true
    try {
      const res = await api.getKlines(t, interval, limit)
      klinesMap.value.set(key, res.klines)
      currentInterval.value = interval
    } catch (e) {
      error.value = '获取K线数据失败'
      console.error(e)
    } finally {
      loading.value = false
    }
  }

  // 切换 K 线周期
  async function setInterval(interval: string) {
    currentInterval.value = interval
    // Bybit 源才获取 K 线
    if (settings.currentSource === 'bybit') {
      await fetchKlines(settings.currentTicker, interval)
    }
  }

  // WebSocket 连接
  async function connectWs(source?: DataSource, ticker?: Ticker) {
    const s = source ?? settings.currentSource
    const t = ticker ?? settings.currentTicker
    try {
      await snapshotWs.connect()
      wsConnected.value = true

      // 订阅快照更新
      snapshotWs.on<Snapshot>('snapshot', (data) => {
        const dataKey = getKey(data.source, data.ticker as Ticker)
        latestSnapshots.value.set(dataKey, data)
        // 更新列表（保持最新在前）
        const currentList = snapshotsMap.value.get(dataKey) ?? []
        snapshotsMap.value.set(dataKey, [data, ...currentList.slice(0, 99)])
      })

      snapshotWs.subscribe('snapshots', t, s)
    } catch (e) {
      console.error('WebSocket 连接失败:', e)
      wsConnected.value = false
    }
  }

  function disconnectWs() {
    snapshotWs.disconnect()
    wsConnected.value = false
  }

  // 切换数据源时重新订阅
  async function switchSource(source: DataSource, ticker: Ticker) {
    settings.setSource(source)
    settings.setTicker(ticker)
    await Promise.all([fetchLatestSnapshot(source, ticker), fetchLatestFeature(source, ticker)])
    // 重新订阅 WebSocket
    snapshotWs.subscribe('snapshots', ticker, source)
  }

  // 初始化
  async function init() {
    await Promise.all([fetchLatestSnapshot(), fetchLatestFeature()])
    await connectWs()
  }

  return {
    // 状态
    latestSnapshot,
    latestFeature,
    snapshots,
    features,
    klines,
    currentInterval,
    latestSnapshots,
    latestFeatures,
    loading,
    error,
    wsConnected,
    // 计算属性
    currentPrice,
    spreadBps,
    fundingRate,
    volume24h,
    longShortRatio,
    rsi,
    rangeHigh,
    rangeLow,
    // 操作
    fetchLatestSnapshot,
    fetchLatestFeature,
    fetchSnapshots,
    fetchFeatures,
    fetchKlines,
    setInterval,
    connectWs,
    disconnectWs,
    switchSource,
    init,
  }
})
