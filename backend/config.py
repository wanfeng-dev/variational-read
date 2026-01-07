# -*- coding: utf-8 -*-
"""
全局配置文件
"""
import os

# === 多标的配置 ===
TICKERS = ["BTC", "ETH"]
DATA_SOURCES = ["variational", "bybit"]

# === Variational 数据采集 ===
VARIATIONAL_API_BASE = "https://omni-client-api.prod.ap-northeast-1.variational.io"
POLL_INTERVAL_SEC = 2          # 采样间隔（受 10/10s 限流约束）
MAX_RETRIES = 3                # 请求重试次数
RETRY_DELAY_SEC = 1            # 重试间隔基数（秒）

# === Bybit 数据采集 ===
BYBIT_API_BASE = "https://api.bybit.com"
BYBIT_CATEGORY = "linear"      # USDT 永续合约
BYBIT_SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}
BYBIT_POLL_INTERVAL_SEC = 1    # Bybit 公开API无严格限流
BYBIT_TIMEOUT_SEC = 5

# === 限流配置 ===
RATE_LIMIT_REQUESTS = 10       # 最大请求数
RATE_LIMIT_WINDOW_SEC = 10     # 限流窗口（秒）

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
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./variational.db")

# === 日志配置 ===
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
