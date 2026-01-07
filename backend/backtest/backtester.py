# -*- coding: utf-8 -*-
"""
回测核心模块
实现回测主循环和 TP/SL 模拟
"""
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from enum import Enum

from sqlalchemy.orm import Session
from sqlalchemy import and_

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.models import Snapshot, BacktestRun
from config import (
    TICKER,
    RANGE_WINDOW_MIN,
    BREAKOUT_THRESHOLD_BPS,
    RECLAIM_TIMEOUT_SEC,
    SPREAD_MAX_BPS,
    QUOTE_AGE_MAX_MS,
    VOL_MIN,
    VOL_MAX,
    SL_BUFFER_BPS,
    RR_RATIO,
)
from .metrics import TradeResult, calculate_metrics

logger = logging.getLogger(__name__)


class TradeStatus(str, Enum):
    """交易状态"""
    OPEN = "OPEN"
    TP_HIT = "TP_HIT"
    SL_HIT = "SL_HIT"
    EXPIRED = "EXPIRED"


class TradeSide(str, Enum):
    """交易方向"""
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class Trade:
    """交易记录"""
    entry_time: datetime
    entry_price: float
    side: TradeSide
    tp_price: float
    sl_price: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    status: TradeStatus = TradeStatus.OPEN
    pnl_bps: float = 0.0
    rationale: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
            "entry_price": self.entry_price,
            "side": self.side.value,
            "tp_price": self.tp_price,
            "sl_price": self.sl_price,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "exit_price": self.exit_price,
            "status": self.status.value,
            "pnl_bps": self.pnl_bps,
            "rationale": self.rationale,
        }


@dataclass
class BacktestResult:
    """回测结果"""
    run_id: Optional[int] = None
    data_start: Optional[datetime] = None
    data_end: Optional[datetime] = None
    params: Dict[str, Any] = field(default_factory=dict)
    trades: List[Trade] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    equity_curve: List[float] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "run_id": self.run_id,
            "data_start": self.data_start.isoformat() if self.data_start else None,
            "data_end": self.data_end.isoformat() if self.data_end else None,
            "params": self.params,
            "trades": [t.to_dict() for t in self.trades],
            "metrics": self.metrics,
            "equity_curve": self.equity_curve,
        }


class SignalGenerator:
    """
    信号生成器
    实现假突破回收（Trap）信号逻辑
    """
    
    def __init__(
        self,
        range_window_min: int = RANGE_WINDOW_MIN,
        breakout_threshold_bps: float = BREAKOUT_THRESHOLD_BPS,
        reclaim_timeout_sec: int = RECLAIM_TIMEOUT_SEC,
        sl_buffer_bps: float = SL_BUFFER_BPS,
        rr_ratio: float = RR_RATIO,
    ):
        self.range_window_min = range_window_min
        self.breakout_threshold_bps = breakout_threshold_bps
        self.reclaim_timeout_sec = reclaim_timeout_sec
        self.sl_buffer_bps = sl_buffer_bps
        self.rr_ratio = rr_ratio
        
        # 状态变量
        self._price_history: List[tuple] = []  # (timestamp, price)
        self._breakout_state = None  # {"direction": "UP"/"DOWN", "time": datetime, "extreme": price}
        
    def reset(self):
        """重置状态"""
        self._price_history = []
        self._breakout_state = None
        
    def update(self, ts: datetime, mid: float) -> Optional[Dict[str, Any]]:
        """
        更新价格并检测信号
        
        Args:
            ts: 时间戳
            mid: 中间价
            
        Returns:
            信号字典（如果触发）或 None
        """
        # 更新价格历史
        self._price_history.append((ts, mid))
        
        # 清理过期数据
        cutoff = ts - timedelta(minutes=self.range_window_min)
        self._price_history = [(t, p) for t, p in self._price_history if t >= cutoff]
        
        if len(self._price_history) < 2:
            return None
            
        # 计算区间
        prices = [p for _, p in self._price_history]
        range_high = max(prices)
        range_low = min(prices)
        
        if range_high == range_low:
            return None
            
        # 突破阈值（bps 转换）
        threshold = (range_high - range_low) * (self.breakout_threshold_bps / 10000)
        
        # 检测突破
        if self._breakout_state is None:
            if mid > range_high + threshold:
                # 向上突破
                self._breakout_state = {
                    "direction": "UP",
                    "time": ts,
                    "extreme": mid,
                    "range_high": range_high,
                    "range_low": range_low,
                }
            elif mid < range_low - threshold:
                # 向下突破
                self._breakout_state = {
                    "direction": "DOWN",
                    "time": ts,
                    "extreme": mid,
                    "range_high": range_high,
                    "range_low": range_low,
                }
        else:
            # 检测回收
            elapsed = (ts - self._breakout_state["time"]).total_seconds()
            
            if elapsed > self.reclaim_timeout_sec:
                # 超时，重置状态
                self._breakout_state = None
                return None
                
            if self._breakout_state["direction"] == "UP":
                # 更新极值
                if mid > self._breakout_state["extreme"]:
                    self._breakout_state["extreme"] = mid
                    
                # 检测回收
                if mid < self._breakout_state["range_high"]:
                    # 向上突破后回收 → 做空
                    signal = self._generate_short_signal(
                        ts=ts,
                        entry_price=mid,
                        breakout_extreme=self._breakout_state["extreme"],
                        range_high=self._breakout_state["range_high"],
                    )
                    self._breakout_state = None
                    return signal
                    
            else:  # DOWN
                # 更新极值
                if mid < self._breakout_state["extreme"]:
                    self._breakout_state["extreme"] = mid
                    
                # 检测回收
                if mid > self._breakout_state["range_low"]:
                    # 向下突破后回收 → 做多
                    signal = self._generate_long_signal(
                        ts=ts,
                        entry_price=mid,
                        breakout_extreme=self._breakout_state["extreme"],
                        range_low=self._breakout_state["range_low"],
                    )
                    self._breakout_state = None
                    return signal
                    
        return None
        
    def _generate_long_signal(
        self,
        ts: datetime,
        entry_price: float,
        breakout_extreme: float,
        range_low: float,
    ) -> Dict[str, Any]:
        """生成做多信号"""
        # SL 设置在突破极低点下方
        sl_buffer = entry_price * (self.sl_buffer_bps / 10000)
        sl_price = breakout_extreme - sl_buffer
        
        # TP 根据 RR 比例计算
        risk = entry_price - sl_price
        tp_price = entry_price + risk * self.rr_ratio
        
        return {
            "ts": ts,
            "side": TradeSide.LONG,
            "entry_price": entry_price,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "breakout_price": breakout_extreme,
            "rationale": f"假突破回收: 向下突破后回收至 {entry_price:.2f}",
        }
        
    def _generate_short_signal(
        self,
        ts: datetime,
        entry_price: float,
        breakout_extreme: float,
        range_high: float,
    ) -> Dict[str, Any]:
        """生成做空信号"""
        # SL 设置在突破极高点上方
        sl_buffer = entry_price * (self.sl_buffer_bps / 10000)
        sl_price = breakout_extreme + sl_buffer
        
        # TP 根据 RR 比例计算
        risk = sl_price - entry_price
        tp_price = entry_price - risk * self.rr_ratio
        
        return {
            "ts": ts,
            "side": TradeSide.SHORT,
            "entry_price": entry_price,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "breakout_price": breakout_extreme,
            "rationale": f"假突破回收: 向上突破后回收至 {entry_price:.2f}",
        }


class Backtester:
    """
    回测器
    实现历史数据回放和 TP/SL 模拟
    """
    
    def __init__(
        self,
        params: Optional[Dict[str, Any]] = None,
    ):
        """
        初始化回测器
        
        Args:
            params: 自定义参数（覆盖默认配置）
        """
        self.params = params or {}
        
        # 合并默认参数
        self.range_window_min = self.params.get("range_window_min", RANGE_WINDOW_MIN)
        self.breakout_threshold_bps = self.params.get("breakout_threshold_bps", BREAKOUT_THRESHOLD_BPS)
        self.reclaim_timeout_sec = self.params.get("reclaim_timeout_sec", RECLAIM_TIMEOUT_SEC)
        self.sl_buffer_bps = self.params.get("sl_buffer_bps", SL_BUFFER_BPS)
        self.rr_ratio = self.params.get("rr_ratio", RR_RATIO)
        self.spread_max_bps = self.params.get("spread_max_bps", SPREAD_MAX_BPS)
        self.quote_age_max_ms = self.params.get("quote_age_max_ms", QUOTE_AGE_MAX_MS)
        
        # 信号生成器
        self.signal_generator = SignalGenerator(
            range_window_min=self.range_window_min,
            breakout_threshold_bps=self.breakout_threshold_bps,
            reclaim_timeout_sec=self.reclaim_timeout_sec,
            sl_buffer_bps=self.sl_buffer_bps,
            rr_ratio=self.rr_ratio,
        )
        
    def run(
        self,
        db: Session,
        start: datetime,
        end: datetime,
        ticker: str = TICKER,
    ) -> BacktestResult:
        """
        运行回测
        
        Args:
            db: 数据库会话
            start: 起始时间
            end: 结束时间
            ticker: 代币符号
            
        Returns:
            回测结果
        """
        logger.info(f"开始回测: {start} 到 {end}")
        
        # 重置信号生成器
        self.signal_generator.reset()
        
        # 加载历史数据
        snapshots = (
            db.query(Snapshot)
            .filter(and_(
                Snapshot.ticker == ticker,
                Snapshot.ts >= start,
                Snapshot.ts <= end,
            ))
            .order_by(Snapshot.ts)
            .all()
        )
        
        logger.info(f"加载了 {len(snapshots)} 条快照数据")
        
        if not snapshots:
            return BacktestResult(
                data_start=start,
                data_end=end,
                params=self.params,
            )
        
        # 回测状态
        trades: List[Trade] = []
        current_trade: Optional[Trade] = None
        equity_curve: List[float] = [0.0]
        cumulative_pnl = 0.0
        
        # 遍历快照
        for snapshot in snapshots:
            if not snapshot.mid:
                continue
                
            current_price = float(snapshot.mid)
            current_time = snapshot.ts
            
            # 1. 检查是否有持仓需要平仓（TP/SL）
            if current_trade and current_trade.status == TradeStatus.OPEN:
                closed = self._check_exit(current_trade, current_price, current_time)
                if closed:
                    cumulative_pnl += current_trade.pnl_bps
                    equity_curve.append(cumulative_pnl)
                    trades.append(current_trade)
                    current_trade = None
            
            # 2. 检查过滤器
            if not self._check_filters(snapshot):
                continue
            
            # 3. 如无持仓，检测新信号
            if current_trade is None:
                signal = self.signal_generator.update(current_time, current_price)
                if signal:
                    current_trade = Trade(
                        entry_time=signal["ts"],
                        entry_price=signal["entry_price"],
                        side=signal["side"],
                        tp_price=signal["tp_price"],
                        sl_price=signal["sl_price"],
                        rationale=signal["rationale"],
                    )
                    logger.debug(f"新开仓: {current_trade.side.value} @ {current_trade.entry_price:.2f}")
            else:
                # 更新信号生成器（即使有持仓也要更新价格历史）
                self.signal_generator.update(current_time, current_price)
        
        # 处理未平仓交易
        if current_trade and current_trade.status == TradeStatus.OPEN:
            # 以最后价格强制平仓
            last_price = float(snapshots[-1].mid) if snapshots[-1].mid else current_trade.entry_price
            current_trade.exit_time = snapshots[-1].ts
            current_trade.exit_price = last_price
            current_trade.status = TradeStatus.EXPIRED
            current_trade.pnl_bps = self._calculate_pnl(current_trade, last_price)
            cumulative_pnl += current_trade.pnl_bps
            equity_curve.append(cumulative_pnl)
            trades.append(current_trade)
        
        # 计算绩效指标
        trade_results = [
            TradeResult(pnl_bps=t.pnl_bps, is_win=t.pnl_bps > 0)
            for t in trades
        ]
        metrics = calculate_metrics(trade_results)
        
        result = BacktestResult(
            data_start=start,
            data_end=end,
            params=self.params,
            trades=trades,
            metrics=metrics,
            equity_curve=equity_curve,
        )
        
        logger.info(f"回测完成: {len(trades)} 笔交易, 胜率 {metrics['win_rate']:.2%}")
        
        return result
    
    def _check_filters(self, snapshot: Snapshot) -> bool:
        """检查过滤器"""
        # 点差过滤
        if snapshot.spread_bps and float(snapshot.spread_bps) > self.spread_max_bps:
            return False
            
        # 报价新鲜度过滤
        if snapshot.quote_age_ms and snapshot.quote_age_ms > self.quote_age_max_ms:
            return False
            
        return True
    
    def _check_exit(self, trade: Trade, current_price: float, current_time: datetime) -> bool:
        """
        检查是否触发平仓
        
        Returns:
            是否已平仓
        """
        if trade.side == TradeSide.LONG:
            if current_price >= trade.tp_price:
                # 止盈
                trade.exit_time = current_time
                trade.exit_price = trade.tp_price
                trade.status = TradeStatus.TP_HIT
                trade.pnl_bps = self._calculate_pnl(trade, trade.tp_price)
                return True
            elif current_price <= trade.sl_price:
                # 止损
                trade.exit_time = current_time
                trade.exit_price = trade.sl_price
                trade.status = TradeStatus.SL_HIT
                trade.pnl_bps = self._calculate_pnl(trade, trade.sl_price)
                return True
        else:  # SHORT
            if current_price <= trade.tp_price:
                # 止盈
                trade.exit_time = current_time
                trade.exit_price = trade.tp_price
                trade.status = TradeStatus.TP_HIT
                trade.pnl_bps = self._calculate_pnl(trade, trade.tp_price)
                return True
            elif current_price >= trade.sl_price:
                # 止损
                trade.exit_time = current_time
                trade.exit_price = trade.sl_price
                trade.status = TradeStatus.SL_HIT
                trade.pnl_bps = self._calculate_pnl(trade, trade.sl_price)
                return True
                
        return False
    
    def _calculate_pnl(self, trade: Trade, exit_price: float) -> float:
        """计算盈亏 (bps)"""
        if trade.side == TradeSide.LONG:
            return (exit_price - trade.entry_price) / trade.entry_price * 10000
        else:  # SHORT
            return (trade.entry_price - exit_price) / trade.entry_price * 10000
    
    def save_result(
        self,
        db: Session,
        result: BacktestResult,
    ) -> BacktestRun:
        """
        保存回测结果到数据库
        
        Args:
            db: 数据库会话
            result: 回测结果
            
        Returns:
            数据库记录
        """
        run = BacktestRun(
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            params=json.dumps(result.params),
            data_start=result.data_start,
            data_end=result.data_end,
            total_signals=result.metrics.get("total_signals", 0),
            win_count=result.metrics.get("win_count", 0),
            loss_count=result.metrics.get("loss_count", 0),
            win_rate=result.metrics.get("win_rate", 0),
            avg_win_bps=result.metrics.get("avg_win_bps", 0),
            avg_loss_bps=result.metrics.get("avg_loss_bps", 0),
            total_pnl_bps=result.metrics.get("total_pnl_bps", 0),
            max_drawdown_bps=result.metrics.get("max_drawdown_bps", 0),
            sharpe_ratio=result.metrics.get("sharpe_ratio", 0),
            results_json=json.dumps(result.to_dict()),
        )
        
        db.add(run)
        db.commit()
        db.refresh(run)
        
        result.run_id = run.id
        
        logger.info(f"回测结果已保存, run_id={run.id}")
        
        return run
