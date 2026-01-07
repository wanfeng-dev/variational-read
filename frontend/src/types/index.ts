// 数据源类型
export type DataSource = 'variational' | 'bybit'
export type Ticker = 'BTC' | 'ETH'

// 快照数据
export interface Snapshot {
  id: number
  ts: string
  source: DataSource
  ticker: Ticker
  mark_price: number | null
  bid_1k: number | null
  ask_1k: number | null
  bid_100k: number | null
  ask_100k: number | null
  mid: number | null
  spread_bps: number | null
  impact_buy_bps: number | null
  impact_sell_bps: number | null
  quote_age_ms: number | null
  funding_rate: number | null
  long_oi: number | null
  short_oi: number | null
  volume_24h: number | null
  quotes_updated_at: string | null
}

// 特征数据
export interface Feature {
  id: number
  ts: string
  source: DataSource
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
  impact_buy_bps: number | null
  impact_sell_bps: number | null
  quote_age_ms: number | null
  long_short_ratio: number | null
}

// 交易信号
export interface Signal {
  id: number
  ts: string
  source: DataSource
  ticker: Ticker
  side: 'LONG' | 'SHORT'
  entry_price: number
  tp_price: number
  sl_price: number
  confidence: number | null
  rationale: string | null
  filters_passed: string | null
  breakout_price: number | null
  reclaim_price: number | null
  status: 'PENDING' | 'TP_HIT' | 'SL_HIT' | 'EXPIRED'
  result_pnl_bps: number | null
  closed_at: string | null
}

// 预警
export interface Alert {
  id: number
  ts: string
  type: string
  priority: 'HIGH' | 'MEDIUM' | 'LOW'
  ticker: Ticker
  message: string
  data: string | null
  acknowledged: boolean
}

// 回测运行记录
export interface BacktestRun {
  id: number
  started_at: string
  finished_at: string | null
  params: string | null
  data_start: string
  data_end: string
  total_signals: number
  win_count: number
  loss_count: number
  win_rate: number | null
  avg_win_bps: number | null
  avg_loss_bps: number | null
  total_pnl_bps: number | null
  max_drawdown_bps: number | null
  sharpe_ratio: number | null
  results_json: string | null
}

// 信号统计
export interface SignalStats {
  total_signals: number
  win_count: number
  loss_count: number
  win_rate: number
  avg_pnl_bps: number
}

// 回测参数
export interface BacktestParams {
  start: string
  end: string
  params?: Record<string, unknown>
}

// 走步验证参数
export interface WalkForwardParams {
  start: string
  end: string
  train_window: number
  test_window: number
  step_size: number
  params?: Record<string, unknown>
}

// API 响应类型
export interface ApiResponse<T> {
  data: T
  error?: string
}

export interface SnapshotsResponse {
  snapshots: Snapshot[]
  total: number
}

export interface FeaturesResponse {
  features: Feature[]
  total: number
}

export interface SignalsResponse {
  signals: Signal[]
  total: number
}

export interface AlertsResponse {
  alerts: Alert[]
  total: number
}

export interface BacktestListResponse {
  runs: BacktestRun[]
}

// WebSocket 消息类型
export interface WsMessage<T = unknown> {
  type: string
  data: T
}

// K线数据点
export interface KLineDataPoint {
  ts: string
  open: number
  high: number
  low: number
  close: number
  volume?: number
}

// 健康检查响应
export interface HealthResponse {
  status: string
  scheduler_running: boolean
  feature_calculator_initialized: boolean
  feature_window_size: number
  ws_connections: number
  alert_ws_connections: number
  signal_ws_connections: number
  signal_engine_active_signals: number
  signal_engine_has_breakout: boolean
}

// 数据源状态
export interface SourceStatus {
  name: DataSource
  status: 'ok' | 'error'
  latency_ms: number
  tickers: Ticker[]
}

export interface SourcesStatusResponse {
  sources: SourceStatus[]
}
