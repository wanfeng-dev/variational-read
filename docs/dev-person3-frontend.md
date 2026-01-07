# 人员 3：前端改造 + API 扩展

## 职责
前端支持多数据源多标的切换、后端 API 扩展

## 产出文件
```
backend/
└── main.py                      # 修改：API 增加 source 参数

frontend/
├── src/
│   ├── stores/
│   │   ├── market.ts            # 修改：按 source+ticker 存储
│   │   ├── signals.ts           # 修改：支持 source 过滤
│   │   └── settings.ts          # 新增：用户选择的数据源/标的
│   ├── views/
│   │   ├── Dashboard.vue        # 修改：数据源/标的选择器
│   │   ├── Signals.vue          # 修改：筛选条件增加 source
│   │   └── Backtest.vue         # 修改：回测参数增加 source
│   ├── components/
│   │   ├── SourceSelector.vue   # 新增：数据源选择组件
│   │   └── TickerSelector.vue   # 新增：标的选择组件
│   ├── api/
│   │   └── index.ts             # 修改：API 增加 source 参数
│   └── types/
│       └── index.ts             # 修改：类型定义增加 source
```

---

## 后端 API 扩展

### 1. 所有 API 增加 source 参数

修改 `main.py` 中的所有查询 API：

```python
@app.get("/api/snapshots")
async def get_snapshots(
    limit: int = Query(default=100, ge=1, le=1000),
    source: Optional[str] = Query(default=None, description="数据源: variational/bybit"),
    ticker: str = Query(default="ETH"),
    db: Session = Depends(get_db),
):
    """获取快照列表"""
    query = db.query(Snapshot)
    
    if source:
        query = query.filter(Snapshot.source == source)
    query = query.filter(Snapshot.ticker == ticker)
    
    snapshots = query.order_by(desc(Snapshot.ts)).limit(limit).all()
    total = query.count()
    
    return {"snapshots": [s.to_dict() for s in snapshots], "total": total}


@app.get("/api/snapshots/latest")
async def get_latest_snapshot(
    source: Optional[str] = Query(default=None),
    ticker: str = Query(default="ETH"),
    db: Session = Depends(get_db),
):
    """获取最新快照"""
    query = db.query(Snapshot).filter(Snapshot.ticker == ticker)
    
    if source:
        query = query.filter(Snapshot.source == source)
    
    snapshot = query.order_by(desc(Snapshot.ts)).first()
    return {"snapshot": snapshot.to_dict() if snapshot else None}


@app.get("/api/features/latest")
async def get_latest_feature(
    source: Optional[str] = Query(default=None),
    ticker: str = Query(default="ETH"),
    db: Session = Depends(get_db),
):
    """获取最新特征"""
    query = db.query(Feature).filter(Feature.ticker == ticker)
    
    if source:
        query = query.filter(Feature.source == source)
    
    feature = query.order_by(desc(Feature.ts)).first()
    return {"feature": feature.to_dict() if feature else None}


@app.get("/api/signals/history")
async def get_signal_history(
    source: Optional[str] = Query(default=None),
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    ticker: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """获取信号历史"""
    query = db.query(Signal)
    
    if source:
        query = query.filter(Signal.source == source)
    if ticker:
        query = query.filter(Signal.ticker == ticker)
    if status:
        query = query.filter(Signal.status == status)
    # ... 其他过滤
    
    signals = query.order_by(desc(Signal.ts)).limit(limit).all()
    return {"signals": [s.to_dict() for s in signals], "total": query.count()}
```

### 2. 新增数据源状态 API

```python
@app.get("/api/sources/status")
async def get_sources_status():
    """
    获取所有数据源状态
    
    Returns:
        各数据源的连接状态和延迟
    """
    sources = []
    
    # Variational 状态
    var_latency = scheduler.get_latency("variational")
    sources.append({
        "name": "variational",
        "status": "ok" if var_latency is not None else "error",
        "latency_ms": var_latency or 0,
        "tickers": ["BTC", "ETH"],
    })
    
    # Bybit 状态
    bybit_latency = scheduler.get_latency("bybit")
    sources.append({
        "name": "bybit",
        "status": "ok" if bybit_latency is not None else "error",
        "latency_ms": bybit_latency or 0,
        "tickers": ["BTC", "ETH"],
    })
    
    return {"sources": sources}
```

### 3. WebSocket 订阅增加 source 参数

```python
@app.websocket("/ws/snapshots")
async def websocket_snapshots(websocket: WebSocket):
    await ws_manager.connect(websocket)
    
    subscribed_sources = set()
    subscribed_tickers = set()
    
    try:
        while True:
            data = await websocket.receive_json()
            
            if data.get("action") == "subscribe":
                source = data.get("source")  # 可选
                ticker = data.get("ticker", "ETH")
                
                if source:
                    subscribed_sources.add(source)
                subscribed_tickers.add(ticker)
                
                await websocket.send_json({
                    "type": "subscribed",
                    "source": source,
                    "ticker": ticker,
                })
                
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
```

---

## 前端改造

### 1. types/index.ts 修改

添加 source 字段到所有类型：

```typescript
// types/index.ts

export type DataSource = 'variational' | 'bybit'
export type Ticker = 'BTC' | 'ETH'

export interface Snapshot {
  id: number
  ts: string
  source: DataSource  // 新增
  ticker: Ticker
  mark_price: number | null
  bid_1k: number | null
  ask_1k: number | null
  mid: number | null
  spread_bps: number | null
  funding_rate: number | null
  long_oi: number | null
  short_oi: number | null
  volume_24h: number | null
  quote_age_ms: number | null
}

export interface Feature {
  id: number
  ts: string
  source: DataSource  // 新增
  ticker: Ticker
  mid: number | null
  return_5s: number | null
  return_15s: number | null
  return_60s: number | null
  std_60s: number | null
  rsi_14: number | null
  z_score: number | null
  range_high_20m: number | null
  range_low_20m: number | null
  spread_bps: number | null
  long_short_ratio: number | null
}

export interface Signal {
  id: number
  ts: string
  source: DataSource  // 新增
  ticker: Ticker
  side: 'LONG' | 'SHORT'
  entry_price: number
  tp_price: number
  sl_price: number
  status: 'PENDING' | 'TP_HIT' | 'SL_HIT' | 'EXPIRED'
  confidence: number | null
  rationale: string | null
  result_pnl_bps: number | null
}

export interface SourceStatus {
  name: DataSource
  status: 'ok' | 'error'
  latency_ms: number
  tickers: Ticker[]
}
```

### 2. stores/settings.ts（新建）

用户偏好存储：

```typescript
// stores/settings.ts
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import type { DataSource, Ticker } from '@/types'

export const useSettingsStore = defineStore('settings', () => {
  // 当前选中的数据源
  const currentSource = ref<DataSource>(
    (localStorage.getItem('currentSource') as DataSource) || 'bybit'
  )
  
  // 当前选中的标的
  const currentTicker = ref<Ticker>(
    (localStorage.getItem('currentTicker') as Ticker) || 'ETH'
  )
  
  // 是否显示所有数据源
  const showAllSources = ref<boolean>(
    localStorage.getItem('showAllSources') === 'true'
  )
  
  // 持久化
  watch(currentSource, (val) => {
    localStorage.setItem('currentSource', val)
  })
  
  watch(currentTicker, (val) => {
    localStorage.setItem('currentTicker', val)
  })
  
  watch(showAllSources, (val) => {
    localStorage.setItem('showAllSources', String(val))
  })
  
  // 切换数据源
  function setSource(source: DataSource) {
    currentSource.value = source
  }
  
  // 切换标的
  function setTicker(ticker: Ticker) {
    currentTicker.value = ticker
  }
  
  // 获取当前 key
  function getCurrentKey(): string {
    return `${currentSource.value}-${currentTicker.value}`
  }
  
  return {
    currentSource,
    currentTicker,
    showAllSources,
    setSource,
    setTicker,
    getCurrentKey,
  }
})
```

### 3. stores/market.ts 修改

按 source+ticker 存储数据：

```typescript
// stores/market.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useSettingsStore } from './settings'
import type { Snapshot, Feature, SourceStatus } from '@/types'
import { api } from '@/api'

export const useMarketStore = defineStore('market', () => {
  const settingsStore = useSettingsStore()
  
  // 按 key 存储快照: { "bybit-BTC": Snapshot[], ... }
  const snapshots = ref<Record<string, Snapshot[]>>({})
  
  // 按 key 存储最新特征
  const latestFeatures = ref<Record<string, Feature | null>>({})
  
  // 数据源状态
  const sourcesStatus = ref<SourceStatus[]>([])
  
  // 当前选中的快照
  const currentSnapshots = computed(() => {
    const key = settingsStore.getCurrentKey()
    return snapshots.value[key] || []
  })
  
  // 当前选中的特征
  const currentFeature = computed(() => {
    const key = settingsStore.getCurrentKey()
    return latestFeatures.value[key] || null
  })
  
  // 获取指定数据源的延迟
  const getSourceLatency = (source: string): number | null => {
    const status = sourcesStatus.value.find(s => s.name === source)
    return status?.latency_ms ?? null
  }
  
  // 加载快照
  async function fetchSnapshots(source?: string, ticker?: string, limit = 100) {
    const s = source || settingsStore.currentSource
    const t = ticker || settingsStore.currentTicker
    const key = `${s}-${t}`
    
    const res = await api.getSnapshots({ source: s, ticker: t, limit })
    snapshots.value[key] = res.snapshots
  }
  
  // 加载最新特征
  async function fetchLatestFeature(source?: string, ticker?: string) {
    const s = source || settingsStore.currentSource
    const t = ticker || settingsStore.currentTicker
    const key = `${s}-${t}`
    
    const res = await api.getLatestFeature({ source: s, ticker: t })
    latestFeatures.value[key] = res.feature
  }
  
  // 加载数据源状态
  async function fetchSourcesStatus() {
    const res = await api.getSourcesStatus()
    sourcesStatus.value = res.sources
  }
  
  // 添加新快照（WebSocket 推送）
  function addSnapshot(snapshot: Snapshot) {
    const key = `${snapshot.source}-${snapshot.ticker}`
    if (!snapshots.value[key]) {
      snapshots.value[key] = []
    }
    snapshots.value[key].unshift(snapshot)
    // 限制长度
    if (snapshots.value[key].length > 1000) {
      snapshots.value[key].pop()
    }
  }
  
  return {
    snapshots,
    latestFeatures,
    sourcesStatus,
    currentSnapshots,
    currentFeature,
    getSourceLatency,
    fetchSnapshots,
    fetchLatestFeature,
    fetchSourcesStatus,
    addSnapshot,
  }
})
```

### 4. stores/signals.ts 修改

支持 source 过滤：

```typescript
// stores/signals.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useSettingsStore } from './settings'
import type { Signal } from '@/types'
import { api } from '@/api'

export const useSignalsStore = defineStore('signals', () => {
  const settingsStore = useSettingsStore()
  
  // 所有信号
  const signals = ref<Signal[]>([])
  
  // 筛选条件
  const filterSource = ref<string | null>(null)
  const filterTicker = ref<string | null>(null)
  const filterStatus = ref<string | null>(null)
  
  // 筛选后的信号
  const filteredSignals = computed(() => {
    return signals.value.filter(s => {
      if (filterSource.value && s.source !== filterSource.value) return false
      if (filterTicker.value && s.ticker !== filterTicker.value) return false
      if (filterStatus.value && s.status !== filterStatus.value) return false
      return true
    })
  })
  
  // 当前数据源+标的的信号
  const currentSignals = computed(() => {
    const source = settingsStore.currentSource
    const ticker = settingsStore.currentTicker
    return signals.value.filter(s => s.source === source && s.ticker === ticker)
  })
  
  // 加载信号
  async function fetchSignals(params: {
    source?: string
    ticker?: string
    status?: string
    limit?: number
  } = {}) {
    const res = await api.getSignalHistory(params)
    signals.value = res.signals
  }
  
  // 添加新信号（WebSocket 推送）
  function addSignal(signal: Signal) {
    signals.value.unshift(signal)
  }
  
  // 更新信号状态
  function updateSignal(signal: Signal) {
    const idx = signals.value.findIndex(s => s.id === signal.id)
    if (idx !== -1) {
      signals.value[idx] = signal
    }
  }
  
  return {
    signals,
    filterSource,
    filterTicker,
    filterStatus,
    filteredSignals,
    currentSignals,
    fetchSignals,
    addSignal,
    updateSignal,
  }
})
```

### 5. api/index.ts 修改

所有请求增加 source 参数：

```typescript
// api/index.ts
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

interface QueryParams {
  source?: string
  ticker?: string
  limit?: number
  start?: string
  end?: string
  status?: string
}

function buildUrl(path: string, params: QueryParams = {}): string {
  const url = new URL(path, API_BASE)
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      url.searchParams.set(key, String(value))
    }
  })
  return url.toString()
}

export const api = {
  // Snapshots
  getSnapshots: (params: QueryParams = {}) =>
    fetch(buildUrl('/api/snapshots', params)).then(r => r.json()),
  
  getLatestSnapshot: (params: QueryParams = {}) =>
    fetch(buildUrl('/api/snapshots/latest', params)).then(r => r.json()),
  
  // Features
  getLatestFeature: (params: QueryParams = {}) =>
    fetch(buildUrl('/api/features/latest', params)).then(r => r.json()),
  
  getFeatureHistory: (params: QueryParams = {}) =>
    fetch(buildUrl('/api/features/history', params)).then(r => r.json()),
  
  // Signals
  getLatestSignal: (params: QueryParams = {}) =>
    fetch(buildUrl('/api/signals/latest', params)).then(r => r.json()),
  
  getSignalHistory: (params: QueryParams = {}) =>
    fetch(buildUrl('/api/signals/history', params)).then(r => r.json()),
  
  getSignalStats: (params: QueryParams = {}) =>
    fetch(buildUrl('/api/signals/stats', params)).then(r => r.json()),
  
  // Sources
  getSourcesStatus: () =>
    fetch(buildUrl('/api/sources/status')).then(r => r.json()),
  
  // Backtest
  runBacktest: (params: QueryParams & { params?: string }) =>
    fetch(buildUrl('/api/backtest/run', params), { method: 'POST' }).then(r => r.json()),
}
```

### 6. components/SourceSelector.vue（新建）

数据源选择组件：

```vue
<template>
  <div class="source-selector">
    <select v-model="currentSource" @change="onChange">
      <option value="variational">Variational</option>
      <option value="bybit">Bybit</option>
    </select>
    <span v-if="latency !== null" class="latency" :class="latencyClass">
      {{ latency }}ms
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { useMarketStore } from '@/stores/market'

const settingsStore = useSettingsStore()
const marketStore = useMarketStore()

const currentSource = computed({
  get: () => settingsStore.currentSource,
  set: (val) => settingsStore.setSource(val)
})

const latency = computed(() => 
  marketStore.getSourceLatency(settingsStore.currentSource)
)

const latencyClass = computed(() => {
  if (latency.value === null) return 'unknown'
  if (latency.value < 100) return 'good'
  if (latency.value < 500) return 'medium'
  return 'slow'
})

function onChange() {
  // 切换数据源后重新加载数据
  marketStore.fetchSnapshots()
  marketStore.fetchLatestFeature()
}
</script>

<style scoped>
.source-selector {
  display: flex;
  align-items: center;
  gap: 8px;
}

select {
  padding: 4px 8px;
  border-radius: 4px;
}

.latency {
  font-size: 12px;
  padding: 2px 6px;
  border-radius: 4px;
}

.latency.good { background: #10b981; color: white; }
.latency.medium { background: #f59e0b; color: white; }
.latency.slow { background: #ef4444; color: white; }
.latency.unknown { background: #6b7280; color: white; }
</style>
```

### 7. components/TickerSelector.vue（新建）

标的选择组件：

```vue
<template>
  <div class="ticker-selector">
    <button 
      v-for="t in tickers" 
      :key="t"
      :class="{ active: currentTicker === t }"
      @click="selectTicker(t)"
    >
      {{ t }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { useMarketStore } from '@/stores/market'
import type { Ticker } from '@/types'

const tickers: Ticker[] = ['BTC', 'ETH']

const settingsStore = useSettingsStore()
const marketStore = useMarketStore()

const currentTicker = computed(() => settingsStore.currentTicker)

function selectTicker(ticker: Ticker) {
  settingsStore.setTicker(ticker)
  // 切换标的后重新加载数据
  marketStore.fetchSnapshots()
  marketStore.fetchLatestFeature()
}
</script>

<style scoped>
.ticker-selector {
  display: flex;
  gap: 4px;
}

button {
  padding: 4px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  transition: all 0.2s;
}

button:hover {
  background: #f3f4f6;
}

button.active {
  background: #3b82f6;
  color: white;
  border-color: #3b82f6;
}
</style>
```

### 8. views/Dashboard.vue 修改

顶部增加选择器：

```vue
<template>
  <div class="dashboard">
    <!-- 顶部选择器 -->
    <div class="header">
      <div class="selectors">
        <SourceSelector />
        <TickerSelector />
      </div>
      <div class="status">
        延迟: {{ currentLatency }}ms
      </div>
    </div>
    
    <!-- 指标卡片 -->
    <div class="metrics">
      <MetricCard title="中间价" :value="currentFeature?.mid" />
      <MetricCard title="24h成交量" :value="formatVolume(currentFeature?.volume_24h)" />
      <MetricCard title="资金费率" :value="formatPercent(latestSnapshot?.funding_rate)" />
      <MetricCard title="点差" :value="formatBps(currentFeature?.spread_bps)" suffix="bps" />
      <MetricCard title="RSI" :value="currentFeature?.rsi_14" />
    </div>
    
    <!-- K线图 -->
    <div class="chart-container">
      <PriceChart 
        :data="currentSnapshots" 
        :title="`${currentTicker} 1分钟 (${currentSource})`"
      />
    </div>
    
    <!-- 信号和预警 -->
    <div class="panels">
      <div class="signals-panel">
        <h3>最新信号 [{{ currentSource }}-{{ currentTicker }}]</h3>
        <SignalCard 
          v-for="signal in currentSignals.slice(0, 3)" 
          :key="signal.id" 
          :signal="signal" 
        />
      </div>
      <div class="alerts-panel">
        <h3>最新预警</h3>
        <AlertItem v-for="alert in alerts.slice(0, 5)" :key="alert.id" :alert="alert" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { useMarketStore } from '@/stores/market'
import { useSignalsStore } from '@/stores/signals'
import SourceSelector from '@/components/SourceSelector.vue'
import TickerSelector from '@/components/TickerSelector.vue'
import MetricCard from '@/components/MetricCard.vue'
import PriceChart from '@/components/PriceChart.vue'
import SignalCard from '@/components/SignalCard.vue'
import AlertItem from '@/components/AlertItem.vue'

const settingsStore = useSettingsStore()
const marketStore = useMarketStore()
const signalsStore = useSignalsStore()

const currentSource = computed(() => settingsStore.currentSource)
const currentTicker = computed(() => settingsStore.currentTicker)
const currentSnapshots = computed(() => marketStore.currentSnapshots)
const currentFeature = computed(() => marketStore.currentFeature)
const currentSignals = computed(() => signalsStore.currentSignals)
const currentLatency = computed(() => marketStore.getSourceLatency(currentSource.value))

onMounted(async () => {
  await Promise.all([
    marketStore.fetchSourcesStatus(),
    marketStore.fetchSnapshots(),
    marketStore.fetchLatestFeature(),
    signalsStore.fetchSignals({ source: currentSource.value, ticker: currentTicker.value }),
  ])
})
</script>
```

### 9. views/Signals.vue 修改

筛选栏增加 source：

```vue
<template>
  <div class="signals-page">
    <!-- 筛选栏 -->
    <div class="filters">
      <select v-model="filterSource">
        <option :value="null">全部数据源</option>
        <option value="variational">Variational</option>
        <option value="bybit">Bybit</option>
      </select>
      
      <select v-model="filterTicker">
        <option :value="null">全部标的</option>
        <option value="BTC">BTC</option>
        <option value="ETH">ETH</option>
      </select>
      
      <select v-model="filterStatus">
        <option :value="null">全部状态</option>
        <option value="PENDING">待处理</option>
        <option value="TP_HIT">止盈</option>
        <option value="SL_HIT">止损</option>
      </select>
    </div>
    
    <!-- 信号表格 -->
    <table>
      <thead>
        <tr>
          <th>时间</th>
          <th>数据源</th>
          <th>标的</th>
          <th>方向</th>
          <th>入场价</th>
          <th>止盈</th>
          <th>止损</th>
          <th>状态</th>
          <th>盈亏(bps)</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="signal in filteredSignals" :key="signal.id">
          <td>{{ formatTime(signal.ts) }}</td>
          <td>{{ signal.source }}</td>
          <td>{{ signal.ticker }}</td>
          <td :class="signal.side.toLowerCase()">{{ signal.side }}</td>
          <td>{{ signal.entry_price }}</td>
          <td>{{ signal.tp_price }}</td>
          <td>{{ signal.sl_price }}</td>
          <td :class="signal.status.toLowerCase()">{{ signal.status }}</td>
          <td>{{ signal.result_pnl_bps ?? '-' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useSignalsStore } from '@/stores/signals'

const signalsStore = useSignalsStore()

const filterSource = computed({
  get: () => signalsStore.filterSource,
  set: (val) => { signalsStore.filterSource = val }
})

const filterTicker = computed({
  get: () => signalsStore.filterTicker,
  set: (val) => { signalsStore.filterTicker = val }
})

const filterStatus = computed({
  get: () => signalsStore.filterStatus,
  set: (val) => { signalsStore.filterStatus = val }
})

const filteredSignals = computed(() => signalsStore.filteredSignals)

onMounted(() => {
  signalsStore.fetchSignals({ limit: 500 })
})
</script>
```

### 10. views/Backtest.vue 修改

回测表单增加 source/ticker：

```vue
<template>
  <div class="backtest-page">
    <form @submit.prevent="runBacktest">
      <!-- 数据源选择 -->
      <div class="form-group">
        <label>数据源</label>
        <select v-model="form.source">
          <option value="variational">Variational</option>
          <option value="bybit">Bybit</option>
        </select>
      </div>
      
      <!-- 标的选择 -->
      <div class="form-group">
        <label>标的</label>
        <select v-model="form.ticker">
          <option value="BTC">BTC</option>
          <option value="ETH">ETH</option>
        </select>
      </div>
      
      <!-- 时间范围 -->
      <div class="form-group">
        <label>开始时间</label>
        <input type="datetime-local" v-model="form.start" />
      </div>
      
      <div class="form-group">
        <label>结束时间</label>
        <input type="datetime-local" v-model="form.end" />
      </div>
      
      <button type="submit" :disabled="loading">
        {{ loading ? '运行中...' : '运行回测' }}
      </button>
    </form>
    
    <!-- 回测结果 -->
    <div v-if="result" class="result">
      <h3>回测结果 [{{ result.source }}-{{ result.ticker }}]</h3>
      <!-- ... 结果展示 -->
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { api } from '@/api'

const form = reactive({
  source: 'bybit',
  ticker: 'ETH',
  start: '',
  end: '',
})

const loading = ref(false)
const result = ref(null)

async function runBacktest() {
  loading.value = true
  try {
    const res = await api.runBacktest({
      source: form.source,
      ticker: form.ticker,
      start: form.start,
      end: form.end,
    })
    result.value = res
  } finally {
    loading.value = false
  }
}
</script>
```

---

## UI 设计示意

```
┌─────────────────────────────────────────────────────────────┐
│  [Variational ▼] [Bybit ▼]  │  [BTC] [ETH]  │  延迟: 80ms  │
├─────────────────────────────────────────────────────────────┤
│  [TVL]   [24h Vol]   [Funding]   [Spread]   [L/S Ratio]    │
├─────────────────────────────────────────────────────────────┤
│                    BTC 1分钟 K线图                          │
│                    (Bybit 数据源)                           │
├─────────────────────────────────────────────────────────────┤
│  最新信号 [bybit-BTC]        │   最新预警                   │
│  [SignalCard]                │   [AlertItem]                │
└─────────────────────────────────────────────────────────────┘
```

---

## 检查清单

**后端**：
- [ ] main.py API 增加 source 查询参数
- [ ] main.py 新增 /api/sources/status 端点
- [ ] main.py WebSocket 订阅支持 source 参数

**前端**：
- [ ] types/index.ts 类型更新
- [ ] stores/settings.ts 用户偏好存储
- [ ] stores/market.ts 多数据源数据管理
- [ ] stores/signals.ts source 过滤
- [ ] api/index.ts 所有请求增加 source
- [ ] components/SourceSelector.vue 数据源选择
- [ ] components/TickerSelector.vue 标的选择
- [ ] views/Dashboard.vue 集成选择器
- [ ] views/Signals.vue 筛选增加 source
- [ ] views/Backtest.vue 回测参数增加 source/ticker
- [ ] 响应式适配测试

---

## 对接说明

**依赖人员 1、2**：
- models.py Snapshot/Feature/Signal source 字段
- API 返回数据格式

## Git 分支

```
feat/frontend-source
```
