# 人员 2：特征计算 + 信号引擎多标的改造

## 职责
FeatureCalculator 和 SignalEngine 支持多标的独立运行

## 产出文件
```
backend/
├── features/
│   ├── calculator.py            # 修改：按 (source, ticker) 维护独立窗口
│   └── rolling_window.py        # 修改：支持多实例
├── signals/
│   ├── signal_engine.py         # 修改：按 (source, ticker) 独立状态
│   ├── trap_signal.py           # 修改：支持多标的区间
│   └── filters.py               # 检查：确保参数可配置
├── alerts/
│   └── alert_engine.py          # 修改：预警包含 source 信息
├── db/
│   └── models.py                # 修改：Feature/Signal 增加 source 字段
└── main.py                      # 修改：多实例初始化
```

---

## 数据流示意

```
Snapshot(source=bybit, ticker=BTC)
    ↓
FeatureCalculator.windows[("bybit", "BTC")]
    ↓
Feature(source=bybit, ticker=BTC)
    ↓
SignalEngine.breakout_states[("bybit", "BTC")]
    ↓
Signal(source=bybit, ticker=BTC)
```

4 个独立数据流：
- variational-BTC
- variational-ETH
- bybit-BTC
- bybit-ETH

---

## 详细任务

### 1. rolling_window.py 修改

支持按 key 创建独立窗口实例：

```python
# -*- coding: utf-8 -*-
"""
滚动窗口管理
支持多数据源多标的独立窗口
"""
from typing import Dict, Tuple, Optional, List
from collections import deque
from dataclasses import dataclass
from datetime import datetime


@dataclass
class WindowEntry:
    """窗口数据条目"""
    ts: datetime
    mid: float
    # ... 其他字段


class RollingWindow:
    """单个滚动窗口"""
    
    def __init__(self, max_size: int = 600):
        self.max_size = max_size
        self.data: deque = deque(maxlen=max_size)
    
    def add(self, entry: WindowEntry):
        self.data.append(entry)
    
    def get_values(self, field: str) -> List:
        return [getattr(e, field) for e in self.data]
    
    # ... 其他方法


class RollingWindowManager:
    """
    滚动窗口管理器
    按 (source, ticker) 维护独立窗口
    """
    
    def __init__(self, max_size: int = 600):
        self.max_size = max_size
        self._windows: Dict[Tuple[str, str], RollingWindow] = {}
    
    def get_window(self, source: str, ticker: str) -> RollingWindow:
        """
        获取指定数据源和标的的窗口
        如不存在则创建
        """
        key = (source, ticker)
        if key not in self._windows:
            self._windows[key] = RollingWindow(self.max_size)
        return self._windows[key]
    
    def add_entry(self, source: str, ticker: str, entry: WindowEntry):
        """添加数据到对应窗口"""
        window = self.get_window(source, ticker)
        window.add(entry)
    
    def get_all_keys(self) -> List[Tuple[str, str]]:
        """获取所有窗口的 key"""
        return list(self._windows.keys())
```

---

### 2. calculator.py 修改

按 (source, ticker) 维护独立窗口计算特征：

```python
# -*- coding: utf-8 -*-
"""
特征计算器
支持多数据源多标的独立计算
"""
from typing import Dict, Tuple, Optional, Callable, List
from datetime import datetime

from features.rolling_window import RollingWindowManager, WindowEntry
from features.indicators import calculate_rsi, calculate_z_score, calculate_std
from db.database import SessionLocal
from db.models import Feature, Snapshot


class FeatureCalculator:
    """
    特征计算器
    为每个 (source, ticker) 维护独立的滚动窗口和计算状态
    """
    
    def __init__(self, window_size: int = 600):
        self.window_manager = RollingWindowManager(max_size=window_size)
        self.window_size = window_size
        self._callbacks: List[Callable] = []
        self._initialized: Dict[Tuple[str, str], bool] = {}
    
    @property
    def is_initialized(self) -> bool:
        """至少有一个窗口初始化"""
        return any(self._initialized.values())
    
    def warmup_from_db(self):
        """从数据库预热所有数据源和标的的窗口"""
        from config import DATA_SOURCES, TICKERS
        
        db = SessionLocal()
        try:
            for source in DATA_SOURCES:
                for ticker in TICKERS:
                    snapshots = (
                        db.query(Snapshot)
                        .filter(Snapshot.source == source, Snapshot.ticker == ticker)
                        .order_by(Snapshot.ts.desc())
                        .limit(self.window_size)
                        .all()
                    )
                    
                    if snapshots:
                        # 按时间正序添加
                        for s in reversed(snapshots):
                            entry = WindowEntry(
                                ts=s.ts,
                                mid=float(s.mid) if s.mid else 0,
                                # ... 其他字段
                            )
                            self.window_manager.add_entry(source, ticker, entry)
                        
                        self._initialized[(source, ticker)] = True
                        logger.info(f"[{source}-{ticker}] 预热完成，加载 {len(snapshots)} 条数据")
        finally:
            db.close()
    
    def on_feature(self, callback: Callable):
        """注册特征计算完成回调"""
        self._callbacks.append(callback)
    
    async def compute(self, snapshot_dict: dict) -> Optional[dict]:
        """
        计算特征
        根据快照的 source 和 ticker 选择对应窗口
        """
        source = snapshot_dict.get("source", "variational")
        ticker = snapshot_dict.get("ticker", "ETH")
        key = (source, ticker)
        
        # 获取对应窗口
        window = self.window_manager.get_window(source, ticker)
        
        # 添加新数据
        mid = snapshot_dict.get("mid")
        if mid is None:
            return None
        
        entry = WindowEntry(
            ts=snapshot_dict["ts"],
            mid=float(mid),
            # ... 其他字段
        )
        window.add(entry)
        
        # 计算特征
        feature_dict = self._calculate_features(window, snapshot_dict, source, ticker)
        
        if feature_dict:
            # 保存到数据库
            await self._save_feature(feature_dict)
            
            # 触发回调
            for callback in self._callbacks:
                await callback(feature_dict)
        
        return feature_dict
    
    def _calculate_features(
        self, 
        window: 'RollingWindow', 
        snapshot: dict,
        source: str,
        ticker: str
    ) -> Optional[dict]:
        """计算所有特征"""
        if len(window.data) < 2:
            return None
        
        mids = window.get_values("mid")
        now = snapshot["ts"]
        
        return {
            "ts": now,
            "source": source,  # 新增
            "ticker": ticker,
            "mid": snapshot.get("mid"),
            "return_5s": self._calc_return(mids, 3),   # ~5秒
            "return_15s": self._calc_return(mids, 8),  # ~15秒
            "return_60s": self._calc_return(mids, 30), # ~60秒
            "std_60s": calculate_std(mids[-30:]) if len(mids) >= 30 else None,
            "rsi_14": calculate_rsi(mids, 14),
            "z_score": calculate_z_score(mids),
            "range_high_20m": max(mids[-600:]) if len(mids) >= 600 else max(mids),
            "range_low_20m": min(mids[-600:]) if len(mids) >= 600 else min(mids),
            "spread_bps": snapshot.get("spread_bps"),
            "impact_buy_bps": snapshot.get("impact_buy_bps"),
            "impact_sell_bps": snapshot.get("impact_sell_bps"),
            "quote_age_ms": snapshot.get("quote_age_ms"),
            "long_short_ratio": self._calc_ls_ratio(snapshot),
        }
    
    async def _save_feature(self, feature_dict: dict):
        """保存特征到数据库"""
        db = SessionLocal()
        try:
            feature = Feature(
                ts=feature_dict["ts"],
                source=feature_dict["source"],  # 新增
                ticker=feature_dict["ticker"],
                # ... 其他字段
            )
            db.add(feature)
            db.commit()
        finally:
            db.close()
```

---

### 3. trap_signal.py 修改

区间状态按 (source, ticker) 独立维护：

```python
# -*- coding: utf-8 -*-
"""
假突破回收信号
支持多数据源多标的独立状态
"""
from typing import Dict, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from config import RANGE_WINDOW_MIN, BREAKOUT_THRESHOLD_BPS, RECLAIM_TIMEOUT_SEC


@dataclass
class RangeState:
    """区间状态"""
    range_high: Decimal = Decimal("0")
    range_low: Decimal = Decimal("0")
    range_mid: Decimal = Decimal("0")
    last_update: datetime = field(default_factory=datetime.utcnow)


@dataclass
class BreakoutState:
    """突破状态"""
    is_active: bool = False
    direction: str = ""  # "UP" / "DOWN"
    breakout_price: Decimal = Decimal("0")
    breakout_time: Optional[datetime] = None
    extreme_price: Decimal = Decimal("0")  # 突破后的极值


class TrapSignalDetector:
    """
    假突破回收信号检测器
    为每个 (source, ticker) 维护独立状态
    """
    
    def __init__(self):
        # 区间状态: {(source, ticker): RangeState}
        self._range_states: Dict[Tuple[str, str], RangeState] = {}
        # 突破状态: {(source, ticker): BreakoutState}
        self._breakout_states: Dict[Tuple[str, str], BreakoutState] = {}
    
    def get_range_state(self, source: str, ticker: str) -> RangeState:
        """获取区间状态"""
        key = (source, ticker)
        if key not in self._range_states:
            self._range_states[key] = RangeState()
        return self._range_states[key]
    
    def get_breakout_state(self, source: str, ticker: str) -> BreakoutState:
        """获取突破状态"""
        key = (source, ticker)
        if key not in self._breakout_states:
            self._breakout_states[key] = BreakoutState()
        return self._breakout_states[key]
    
    def update_range(self, source: str, ticker: str, feature: dict):
        """
        更新区间
        使用 feature 中的 range_high_20m 和 range_low_20m
        """
        state = self.get_range_state(source, ticker)
        
        high = feature.get("range_high_20m")
        low = feature.get("range_low_20m")
        
        if high and low:
            state.range_high = Decimal(str(high))
            state.range_low = Decimal(str(low))
            state.range_mid = (state.range_high + state.range_low) / 2
            state.last_update = feature["ts"]
    
    def detect(self, source: str, ticker: str, feature: dict) -> Optional[dict]:
        """
        检测假突破回收信号
        
        Returns:
            信号字典或 None
        """
        key = (source, ticker)
        range_state = self.get_range_state(source, ticker)
        breakout_state = self.get_breakout_state(source, ticker)
        
        mid = feature.get("mid")
        if not mid:
            return None
        mid = Decimal(str(mid))
        now = feature["ts"]
        
        # 1. 更新区间
        self.update_range(source, ticker, feature)
        
        # 2. 检查突破超时
        if breakout_state.is_active:
            if (now - breakout_state.breakout_time).total_seconds() > RECLAIM_TIMEOUT_SEC:
                # 突破超时，重置
                breakout_state.is_active = False
        
        # 3. 检测突破
        if not breakout_state.is_active:
            threshold = range_state.range_high * Decimal(str(BREAKOUT_THRESHOLD_BPS)) / 10000
            
            if mid > range_state.range_high + threshold:
                # 向上突破
                breakout_state.is_active = True
                breakout_state.direction = "UP"
                breakout_state.breakout_price = mid
                breakout_state.breakout_time = now
                breakout_state.extreme_price = mid
                return None
            
            elif mid < range_state.range_low - threshold:
                # 向下突破
                breakout_state.is_active = True
                breakout_state.direction = "DOWN"
                breakout_state.breakout_price = mid
                breakout_state.breakout_time = now
                breakout_state.extreme_price = mid
                return None
        
        # 4. 更新极值
        if breakout_state.is_active:
            if breakout_state.direction == "UP":
                breakout_state.extreme_price = max(breakout_state.extreme_price, mid)
            else:
                breakout_state.extreme_price = min(breakout_state.extreme_price, mid)
        
        # 5. 检测回收
        if breakout_state.is_active:
            if breakout_state.direction == "UP" and mid < range_state.range_high:
                # 向上突破后回收 -> 做空
                signal = self._create_signal(
                    source=source,
                    ticker=ticker,
                    side="SHORT",
                    entry_price=mid,
                    breakout_state=breakout_state,
                    range_state=range_state,
                    feature=feature,
                )
                breakout_state.is_active = False
                return signal
            
            elif breakout_state.direction == "DOWN" and mid > range_state.range_low:
                # 向下突破后回收 -> 做多
                signal = self._create_signal(
                    source=source,
                    ticker=ticker,
                    side="LONG",
                    entry_price=mid,
                    breakout_state=breakout_state,
                    range_state=range_state,
                    feature=feature,
                )
                breakout_state.is_active = False
                return signal
        
        return None
    
    def _create_signal(self, source: str, ticker: str, side: str, 
                       entry_price: Decimal, breakout_state: BreakoutState,
                       range_state: RangeState, feature: dict) -> dict:
        """创建信号"""
        from config import SL_BUFFER_BPS, RR_RATIO
        
        buffer = entry_price * Decimal(str(SL_BUFFER_BPS)) / 10000
        
        if side == "SHORT":
            sl_price = breakout_state.extreme_price + buffer
            tp_price = entry_price - (sl_price - entry_price) * Decimal(str(RR_RATIO))
        else:  # LONG
            sl_price = breakout_state.extreme_price - buffer
            tp_price = entry_price + (entry_price - sl_price) * Decimal(str(RR_RATIO))
        
        return {
            "ts": feature["ts"],
            "source": source,  # 新增
            "ticker": ticker,
            "side": side,
            "entry_price": entry_price,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "breakout_price": breakout_state.breakout_price,
            "reclaim_price": entry_price,
            "rationale": f"假突破回收: 突破{range_state.range_high if side == 'SHORT' else range_state.range_low}后回收",
        }
    
    def has_active_breakout(self, source: str, ticker: str) -> bool:
        """检查是否有活跃突破"""
        state = self._breakout_states.get((source, ticker))
        return state.is_active if state else False
```

---

### 4. signal_engine.py 修改

活跃信号和状态按 (source, ticker) 分组：

```python
# -*- coding: utf-8 -*-
"""
信号引擎
支持多数据源多标的独立信号生成
"""
from typing import Dict, Tuple, Optional, List, Callable
from datetime import datetime
from decimal import Decimal

from signals.trap_signal import TrapSignalDetector
from signals.filters import SignalFilter
from db.database import SessionLocal
from db.models import Signal


class SignalEngine:
    """
    信号引擎
    为每个 (source, ticker) 独立处理信号
    """
    
    def __init__(self):
        self.trap_detector = TrapSignalDetector()
        self.signal_filter = SignalFilter()
        
        # 活跃信号: {(source, ticker): List[Signal]}
        self._active_signals: Dict[Tuple[str, str], List[dict]] = {}
        
        # 回调
        self._signal_callbacks: List[Callable] = []
        self._close_callbacks: List[Callable] = []
    
    @property
    def active_signal_count(self) -> int:
        """所有活跃信号数量"""
        return sum(len(signals) for signals in self._active_signals.values())
    
    @property
    def has_active_breakout(self) -> bool:
        """是否有任何活跃突破"""
        from config import DATA_SOURCES, TICKERS
        for source in DATA_SOURCES:
            for ticker in TICKERS:
                if self.trap_detector.has_active_breakout(source, ticker):
                    return True
        return False
    
    @property
    def active_signals(self) -> List[dict]:
        """获取所有活跃信号列表"""
        result = []
        for signals in self._active_signals.values():
            result.extend(signals)
        return result
    
    def get_active_signals(self, source: str, ticker: str) -> List[dict]:
        """获取指定数据源和标的的活跃信号"""
        return self._active_signals.get((source, ticker), [])
    
    def on_signal(self, callback: Callable):
        """注册新信号回调"""
        self._signal_callbacks.append(callback)
    
    def on_signal_close(self, callback: Callable):
        """注册信号关闭回调"""
        self._close_callbacks.append(callback)
    
    def load_active_signals(self):
        """从数据库加载活跃信号"""
        db = SessionLocal()
        try:
            pending_signals = (
                db.query(Signal)
                .filter(Signal.status == "PENDING")
                .all()
            )
            
            for s in pending_signals:
                key = (s.source, s.ticker)
                if key not in self._active_signals:
                    self._active_signals[key] = []
                self._active_signals[key].append(s.to_dict())
            
            logger.info(f"加载 {len(pending_signals)} 个活跃信号")
        finally:
            db.close()
    
    async def process(self, feature_dict: dict):
        """
        处理新特征，检测信号
        
        1. 检查活跃信号是否触达 TP/SL
        2. 检测新信号
        """
        source = feature_dict.get("source", "variational")
        ticker = feature_dict.get("ticker", "ETH")
        key = (source, ticker)
        
        mid = feature_dict.get("mid")
        if not mid:
            return
        mid = Decimal(str(mid))
        
        # 1. 检查活跃信号
        await self._check_active_signals(source, ticker, mid, feature_dict["ts"])
        
        # 2. 检测新信号（仅当无活跃信号时）
        if not self._active_signals.get(key):
            signal = self.trap_detector.detect(source, ticker, feature_dict)
            
            if signal:
                # 应用过滤器
                if self.signal_filter.apply(feature_dict):
                    await self._save_and_notify_signal(signal)
    
    async def _check_active_signals(self, source: str, ticker: str, 
                                     mid: Decimal, ts: datetime):
        """检查活跃信号是否触达 TP/SL"""
        key = (source, ticker)
        active = self._active_signals.get(key, [])
        
        for signal in active[:]:  # 复制列表以便修改
            tp = Decimal(str(signal["tp_price"]))
            sl = Decimal(str(signal["sl_price"]))
            side = signal["side"]
            
            hit = None
            if side == "LONG":
                if mid >= tp:
                    hit = "TP_HIT"
                elif mid <= sl:
                    hit = "SL_HIT"
            else:  # SHORT
                if mid <= tp:
                    hit = "TP_HIT"
                elif mid >= sl:
                    hit = "SL_HIT"
            
            if hit:
                await self._close_signal(signal, hit, mid, ts)
                active.remove(signal)
    
    async def _save_and_notify_signal(self, signal_dict: dict):
        """保存并通知新信号"""
        db = SessionLocal()
        try:
            signal = Signal(
                ts=signal_dict["ts"],
                source=signal_dict["source"],  # 新增
                ticker=signal_dict["ticker"],
                side=signal_dict["side"],
                entry_price=signal_dict["entry_price"],
                tp_price=signal_dict["tp_price"],
                sl_price=signal_dict["sl_price"],
                breakout_price=signal_dict.get("breakout_price"),
                reclaim_price=signal_dict.get("reclaim_price"),
                rationale=signal_dict.get("rationale"),
                status="PENDING",
            )
            db.add(signal)
            db.commit()
            db.refresh(signal)
            
            signal_dict["id"] = signal.id
            
            # 添加到活跃列表
            key = (signal_dict["source"], signal_dict["ticker"])
            if key not in self._active_signals:
                self._active_signals[key] = []
            self._active_signals[key].append(signal.to_dict())
            
            # 触发回调
            for callback in self._signal_callbacks:
                await callback(signal.to_dict())
                
        finally:
            db.close()
```

---

### 5. alert_engine.py 修改

预警消息包含 source 和 ticker：

```python
async def create_alert(self, alert_type: str, source: str, ticker: str, 
                       message: str, data: dict = None, priority: str = "MEDIUM"):
    """
    创建预警
    """
    # 消息前缀
    full_message = f"[{source}-{ticker}] {message}"
    
    db = SessionLocal()
    try:
        alert = Alert(
            ts=datetime.utcnow(),
            type=alert_type,
            priority=priority,
            ticker=ticker,
            message=full_message,
            data=json.dumps(data) if data else None,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        
        # 推送
        await self.notifier.notify(alert.to_dict())
        
    finally:
        db.close()
```

---

### 6. models.py 修改

Feature 和 Signal 增加 source 字段：

```python
class Feature(Base):
    __tablename__ = "features"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    source = Column(String(20), nullable=False, default="variational", index=True)  # 新增
    ticker = Column(String(10), nullable=False, default="ETH", index=True)
    # ... 其他字段

    __table_args__ = (
        Index("ix_features_source_ticker_ts", "source", "ticker", "ts"),
    )


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    source = Column(String(20), nullable=False, default="variational", index=True)  # 新增
    ticker = Column(String(10), nullable=False, default="ETH", index=True)
    # ... 其他字段

    __table_args__ = (
        Index("ix_signals_source_ticker_ts", "source", "ticker", "ts"),
        Index("ix_signals_status", "status"),
    )
```

---

### 7. main.py 修改

多实例初始化与回调路由：

```python
# 特征计算器（单例，内部管理多窗口）
feature_calculator = FeatureCalculator()

# 信号引擎（单例，内部管理多状态）
signal_engine = SignalEngine()


async def on_new_snapshot(snapshot_dict: dict):
    """
    新快照回调
    根据 source 和 ticker 路由到对应处理
    """
    source = snapshot_dict.get("source", "variational")
    ticker = snapshot_dict.get("ticker", "ETH")
    
    logger.debug(f"[{source}-{ticker}] 收到新快照")
    
    # 广播快照
    await broadcast_snapshot(snapshot_dict)
    
    # 计算特征（内部会根据 source+ticker 选择窗口）
    await feature_calculator.compute(snapshot_dict)


async def on_new_feature(feature_dict: dict):
    """
    新特征回调
    触发信号引擎处理
    """
    source = feature_dict.get("source", "variational")
    ticker = feature_dict.get("ticker", "ETH")
    
    logger.debug(f"[{source}-{ticker}] 处理新特征")
    
    # 信号引擎处理（内部会根据 source+ticker 选择状态）
    await signal_engine.process(feature_dict)
```

---

## 检查清单

- [ ] rolling_window.py 支持多实例 key
- [ ] calculator.py 按 (source, ticker) 维护独立窗口
- [ ] Feature 模型增加 source 字段
- [ ] trap_signal.py 区间状态多标的独立
- [ ] signal_engine.py 活跃信号/突破状态多标的独立
- [ ] Signal 模型增加 source 字段
- [ ] alert_engine.py 预警消息包含 source/ticker
- [ ] main.py 多实例初始化与回调路由
- [ ] 单元测试：多标的特征计算独立性
- [ ] 单元测试：多标的信号引擎独立性

---

## 对接说明

**依赖人员 1**：
- base_client.py 接口定义
- models.py Snapshot source 字段

**完成后通知人员 3**：
- Feature/Signal 新增 source 字段
- API 返回数据格式变化

## Git 分支

```
feat/multi-ticker-engine
```
