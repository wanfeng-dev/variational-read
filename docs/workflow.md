# Variational ETH 高胜率交易系统 - 工作流文档

## 项目概述

基于 Variational 只读 API，构建 ETH 1分钟级交易信号系统（仪表盘 + 信号引擎 + 预警）。

### 核心约束
- **标的**：仅 ETH
- **仓位**：约 1 ETH / 笔
- **执行**：市价单（Taker）
- **出场**：TP/SL（无时间止损）
- **盈亏比**：名义 RR = 2:1
- **目标胜率**：≥ 80%

### 技术栈
- **后端**：Python + FastAPI + SQLAlchemy
- **前端**：Vue3 + TypeScript + Pinia + ECharts
- **数据库**：SQLite（开发）/ PostgreSQL（生产）
- **通信**：REST API + WebSocket

---

## 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (Vue3)                          │
│   仪表盘 / 信号面板 / 预警通知 / 回测结果展示                │
└───────────────────────────┬─────────────────────────────────┘
                            │ REST + WebSocket
┌───────────────────────────┴─────────────────────────────────┐
│                      后端 (FastAPI)                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │ Collector│ │ Feature  │ │ Signal   │ │ Alert    │        │
│  │ 数据采集 │→│ Engine   │→│ Engine   │→│ Engine   │        │
│  └──────────┘ │ 特征计算 │ │ 信号生成 │ │ 预警推送 │        │
│               └──────────┘ └──────────┘ └──────────┘        │
│  ┌──────────────────────────────────────────────────┐       │
│  │              Backtest / WalkForward              │       │
│  │              回测与走步验证模块                   │       │
│  └──────────────────────────────────────────────────┘       │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                    数据库 (SQLite/PG)                       │
│   snapshots / features / signals / alerts / backtest_runs   │
└─────────────────────────────────────────────────────────────┘
```

---

## 五人分工详解

### 人员 1：数据采集与存储（Collector + DB）

#### 职责
1. 实现 Variational API 客户端
2. 定时拉取 `/metadata/stats`，提取 ETH 数据
3. 计算派生字段（mid, spread_bps, impact_bps, quote_age）
4. 设计并初始化数据库表
5. 实现限流控制（10 req/10s）与异常重试
6. 提供 WebSocket 实时推送新快照

#### 产出文件
```
backend/
├── config.py                    # 全局配置
├── collector/
│   ├── __init__.py
│   ├── variational_client.py    # API 客户端
│   └── scheduler.py             # 定时任务调度
├── db/
│   ├── __init__.py
│   ├── database.py              # 数据库连接
│   ├── models.py                # ORM 模型
│   └── init_db.py               # 初始化脚本
```

#### 数据库模型

**snapshots 表**
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| ts | DATETIME | 采集时间 |
| ticker | VARCHAR(10) | 代币符号 |
| mark_price | DECIMAL | 标记价格 |
| bid_1k | DECIMAL | $1k 档位买价 |
| ask_1k | DECIMAL | $1k 档位卖价 |
| bid_100k | DECIMAL | $100k 档位买价 |
| ask_100k | DECIMAL | $100k 档位卖价 |
| mid | DECIMAL | 中间价 (bid+ask)/2 |
| spread_bps | DECIMAL | 点差 (bps) |
| impact_buy_bps | DECIMAL | 买入冲击 (bps) |
| impact_sell_bps | DECIMAL | 卖出冲击 (bps) |
| quote_age_ms | INTEGER | 报价延迟 (ms) |
| funding_rate | DECIMAL | 资金费率 |
| long_oi | DECIMAL | 多头持仓 |
| short_oi | DECIMAL | 空头持仓 |
| volume_24h | DECIMAL | 24h 成交量 |
| quotes_updated_at | DATETIME | 报价更新时间 |
| raw_json | TEXT | 原始 JSON（可选） |

#### 接口契约

**REST API**
```
GET /api/snapshots
  Query: limit (int, default=100), ticker (str, default=ETH)
  Response: { snapshots: [...], total: int }

GET /api/snapshots/latest
  Query: ticker (str, default=ETH)
  Response: { snapshot: {...} }
```

**WebSocket**
```
WS /ws/snapshots
  Subscribe: { "action": "subscribe", "ticker": "ETH" }
  Push: { "type": "snapshot", "data": {...} }
```

#### 检查清单
- [ ] config.py 配置文件（API URL、限流参数、数据库路径）
- [ ] variational_client.py 实现 fetch_stats() 方法
- [ ] 派生字段计算（mid, spread_bps, impact_bps, quote_age）
- [ ] database.py 数据库连接与会话管理
- [ ] models.py Snapshot ORM 模型
- [ ] init_db.py 建表脚本
- [ ] scheduler.py 定时任务（2秒间隔，限流保护）
- [ ] REST API /api/snapshots, /api/snapshots/latest
- [ ] WebSocket /ws/snapshots 推送
- [ ] 异常重试与日志记录

---

### 人员 2：特征工程（Feature Engine）

#### 职责
1. 基于 snapshots 维护滚动窗口
2. 计算 1 分钟级技术特征
3. 存储到 features 表
4. 提供特征查询 API

#### 产出文件
```
backend/features/
├── __init__.py
├── calculator.py          # 特征计算主逻辑
├── indicators.py          # 技术指标实现
└── rolling_window.py      # 滚动窗口管理
```

#### 特征列表

| 特征名 | 计算方法 | 用途 |
|--------|----------|------|
| mid | (bid_1k + ask_1k) / 2 | 基础价格 |
| return_5s | (mid - mid_5s_ago) / mid_5s_ago | 短周期动量 |
| return_15s | (mid - mid_15s_ago) / mid_15s_ago | 短周期动量 |
| return_60s | (mid - mid_60s_ago) / mid_60s_ago | 1分钟动量 |
| std_60s | 60秒 mid 标准差 | 波动率 |
| atr_60s | 60秒 ATR | 波动率 |
| rsi_14 | 14周期 RSI | 超买超卖 |
| z_score | (mid - ema_60s) / std_60s | 偏离度 |
| range_high_20m | 20分钟滚动最高价 | 区间上沿 |
| range_low_20m | 20分钟滚动最低价 | 区间下沿 |
| spread_bps | (ask - bid) / mid * 10000 | 流动性 |
| impact_buy_bps | (ask_100k - ask_1k) / mid * 10000 | 买入冲击 |
| impact_sell_bps | (bid_1k - bid_100k) / mid * 10000 | 卖出冲击 |
| quote_age_ms | now - quotes_updated_at | 报价新鲜度 |
| long_short_ratio | long_oi / short_oi | 多空比 |

#### 数据库模型

**features 表**
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| ts | DATETIME | 时间戳 |
| ticker | VARCHAR(10) | 代币符号 |
| mid | DECIMAL | 中间价 |
| return_5s | DECIMAL | 5秒收益 |
| return_15s | DECIMAL | 15秒收益 |
| return_60s | DECIMAL | 60秒收益 |
| std_60s | DECIMAL | 60秒标准差 |
| rsi_14 | DECIMAL | RSI |
| z_score | DECIMAL | z-score |
| range_high_20m | DECIMAL | 20分钟高点 |
| range_low_20m | DECIMAL | 20分钟低点 |
| spread_bps | DECIMAL | 点差 |
| impact_buy_bps | DECIMAL | 买入冲击 |
| impact_sell_bps | DECIMAL | 卖出冲击 |
| quote_age_ms | INTEGER | 报价延迟 |
| long_short_ratio | DECIMAL | 多空比 |

#### 接口契约

```
GET /api/features/latest
  Query: ticker (str, default=ETH)
  Response: { feature: {...} }

GET /api/features/history
  Query: ticker, start (datetime), end (datetime), limit (int)
  Response: { features: [...], total: int }
```

#### 检查清单
- [ ] rolling_window.py 实现滚动窗口数据结构
- [ ] indicators.py 实现 RSI 计算
- [ ] indicators.py 实现 z-score 计算
- [ ] indicators.py 实现 ATR 计算
- [ ] indicators.py 实现 EMA/SMA 计算
- [ ] calculator.py 整合所有特征计算
- [ ] models.py 添加 Feature ORM 模型
- [ ] 特征计算触发逻辑（每次新 snapshot 后）
- [ ] REST API /api/features/latest, /api/features/history
- [ ] 单元测试：指标计算正确性

---

### 人员 3：信号引擎（Signal Engine）

#### 职责
1. 实现主信号：假突破回收（Trap）
2. 实现过滤器/确认器
3. 计算 TP/SL（名义 RR=2:1）
4. 存储信号并提供 API/WebSocket

#### 产出文件
```
backend/signals/
├── __init__.py
├── models.py              # Signal 数据模型
├── trap_signal.py         # 假突破回收信号
├── filters.py             # 过滤器集合
└── signal_engine.py       # 信号引擎主类
```

#### 主信号：假突破回收（Trap）

**逻辑流程**
```
1. 区间定义
   - range_high = max(mid, last N minutes)
   - range_low = min(mid, last N minutes)
   - range_mid = (range_high + range_low) / 2

2. 突破检测
   - 向上突破: mid > range_high + BREAKOUT_THRESHOLD_BPS
   - 向下突破: mid < range_low - BREAKOUT_THRESHOLD_BPS
   - 记录突破时间和极值

3. 回收检测（突破后 T 秒内）
   - 向上突破后回收: mid < range_high
   - 向下突破后回收: mid > range_low

4. 信号生成
   - 向上突破回收 → 做空 (SHORT)
   - 向下突破回收 → 做多 (LONG)

5. TP/SL 计算
   - 做空: SL = breakout_high + SL_BUFFER_BPS, TP = entry - 2*(SL - entry)
   - 做多: SL = breakout_low - SL_BUFFER_BPS, TP = entry + 2*(entry - SL)
```

#### 过滤器

| 过滤器 | 条件 | 说明 |
|--------|------|------|
| SpreadFilter | spread_bps < SPREAD_MAX_BPS | 点差过大不做 |
| QuoteAgeFilter | quote_age_ms < QUOTE_AGE_MAX_MS | 报价过旧不做 |
| ImpactFilter | impact_bps < IMPACT_MAX_BPS | 冲击过大不做 |
| VolatilityFilter | VOL_MIN < std_60s < VOL_MAX | 波动率过高/过低不做 |
| RSIFilter | RSI 极值后回归确认 | 超买超卖确认 |

**RSI 确认逻辑**
```
做空信号: 需要 RSI 曾达到 > RSI_OVERBOUGHT，且当前 RSI < RSI_OVERBOUGHT - 5
做多信号: 需要 RSI 曾达到 < RSI_OVERSOLD，且当前 RSI > RSI_OVERSOLD + 5
```

#### 数据库模型

**signals 表**
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| ts | DATETIME | 信号时间 |
| ticker | VARCHAR(10) | 代币符号 |
| side | VARCHAR(10) | LONG / SHORT |
| entry_price | DECIMAL | 入场价 |
| tp_price | DECIMAL | 止盈价 |
| sl_price | DECIMAL | 止损价 |
| confidence | DECIMAL | 置信度 (0-1) |
| rationale | TEXT | 信号理由 |
| filters_passed | TEXT | 通过的过滤器列表 |
| breakout_price | DECIMAL | 突破时价格 |
| reclaim_price | DECIMAL | 回收时价格 |
| status | VARCHAR(20) | PENDING/TP_HIT/SL_HIT/EXPIRED |
| result_pnl_bps | DECIMAL | 结果盈亏 (bps) |
| closed_at | DATETIME | 平仓时间 |

#### 接口契约

```
GET /api/signals/latest
  Response: { signal: {...} | null }

GET /api/signals/history
  Query: start, end, status, limit
  Response: { signals: [...], total: int }

GET /api/signals/stats
  Query: start, end
  Response: { win_rate, avg_pnl_bps, total_signals, ... }

WS /ws/signals
  Push: { "type": "signal", "data": {...} }
```

#### 检查清单
- [ ] models.py 定义 Signal 模型
- [ ] trap_signal.py 实现区间计算
- [ ] trap_signal.py 实现突破检测
- [ ] trap_signal.py 实现回收检测
- [ ] trap_signal.py 实现 TP/SL 计算
- [ ] filters.py 实现 SpreadFilter
- [ ] filters.py 实现 QuoteAgeFilter
- [ ] filters.py 实现 ImpactFilter
- [ ] filters.py 实现 VolatilityFilter
- [ ] filters.py 实现 RSIFilter（超买超卖确认）
- [ ] signal_engine.py 整合信号生成 + 过滤
- [ ] 信号状态跟踪（TP/SL 命中检测）
- [ ] REST API /api/signals/*
- [ ] WebSocket /ws/signals 推送
- [ ] 单元测试：信号生成逻辑

---

### 人员 4：预警与回测（Alert + Backtest）

#### 职责
1. 实现预警引擎（信号触发、价格异常、质量预警）
2. 实现回测框架
3. 实现走步验证（walk-forward）
4. 计算绩效指标

#### 产出文件
```
backend/
├── alerts/
│   ├── __init__.py
│   ├── alert_engine.py    # 预警引擎
│   └── notifiers.py       # 通知渠道
├── backtest/
│   ├── __init__.py
│   ├── backtester.py      # 回测核心
│   ├── walk_forward.py    # 走步验证
│   └── metrics.py         # 绩效指标
```

#### 预警类型

| 类型 | 触发条件 | 优先级 |
|------|----------|--------|
| SIGNAL_NEW | 新信号生成 | HIGH |
| SIGNAL_TP_HIT | 信号触达 TP | MEDIUM |
| SIGNAL_SL_HIT | 信号触达 SL | MEDIUM |
| PRICE_SPIKE | 1分钟涨跌幅 > 阈值 | HIGH |
| SPREAD_HIGH | spread_bps > 阈值 | MEDIUM |
| QUOTE_STALE | quote_age > 阈值 | LOW |
| DATA_ERROR | 数据采集异常 | HIGH |

#### 数据库模型

**alerts 表**
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| ts | DATETIME | 预警时间 |
| type | VARCHAR(50) | 预警类型 |
| priority | VARCHAR(10) | HIGH/MEDIUM/LOW |
| ticker | VARCHAR(10) | 代币符号 |
| message | TEXT | 预警内容 |
| data | TEXT | 关联数据 JSON |
| acknowledged | BOOLEAN | 是否已确认 |

**backtest_runs 表**
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| started_at | DATETIME | 开始时间 |
| finished_at | DATETIME | 结束时间 |
| params | TEXT | 参数 JSON |
| data_start | DATETIME | 数据起始 |
| data_end | DATETIME | 数据结束 |
| total_signals | INTEGER | 总信号数 |
| win_count | INTEGER | 盈利次数 |
| loss_count | INTEGER | 亏损次数 |
| win_rate | DECIMAL | 胜率 |
| avg_win_bps | DECIMAL | 平均盈利 |
| avg_loss_bps | DECIMAL | 平均亏损 |
| total_pnl_bps | DECIMAL | 总盈亏 |
| max_drawdown_bps | DECIMAL | 最大回撤 |
| sharpe_ratio | DECIMAL | 夏普率 |
| results_json | TEXT | 详细结果 |

#### 回测流程

```
1. 加载历史 features 数据
2. 按时间顺序遍历
3. 对每个时间点：
   a. 检查是否有持仓需要平仓（TP/SL）
   b. 运行信号引擎生成新信号
   c. 如无持仓且有信号，记录开仓
4. 统计绩效指标
5. 存储结果
```

#### 走步验证（Walk-Forward）

```
总数据: [===============================]
         训练窗口1  验证1
               训练窗口2  验证2
                     训练窗口3  验证3
                           ...

参数:
- TRAIN_WINDOW: 训练窗口大小（如 7 天）
- TEST_WINDOW: 验证窗口大小（如 1 天）
- STEP_SIZE: 步进大小（如 1 天）
```

#### 接口契约

```
POST /api/backtest/run
  Body: { start, end, params: {...} }
  Response: { run_id: int }

GET /api/backtest/results/{run_id}
  Response: { run: {...}, trades: [...] }

GET /api/backtest/list
  Query: limit
  Response: { runs: [...] }

POST /api/backtest/walk-forward
  Body: { start, end, train_window, test_window, step_size }
  Response: { run_id: int }

GET /api/alerts/history
  Query: type, priority, start, end, limit
  Response: { alerts: [...], total: int }

WS /ws/alerts
  Push: { "type": "alert", "data": {...} }
```

#### 检查清单
- [ ] models.py 添加 Alert, BacktestRun 模型
- [ ] alert_engine.py 实现预警检测逻辑
- [ ] alert_engine.py 实现信号状态跟踪（TP/SL 命中）
- [ ] notifiers.py 实现 WebSocket 通知
- [ ] notifiers.py 实现 Telegram 通知（可选）
- [ ] backtester.py 实现回测主循环
- [ ] backtester.py 实现 TP/SL 模拟
- [ ] metrics.py 实现胜率计算
- [ ] metrics.py 实现最大回撤计算
- [ ] metrics.py 实现夏普率计算
- [ ] walk_forward.py 实现走步验证
- [ ] REST API /api/backtest/*, /api/alerts/*
- [ ] WebSocket /ws/alerts 推送
- [ ] 单元测试：回测逻辑、指标计算

---

### 人员 5：前端仪表盘（Vue3 + ECharts）

#### 职责
1. 搭建 Vue3 + Vite + TypeScript 项目
2. 实现仪表盘、信号面板、预警中心、回测页面
3. 封装 API 调用与 WebSocket
4. 实现状态管理

#### 产出文件
```
frontend/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── index.html
├── src/
│   ├── main.ts
│   ├── App.vue
│   ├── router/
│   │   └── index.ts
│   ├── stores/
│   │   ├── market.ts        # 市场数据
│   │   ├── signals.ts       # 信号数据
│   │   └── alerts.ts        # 预警数据
│   ├── views/
│   │   ├── Dashboard.vue    # 仪表盘
│   │   ├── Signals.vue      # 信号面板
│   │   ├── Alerts.vue       # 预警中心
│   │   └── Backtest.vue     # 回测页面
│   ├── components/
│   │   ├── PriceChart.vue   # K线图
│   │   ├── SignalCard.vue   # 信号卡片
│   │   ├── AlertItem.vue    # 预警项
│   │   ├── MetricCard.vue   # 指标卡片
│   │   └── BacktestForm.vue # 回测表单
│   ├── api/
│   │   └── index.ts         # API 封装
│   ├── utils/
│   │   └── websocket.ts     # WebSocket 封装
│   └── types/
│       └── index.ts         # 类型定义
```

#### 页面设计

**1. Dashboard（仪表盘）**
```
┌────────────────────────────────────────────────────────┐
│  [TVL]   [24h Vol]   [Funding]   [Spread]   [L/S Ratio]│  <- 指标卡片
├────────────────────────────────────────────────────────┤
│                                                        │
│              ETH 1分钟 K线图                           │
│              （标注信号触发点）                         │
│                                                        │
├────────────────────────────────────────────────────────┤
│  最新信号                    │   最新预警              │
│  [SignalCard]                │   [AlertItem]           │
│  [SignalCard]                │   [AlertItem]           │
└────────────────────────────────────────────────────────┘
```

**2. Signals（信号面板）**
```
┌────────────────────────────────────────────────────────┐
│  统计: 今日信号 X 个  |  胜率 XX%  |  盈亏 +XX bps     │
├────────────────────────────────────────────────────────┤
│  [筛选: 状态/方向/时间范围]                            │
├────────────────────────────────────────────────────────┤
│  时间  │ 方向 │ 入场 │ TP │ SL │ 状态 │ 盈亏         │
│  ...   │ ...  │ ...  │ ...│ ...│ ...  │ ...          │
└────────────────────────────────────────────────────────┘
```

**3. Alerts（预警中心）**
```
┌────────────────────────────────────────────────────────┐
│  [筛选: 类型/优先级/时间范围]    [标记全部已读]        │
├────────────────────────────────────────────────────────┤
│  [AlertItem - HIGH - SIGNAL_NEW]                       │
│  [AlertItem - MEDIUM - SIGNAL_TP_HIT]                  │
│  [AlertItem - LOW - QUOTE_STALE]                       │
│  ...                                                   │
└────────────────────────────────────────────────────────┘
```

**4. Backtest（回测页面）**
```
┌────────────────────────────────────────────────────────┐
│  [BacktestForm]                                        │
│  数据范围: [起始] - [结束]                             │
│  参数: RANGE_WINDOW, BREAKOUT_THRESHOLD, ...           │
│  [运行回测]  [运行走步验证]                            │
├────────────────────────────────────────────────────────┤
│  回测结果                                              │
│  胜率: XX%  |  平均盈利: +XX bps  |  最大回撤: XX bps  │
│  [净值曲线图]                                          │
│  [交易列表]                                            │
└────────────────────────────────────────────────────────┘
```

#### API 封装

```typescript
// api/index.ts
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export const api = {
  // Snapshots
  getSnapshots: (limit = 100) => fetch(`${API_BASE}/api/snapshots?limit=${limit}`),
  getLatestSnapshot: () => fetch(`${API_BASE}/api/snapshots/latest`),
  
  // Features
  getLatestFeature: () => fetch(`${API_BASE}/api/features/latest`),
  getFeatureHistory: (start, end) => fetch(`${API_BASE}/api/features/history?start=${start}&end=${end}`),
  
  // Signals
  getLatestSignal: () => fetch(`${API_BASE}/api/signals/latest`),
  getSignalHistory: (params) => fetch(`${API_BASE}/api/signals/history?${new URLSearchParams(params)}`),
  getSignalStats: (start, end) => fetch(`${API_BASE}/api/signals/stats?start=${start}&end=${end}`),
  
  // Alerts
  getAlertHistory: (params) => fetch(`${API_BASE}/api/alerts/history?${new URLSearchParams(params)}`),
  
  // Backtest
  runBacktest: (body) => fetch(`${API_BASE}/api/backtest/run`, { method: 'POST', body: JSON.stringify(body) }),
  getBacktestResult: (runId) => fetch(`${API_BASE}/api/backtest/results/${runId}`),
  runWalkForward: (body) => fetch(`${API_BASE}/api/backtest/walk-forward`, { method: 'POST', body: JSON.stringify(body) }),
}
```

#### WebSocket 封装

```typescript
// utils/websocket.ts
export class WarpWebSocket {
  private ws: WebSocket | null = null
  private listeners: Map<string, Function[]> = new Map()
  
  connect(url: string) {
    this.ws = new WebSocket(url)
    this.ws.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      const handlers = this.listeners.get(msg.type) || []
      handlers.forEach(h => h(msg.data))
    }
  }
  
  on(type: string, handler: Function) {
    if (!this.listeners.has(type)) this.listeners.set(type, [])
    this.listeners.get(type)!.push(handler)
  }
  
  subscribe(channel: string) {
    this.ws?.send(JSON.stringify({ action: 'subscribe', channel }))
  }
}
```

#### 检查清单
- [ ] 项目初始化（Vite + Vue3 + TypeScript）
- [ ] 安装依赖（vue-router, pinia, echarts, axios）
- [ ] 路由配置（/, /signals, /alerts, /backtest）
- [ ] stores/market.ts 市场数据状态
- [ ] stores/signals.ts 信号状态
- [ ] stores/alerts.ts 预警状态
- [ ] api/index.ts API 封装
- [ ] utils/websocket.ts WebSocket 封装
- [ ] components/MetricCard.vue 指标卡片
- [ ] components/PriceChart.vue K线图（ECharts）
- [ ] components/SignalCard.vue 信号卡片
- [ ] components/AlertItem.vue 预警项
- [ ] components/BacktestForm.vue 回测表单
- [ ] views/Dashboard.vue 仪表盘
- [ ] views/Signals.vue 信号面板
- [ ] views/Alerts.vue 预警中心
- [ ] views/Backtest.vue 回测页面
- [ ] 响应式布局适配
- [ ] 深色主题（可选）

---

## 关键参数配置

```python
# backend/config.py

# === 数据采集 ===
VARIATIONAL_API_BASE = "https://omni-client-api.prod.ap-northeast-1.variational.io"
POLL_INTERVAL_SEC = 2          # 采样间隔（受 10/10s 限流约束）
MAX_RETRIES = 3                # 请求重试次数

# === 信号参数 ===
TICKER = "ETH"                 # 交易标的
RANGE_WINDOW_MIN = 20          # 假突破区间窗口（分钟）
BREAKOUT_THRESHOLD_BPS = 5     # 突破阈值（bps）
RECLAIM_TIMEOUT_SEC = 60       # 回收判定超时（秒）

# === 过滤器阈值 ===
SPREAD_MAX_BPS = 3             # 点差上限
IMPACT_MAX_BPS = 5             # 冲击上限
QUOTE_AGE_MAX_MS = 5000        # 报价新鲜度上限（毫秒）
VOL_MIN = 0.0001               # 最小波动率
VOL_MAX = 0.01                 # 最大波动率

# === RSI 参数 ===
RSI_PERIOD = 14                # RSI 周期
RSI_OVERBOUGHT = 75            # 超买阈值
RSI_OVERSOLD = 25              # 超卖阈值
RSI_CONFIRM_BUFFER = 5         # RSI 回归确认缓冲

# === TP/SL ===
SL_BUFFER_BPS = 2              # 止损 buffer（bps）
RR_RATIO = 2.0                 # 盈亏比

# === 回测 ===
BACKTEST_DEFAULT_DAYS = 7      # 默认回测天数
WALK_FORWARD_TRAIN_DAYS = 7    # 走步验证训练窗口
WALK_FORWARD_TEST_DAYS = 1     # 走步验证测试窗口

# === 数据库 ===
DATABASE_URL = "sqlite:///./variational.db"  # 开发环境
# DATABASE_URL = "postgresql://user:pass@host/db"  # 生产环境
```

---

## 执行时间线

```
Day 1
├── 人员 1: 项目初始化 + DB 模型 + API 客户端
├── 人员 2: 指标算法实现（RSI, z-score, ATR）
└── 人员 5: Vue 项目初始化 + 路由 + 基础布局

Day 2
├── 人员 1: 调度器 + REST API + WebSocket
├── 人员 2: 滚动窗口 + 特征计算器 + API
├── 人员 3: 信号模型 + 区间计算 + 突破检测
└── 人员 5: API 封装 + WebSocket 封装 + Store

Day 3
├── 人员 2: 完善特征 + 单元测试
├── 人员 3: 回收检测 + 过滤器实现
├── 人员 4: Alert 模型 + 预警引擎
└── 人员 5: Dashboard 页面 + K 线图

Day 4
├── 人员 3: 信号引擎整合 + TP/SL + API
├── 人员 4: 回测框架 + 绩效指标
└── 人员 5: Signals 页面 + Alerts 页面

Day 5
├── 人员 3: 信号状态跟踪 + WebSocket
├── 人员 4: 走步验证 + 回测 API
└── 人员 5: Backtest 页面 + 图表

Day 6
├── 全员: 集成测试
├── 全员: Bug 修复
└── 人员 4: 参数调优

Day 7
├── 人员 4: 走步验证报告
├── 全员: 文档完善
└── 全员: 部署上线
```

---

## 沟通与协作

### 每日站会
- 时间：每天 10:00
- 内容：昨日完成 / 今日计划 / 阻塞问题

### 接口对接
- 人员 1 完成 API 后通知人员 2、5
- 人员 2 完成 API 后通知人员 3
- 人员 3 完成 API 后通知人员 4、5

### Git 分支策略
```
main          <- 稳定版本
├── dev       <- 开发集成
├── feat/collector     <- 人员 1
├── feat/features      <- 人员 2
├── feat/signals       <- 人员 3
├── feat/backtest      <- 人员 4
└── feat/frontend      <- 人员 5
```

### 代码审查
- 每个 PR 至少一人 review
- 重点检查：接口契约一致性、错误处理、测试覆盖

---

## 风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| API 更新频率不够 | 信号延迟 | quote_age 过滤 + 降低预期频率 |
| API 限流触发 | 数据缺失 | 限流保护 + 指数退避重试 |
| 胜率无法达到 80% | 策略失效 | 走步验证 + 参数优化 + 降低频率 |
| 前后端接口不一致 | 集成困难 | 先定接口契约 + Mock 数据开发 |
| 数据库性能瓶颈 | 查询慢 | 索引优化 + 数据归档 |

---

## 附录

### A. Variational API 响应示例（ETH）

```json
{
  "ticker": "ETH",
  "name": "Ethereum",
  "mark_price": "3216.255",
  "volume_24h": "386355837.510539",
  "funding_rate": "0.011135",
  "funding_interval_s": 28800,
  "base_spread_bps": "0.5289",
  "open_interest": {
    "long_open_interest": "50580505.88",
    "short_open_interest": "45203744.92"
  },
  "quotes": {
    "updated_at": "2026-01-06T09:09:33.367550571Z",
    "size_1k": { "bid": "3216.01", "ask": "3216.17" },
    "size_100k": { "bid": "3215.26", "ask": "3216.87" }
  }
}
```

### B. Signal 对象示例

```json
{
  "id": 1,
  "ts": "2026-01-06T09:15:00Z",
  "ticker": "ETH",
  "side": "SHORT",
  "entry_price": 3220.50,
  "tp_price": 3210.50,
  "sl_price": 3225.50,
  "confidence": 0.85,
  "rationale": "假突破回收: 突破20分钟高点3222后回收至3220.50, RSI从78回落至72",
  "filters_passed": ["SpreadFilter", "QuoteAgeFilter", "RSIFilter"],
  "breakout_price": 3222.30,
  "reclaim_price": 3220.50,
  "status": "PENDING"
}
```

### C. 绩效指标公式

```
胜率 = win_count / total_signals

平均盈利 = sum(win_pnl) / win_count
平均亏损 = sum(loss_pnl) / loss_count

盈亏比 = avg_win / |avg_loss|

最大回撤 = max(peak - trough) for all peaks

夏普率 = (avg_return - risk_free) / std(returns) * sqrt(252 * 24 * 60)
```
