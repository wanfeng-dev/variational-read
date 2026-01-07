import axios from 'axios'
import type {
  Snapshot,
  Feature,
  Signal,
  Alert,
  BacktestRun,
  SignalStats,
  SnapshotsResponse,
  FeaturesResponse,
  SignalsResponse,
  AlertsResponse,
  BacktestListResponse,
  HealthResponse,
  DataSource,
  Ticker,
  SourcesStatusResponse,
} from '@/types'

const API_BASE = import.meta.env.VITE_API_BASE || ''

const http = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 响应拦截器
http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

// K线数据类型
export interface KlineData {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface KlinesResponse {
  klines: KlineData[]
  ticker: string
  interval: string
  source: string
}

export const api = {
  // === 健康检查 ===
  health: (): Promise<HealthResponse> => http.get('/api/health'),

  // === 数据源状态 ===
  getSourcesStatus: (): Promise<SourcesStatusResponse> =>
    http.get('/api/sources/status'),

  // === K线数据 (Bybit) ===
  getKlines: (
    ticker: string = 'BTC',
    interval: string = '1',
    limit: number = 200
  ): Promise<KlinesResponse> =>
    http.get('/api/klines', { params: { ticker, interval, limit } }),

  // === Snapshots ===
  getSnapshots: (limit = 100, source?: DataSource, ticker?: Ticker): Promise<SnapshotsResponse> =>
    http.get('/api/snapshots', { params: { limit, source, ticker } }),

  getLatestSnapshot: (source?: DataSource, ticker?: Ticker): Promise<{ snapshot: Snapshot | null }> =>
    http.get('/api/snapshots/latest', { params: { source, ticker } }),

  // === Features ===
  getLatestFeature: (source?: DataSource, ticker?: Ticker): Promise<{ feature: Feature | null }> =>
    http.get('/api/features/latest', { params: { source, ticker } }),

  getFeatureHistory: (
    ticker?: Ticker,
    start?: string,
    end?: string,
    limit = 100,
    source?: DataSource
  ): Promise<FeaturesResponse> =>
    http.get('/api/features/history', { params: { ticker, start, end, limit, source } }),

  // === Signals ===
  getLatestSignal: (source?: DataSource, ticker?: Ticker): Promise<{ signal: Signal | null }> =>
    http.get('/api/signals/latest', { params: { source, ticker } }),

  getSignalHistory: (params: {
    start?: string
    end?: string
    status?: string
    limit?: number
    source?: DataSource
    ticker?: Ticker
  }): Promise<SignalsResponse> =>
    http.get('/api/signals/history', { params }),

  getSignalStats: (start?: string, end?: string, source?: DataSource, ticker?: Ticker): Promise<SignalStats> =>
    http.get('/api/signals/stats', { params: { start, end, source, ticker } }),

  // === Alerts ===
  getAlertHistory: (params: {
    type?: string
    priority?: string
    start?: string
    end?: string
    limit?: number
  }): Promise<AlertsResponse> =>
    http.get('/api/alerts/history', { params }),

  acknowledgeAlert: (alertId: number): Promise<{ success: boolean; alert: Alert }> =>
    http.put(`/api/alerts/${alertId}/acknowledge`),

  // === Backtest ===
  runBacktest: (
    start: string,
    end: string,
    source?: DataSource,
    ticker?: Ticker,
    params?: Record<string, unknown>
  ): Promise<{ run_id: number; metrics: Record<string, unknown> }> =>
    http.post('/api/backtest/run', null, {
      params: { start, end, source, ticker, params: params ? JSON.stringify(params) : undefined },
    }),

  getBacktestResult: (
    runId: number
  ): Promise<{ run: BacktestRun & { details?: unknown } }> =>
    http.get(`/api/backtest/results/${runId}`),

  listBacktestRuns: (limit = 20): Promise<BacktestListResponse> =>
    http.get('/api/backtest/list', { params: { limit } }),

  runWalkForward: (
    start: string,
    end: string,
    trainWindow = 7,
    testWindow = 1,
    stepSize = 1,
    params?: Record<string, unknown>
  ): Promise<{
    run_id: number
    aggregate_metrics: Record<string, unknown>
    total_windows: number
  }> =>
    http.post('/api/backtest/walk-forward', null, {
      params: {
        start,
        end,
        train_window: trainWindow,
        test_window: testWindow,
        step_size: stepSize,
        params: params ? JSON.stringify(params) : undefined,
      },
    }),
}

export default api
