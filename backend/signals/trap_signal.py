# -*- coding: utf-8 -*-
"""
假突破回收信号检测器
实现区间计算、突破检测、回收检测和 TP/SL 计算
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    RANGE_WINDOW_MIN,
    BREAKOUT_THRESHOLD_BPS,
    RECLAIM_TIMEOUT_SEC,
    SL_BUFFER_BPS,
    RR_RATIO,
)

logger = logging.getLogger(__name__)


class SignalSide(str, Enum):
    """信号方向"""
    LONG = "LONG"
    SHORT = "SHORT"


class BreakoutDirection(str, Enum):
    """突破方向"""
    UP = "UP"
    DOWN = "DOWN"


@dataclass
class BreakoutState:
    """突破状态记录"""
    direction: BreakoutDirection
    breakout_time: datetime
    breakout_price: float      # 突破时的价格
    extreme_price: float       # 突破后的极值价格
    range_high: float          # 区间高点
    range_low: float           # 区间低点
    
    def update_extreme(self, price: float):
        """更新极值价格"""
        if self.direction == BreakoutDirection.UP:
            self.extreme_price = max(self.extreme_price, price)
        else:
            self.extreme_price = min(self.extreme_price, price)


@dataclass
class SignalCandidate:
    """信号候选"""
    side: SignalSide
    entry_price: float
    tp_price: float
    sl_price: float
    breakout_price: float
    reclaim_price: float
    range_high: float
    range_low: float
    confidence: float
    rationale: str


class TrapSignalDetector:
    """
    假突破回收信号检测器
    
    逻辑流程:
    1. 维护 N 分钟区间的高低点
    2. 检测价格突破区间
    3. 检测突破后是否回收
    4. 生成反向信号并计算 TP/SL
    """
    
    def __init__(
        self,
        range_window_min: int = RANGE_WINDOW_MIN,
        breakout_threshold_bps: float = BREAKOUT_THRESHOLD_BPS,
        reclaim_timeout_sec: int = RECLAIM_TIMEOUT_SEC,
        sl_buffer_bps: float = SL_BUFFER_BPS,
        rr_ratio: float = RR_RATIO,
    ):
        """
        初始化检测器
        
        Args:
            range_window_min: 区间窗口大小（分钟）
            breakout_threshold_bps: 突破阈值（bps）
            reclaim_timeout_sec: 回收超时时间（秒）
            sl_buffer_bps: 止损缓冲（bps）
            rr_ratio: 盈亏比
        """
        self.range_window_min = range_window_min
        self.breakout_threshold_bps = breakout_threshold_bps
        self.reclaim_timeout_sec = reclaim_timeout_sec
        self.sl_buffer_bps = sl_buffer_bps
        self.rr_ratio = rr_ratio
        
        # 当前突破状态
        self._breakout_state: Optional[BreakoutState] = None
        
        # RSI 历史记录（用于 RSI 确认）
        self._rsi_history: List[Dict[str, Any]] = []
        self._max_rsi_history = 60  # 保留最近 60 个 RSI 数据点
    
    def detect(self, feature: Dict[str, Any]) -> Optional[SignalCandidate]:
        """
        检测信号
        
        Args:
            feature: 特征数据字典，包含 mid, range_high_20m, range_low_20m, rsi_14 等
            
        Returns:
            信号候选，如果没有信号返回 None
        """
        mid = feature.get("mid")
        range_high = feature.get("range_high_20m")
        range_low = feature.get("range_low_20m")
        ts = feature.get("ts")
        rsi = feature.get("rsi_14")
        
        # 数据完整性检查
        if any(v is None for v in [mid, range_high, range_low]):
            return None
        
        # 解析时间戳
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace('Z', '+00:00').replace('+00:00', ''))
        elif ts is None:
            ts = datetime.utcnow()
        
        # 记录 RSI 历史
        if rsi is not None:
            self._record_rsi(ts, rsi)
        
        # 计算阈值
        threshold = mid * self.breakout_threshold_bps / 10000
        
        # 检查是否存在活跃的突破状态
        if self._breakout_state:
            return self._check_reclaim(mid, ts, feature)
        else:
            return self._check_breakout(mid, ts, range_high, range_low, threshold, feature)
    
    def _check_breakout(
        self,
        mid: float,
        ts: datetime,
        range_high: float,
        range_low: float,
        threshold: float,
        feature: Dict[str, Any],
    ) -> Optional[SignalCandidate]:
        """检测突破"""
        # 向上突破
        if mid > range_high + threshold:
            logger.info(f"检测到向上突破: mid={mid:.2f} > range_high={range_high:.2f} + {threshold:.4f}")
            self._breakout_state = BreakoutState(
                direction=BreakoutDirection.UP,
                breakout_time=ts,
                breakout_price=mid,
                extreme_price=mid,
                range_high=range_high,
                range_low=range_low,
            )
            return None
        
        # 向下突破
        if mid < range_low - threshold:
            logger.info(f"检测到向下突破: mid={mid:.2f} < range_low={range_low:.2f} - {threshold:.4f}")
            self._breakout_state = BreakoutState(
                direction=BreakoutDirection.DOWN,
                breakout_time=ts,
                breakout_price=mid,
                extreme_price=mid,
                range_high=range_high,
                range_low=range_low,
            )
            return None
        
        return None
    
    def _check_reclaim(
        self,
        mid: float,
        ts: datetime,
        feature: Dict[str, Any],
    ) -> Optional[SignalCandidate]:
        """检测回收"""
        state = self._breakout_state
        
        # 更新极值
        state.update_extreme(mid)
        
        # 检查超时
        elapsed = (ts - state.breakout_time).total_seconds()
        if elapsed > self.reclaim_timeout_sec:
            logger.debug(f"突破超时未回收，重置状态: elapsed={elapsed:.1f}s")
            self._breakout_state = None
            return None
        
        signal = None
        
        # 向上突破后回收
        if state.direction == BreakoutDirection.UP:
            if mid < state.range_high:
                logger.info(f"检测到向上突破后回收: mid={mid:.2f} < range_high={state.range_high:.2f}")
                signal = self._generate_signal(
                    side=SignalSide.SHORT,
                    entry_price=mid,
                    breakout_price=state.extreme_price,
                    range_high=state.range_high,
                    range_low=state.range_low,
                    feature=feature,
                )
                self._breakout_state = None
        
        # 向下突破后回收
        elif state.direction == BreakoutDirection.DOWN:
            if mid > state.range_low:
                logger.info(f"检测到向下突破后回收: mid={mid:.2f} > range_low={state.range_low:.2f}")
                signal = self._generate_signal(
                    side=SignalSide.LONG,
                    entry_price=mid,
                    breakout_price=state.extreme_price,
                    range_high=state.range_high,
                    range_low=state.range_low,
                    feature=feature,
                )
                self._breakout_state = None
        
        return signal
    
    def _generate_signal(
        self,
        side: SignalSide,
        entry_price: float,
        breakout_price: float,
        range_high: float,
        range_low: float,
        feature: Dict[str, Any],
    ) -> SignalCandidate:
        """生成信号并计算 TP/SL"""
        sl_buffer = entry_price * self.sl_buffer_bps / 10000
        
        if side == SignalSide.SHORT:
            # 做空：SL 在突破高点上方，TP 向下
            sl_price = breakout_price + sl_buffer
            risk = sl_price - entry_price
            tp_price = entry_price - risk * self.rr_ratio
            rationale = f"假突破回收: 突破{self.range_window_min}分钟高点{range_high:.2f}后回收至{entry_price:.2f}"
        else:
            # 做多：SL 在突破低点下方，TP 向上
            sl_price = breakout_price - sl_buffer
            risk = entry_price - sl_price
            tp_price = entry_price + risk * self.rr_ratio
            rationale = f"假突破回收: 跌破{self.range_window_min}分钟低点{range_low:.2f}后回收至{entry_price:.2f}"
        
        # 添加 RSI 信息
        rsi = feature.get("rsi_14")
        if rsi is not None:
            rationale += f", RSI={rsi:.1f}"
        
        # 计算置信度（基于回收速度和 RSI 状态）
        confidence = self._calculate_confidence(side, feature)
        
        return SignalCandidate(
            side=side,
            entry_price=entry_price,
            tp_price=tp_price,
            sl_price=sl_price,
            breakout_price=breakout_price,
            reclaim_price=entry_price,
            range_high=range_high,
            range_low=range_low,
            confidence=confidence,
            rationale=rationale,
        )
    
    def _calculate_confidence(self, side: SignalSide, feature: Dict[str, Any]) -> float:
        """计算信号置信度"""
        confidence = 0.5  # 基础置信度
        
        rsi = feature.get("rsi_14")
        if rsi is not None:
            # RSI 在极值区域增加置信度
            if side == SignalSide.SHORT and rsi > 70:
                confidence += 0.2
            elif side == SignalSide.LONG and rsi < 30:
                confidence += 0.2
        
        # 多空比因素
        ls_ratio = feature.get("long_short_ratio")
        if ls_ratio is not None:
            if side == SignalSide.SHORT and ls_ratio > 1.2:
                confidence += 0.1  # 多头过度拥挤，做空置信度更高
            elif side == SignalSide.LONG and ls_ratio < 0.8:
                confidence += 0.1  # 空头过度拥挤，做多置信度更高
        
        return min(confidence, 1.0)
    
    def _record_rsi(self, ts: datetime, rsi: float):
        """记录 RSI 历史"""
        self._rsi_history.append({"ts": ts, "rsi": rsi})
        
        # 保持历史记录在限制范围内
        if len(self._rsi_history) > self._max_rsi_history:
            self._rsi_history = self._rsi_history[-self._max_rsi_history:]
    
    def get_recent_rsi_extreme(self, lookback_sec: int = 120) -> Optional[Dict[str, float]]:
        """
        获取近期 RSI 极值
        
        Args:
            lookback_sec: 回顾秒数
            
        Returns:
            包含 max_rsi 和 min_rsi 的字典
        """
        if not self._rsi_history:
            return None
        
        now = self._rsi_history[-1]["ts"]
        cutoff = now - timedelta(seconds=lookback_sec)
        
        recent = [h["rsi"] for h in self._rsi_history if h["ts"] >= cutoff]
        if not recent:
            return None
        
        return {
            "max_rsi": max(recent),
            "min_rsi": min(recent),
        }
    
    def reset(self):
        """重置检测器状态"""
        self._breakout_state = None
        self._rsi_history.clear()
    
    @property
    def has_active_breakout(self) -> bool:
        """是否有活跃的突破状态"""
        return self._breakout_state is not None
    
    @property
    def current_breakout_direction(self) -> Optional[BreakoutDirection]:
        """当前突破方向"""
        if self._breakout_state:
            return self._breakout_state.direction
        return None
