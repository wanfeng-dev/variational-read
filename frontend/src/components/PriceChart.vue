<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import * as echarts from 'echarts'
import type { Snapshot, Signal } from '@/types'
import type { KlineData } from '@/api'

const props = defineProps<{
  snapshots: Snapshot[]
  klines?: KlineData[]
  signals?: Signal[]
  height?: number
  ticker?: string
  source?: string
  interval?: string
}>()

const chartRef = ref<HTMLDivElement | null>(null)
let chartInstance: echarts.ECharts | null = null

// 鼠标悬停的 OHLC 数据
const hoverData = ref<{
  time: string
  open: number
  high: number
  low: number
  close: number
  change: number
  changePercent: number
} | null>(null)

// 是否使用 K 线 API 数据
const useKlineApi = computed(() => props.source === 'bybit' && props.klines && props.klines.length > 0)

// 从 Bybit K 线数据生成图表数据
const klineApiData = computed(() => {
  if (!props.klines?.length) return { times: [], klineData: [], volumes: [], lastPrice: 0, lastData: null }

  const times: string[] = []
  const klineData: number[][] = [] // [open, close, low, high]
  const volumes: number[] = []

  // Bybit K 线数据已按时间升序排列
  props.klines.forEach((k) => {
    const date = new Date(k.time)  // time 是时间戳 (ms)
    times.push(
      date.toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
      })
    )
    klineData.push([k.open, k.close, k.low, k.high])
    volumes.push(k.volume / 1000000)
  })

  const lastPrice = klineData.length > 0 ? klineData[klineData.length - 1][1] : 0
  const lastData = klineData.length > 0 ? {
    time: times[times.length - 1],
    open: klineData[klineData.length - 1][0],
    high: klineData[klineData.length - 1][3],
    low: klineData[klineData.length - 1][2],
    close: klineData[klineData.length - 1][1],
  } : null

  return { times, klineData, volumes, lastPrice, lastData }
})

// 从快照数据聚合为 K 线数据（Variational）
const snapshotAggData = computed(() => {
  if (!props.snapshots.length) return { times: [], klineData: [], volumes: [], lastPrice: 0, lastData: null }

  // 按时间升序排列
  const sorted = [...props.snapshots].sort(
    (a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime()
  )

  // 按 10 秒窗口聚合数据
  const INTERVAL_MS = 10000
  const buckets: Map<number, Snapshot[]> = new Map()

  sorted.forEach((snap) => {
    if (!snap.mid) return
    const ts = new Date(snap.ts).getTime()
    const bucketKey = Math.floor(ts / INTERVAL_MS) * INTERVAL_MS
    if (!buckets.has(bucketKey)) {
      buckets.set(bucketKey, [])
    }
    buckets.get(bucketKey)!.push(snap)
  })

  const times: string[] = []
  const klineData: number[][] = [] // [open, close, low, high]
  const volumes: number[] = []

  // 按时间顺序处理每个桶
  const sortedKeys = Array.from(buckets.keys()).sort((a, b) => a - b)

  sortedKeys.forEach((key) => {
    const snaps = buckets.get(key)!
    if (snaps.length === 0) return

    const open = snaps[0].mid!
    const close = snaps[snaps.length - 1].mid!
    const prices = snaps.map((s) => s.mid!)
    const low = Math.min(...prices)
    const high = Math.max(...prices)
    const volume = snaps.reduce((sum, s) => sum + (s.volume_24h || 0), 0) / snaps.length

    times.push(
      new Date(key).toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    )
    klineData.push([open, close, low, high])
    volumes.push(volume / 1000000)
  })

  const lastPrice = klineData.length > 0 ? klineData[klineData.length - 1][1] : 0
  const lastData = klineData.length > 0 ? {
    time: times[times.length - 1],
    open: klineData[klineData.length - 1][0],
    high: klineData[klineData.length - 1][3],
    low: klineData[klineData.length - 1][2],
    close: klineData[klineData.length - 1][1],
  } : null

  return { times, klineData, volumes, lastPrice, lastData }
})

// 统一的图表数据
const chartData = computed(() => {
  return useKlineApi.value ? klineApiData.value : snapshotAggData.value
})

// 获取周期显示文本
const intervalText = computed(() => {
  if (props.source === 'bybit') {
    const map: Record<string, string> = {
      '1': '1m', '3': '3m', '5': '5m', '15': '15m', '30': '30m',
      '60': '1H', '120': '2H', '240': '4H', 'D': '1D', 'W': '1W'
    }
    return map[props.interval || '1'] || '1m'
  }
  return '10s'
})

// 显示的 OHLC 数据（鼠标悬停时显示悬停位置，否则显示最新）
const displayData = computed(() => {
  if (hoverData.value) return hoverData.value
  const { lastData } = chartData.value
  if (!lastData) return null
  const change = lastData.close - lastData.open
  const changePercent = lastData.open > 0 ? (change / lastData.open) * 100 : 0
  return {
    ...lastData,
    change,
    changePercent,
  }
})

// 信号标记
const signalMarkers = computed(() => {
  if (!props.signals?.length) return []

  return props.signals.map((signal) => ({
    name: signal.side === 'LONG' ? '做多' : '做空',
    coord: [
      new Date(signal.ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      signal.entry_price,
    ],
    value: signal.entry_price.toFixed(2),
    itemStyle: {
      color: signal.side === 'LONG' ? '#26a69a' : '#ef5350',
    },
    symbol: signal.side === 'LONG' ? 'triangle' : 'pin',
    symbolSize: 14,
    symbolRotate: signal.side === 'LONG' ? 0 : 180,
  }))
})

// 格式化价格
function formatPrice(num: number): string {
  if (num >= 10000) return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (num >= 1000) return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return num.toFixed(2)
}

function initChart() {
  if (!chartRef.value) return

  chartInstance = echarts.init(chartRef.value, 'dark')
  updateChart()

  // 响应窗口大小变化
  window.addEventListener('resize', handleResize)
}

function updateChart() {
  if (!chartInstance) return

  const { times, klineData, volumes, lastPrice } = chartData.value

  // TradingView 风格颜色
  const upColor = '#26a69a'
  const downColor = '#ef5350'

  const option: echarts.EChartsOption = {
    backgroundColor: 'transparent',
    animation: false,
    grid: {
      left: 10,
      right: 60,
      top: 10,
      bottom: 30,
      containLabel: false,
    },
    tooltip: {
      show: false, // 禁用默认 tooltip，使用顶部 OHLC 显示
    },
    axisPointer: {
      link: [{ xAxisIndex: 'all' }],
      label: {
        backgroundColor: '#363a45',
        color: '#d1d4dc',
        fontSize: 11,
      },
    },
    xAxis: {
      type: 'category',
      data: times,
      axisLine: { lineStyle: { color: '#363a45' } },
      axisTick: { show: false },
      axisLabel: {
        color: '#787b86',
        fontSize: 11,
        margin: 8,
      },
      splitLine: {
        show: true,
        lineStyle: { color: '#363a45', width: 1 },
      },
    },
    yAxis: {
      type: 'value',
      scale: true,
      position: 'right',
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: '#787b86',
        fontSize: 11,
        inside: false,
        margin: 4,
        formatter: (value: number) => formatPrice(value),
      },
      splitLine: {
        show: true,
        lineStyle: { color: '#363a45', width: 1 },
      },
      splitNumber: 8,
    },
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: klineData,
        itemStyle: {
          color: upColor,
          color0: downColor,
          borderColor: upColor,
          borderColor0: downColor,
          borderWidth: 1,
        },
        barWidth: '70%',
        markPoint: signalMarkers.value.length > 0 ? {
          data: signalMarkers.value,
          label: {
            show: true,
            formatter: (params: any) => params.name,
            color: '#fff',
            fontSize: 10,
          },
        } : undefined,
        markLine: props.signals?.length
          ? {
              silent: true,
              symbol: 'none',
              data: props.signals.slice(0, 3).flatMap((s) => [
                {
                  yAxis: s.tp_price,
                  lineStyle: { color: upColor, type: 'dashed', width: 1 },
                  label: {
                    show: true,
                    formatter: `TP`,
                    position: 'insideEndTop',
                    fontSize: 10,
                    color: upColor,
                  },
                },
                {
                  yAxis: s.sl_price,
                  lineStyle: { color: downColor, type: 'dashed', width: 1 },
                  label: {
                    show: true,
                    formatter: `SL`,
                    position: 'insideEndTop',
                    fontSize: 10,
                    color: downColor,
                  },
                },
              ]),
            }
          : undefined,
      },
    ],
    dataZoom: [
      {
        type: 'inside',
        start: 50,
        end: 100,
        zoomLock: false,
        minValueSpan: 10,
      },
    ],
  }

  chartInstance.setOption(option, true)

  // 监听鼠标移动更新 OHLC 显示
  chartInstance.off('mousemove')
  chartInstance.on('mousemove', (params: any) => {
    if (params.componentType === 'series' && params.data) {
      const [open, close, low, high] = params.data
      const change = close - open
      const changePercent = open > 0 ? (change / open) * 100 : 0
      hoverData.value = {
        time: params.name,
        open,
        high,
        low,
        close,
        change,
        changePercent,
      }
    }
  })

  chartInstance.off('mouseout')
  chartInstance.on('mouseout', () => {
    hoverData.value = null
  })
}

function handleResize() {
  chartInstance?.resize()
}

watch(
  () => [props.snapshots, props.signals, props.klines, props.source],
  () => {
    updateChart()
  },
  { deep: true }
)

onMounted(() => {
  initChart()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chartInstance?.dispose()
})
</script>

<template>
  <div class="chart-container">
    <!-- TradingView 风格顶部 OHLC 信息栏 -->
    <div class="ohlc-bar">
      <span class="pair-name">{{ ticker || 'BTC' }}-USD · {{ intervalText }} · {{ source || 'Variational' }}</span>
      <template v-if="displayData">
        <span class="ohlc-item">
          <span class="label">O</span>
          <span class="value">{{ formatPrice(displayData.open) }}</span>
        </span>
        <span class="ohlc-item">
          <span class="label">H</span>
          <span class="value">{{ formatPrice(displayData.high) }}</span>
        </span>
        <span class="ohlc-item">
          <span class="label">L</span>
          <span class="value">{{ formatPrice(displayData.low) }}</span>
        </span>
        <span class="ohlc-item">
          <span class="label">C</span>
          <span class="value">{{ formatPrice(displayData.close) }}</span>
        </span>
        <span 
          class="change" 
          :class="{ up: displayData.change >= 0, down: displayData.change < 0 }"
        >
          {{ displayData.change >= 0 ? '+' : '' }}{{ displayData.change.toFixed(2) }}
          ({{ displayData.change >= 0 ? '+' : '' }}{{ displayData.changePercent.toFixed(2) }}%)
        </span>
      </template>
    </div>
    <!-- K线图 -->
    <div
      ref="chartRef"
      class="price-chart"
      :style="{ height: `${(height || 300) - 28}px` }"
    ></div>
  </div>
</template>

<style scoped>
.chart-container {
  width: 100%;
  background: #131722;
  border-radius: 4px;
  overflow: hidden;
}

.ohlc-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 12px;
  font-family: 'SF Mono', Monaco, 'Courier New', monospace;
  font-size: 12px;
  color: #d1d4dc;
  background: #131722;
  border-bottom: 1px solid #363a45;
}

.pair-name {
  color: #787b86;
  margin-right: 8px;
}

.ohlc-item {
  display: flex;
  align-items: center;
  gap: 2px;
}

.ohlc-item .label {
  color: #787b86;
}

.ohlc-item .value {
  color: #d1d4dc;
}

.change {
  font-weight: 500;
}

.change.up {
  color: #26a69a;
}

.change.down {
  color: #ef5350;
}

.price-chart {
  width: 100%;
  background: #131722;
}
</style>
