# -*- coding: utf-8 -*-
"""
预警引擎
实现预警检测逻辑和信号状态跟踪（TP/SL命中检测）
"""
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Optional, Callable, List, Dict, Any
from decimal import Decimal

from sqlalchemy.orm import Session

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.models import Alert, Signal, Snapshot
from config import (
    SPREAD_MAX_BPS,
    QUOTE_AGE_MAX_MS,
    TICKER,
)

logger = logging.getLogger(__name__)


class AlertType(str, Enum):
    """预警类型枚举"""
    SIGNAL_NEW = "SIGNAL_NEW"           # 新信号生成
    SIGNAL_TP_HIT = "SIGNAL_TP_HIT"     # 信号触达止盈
    SIGNAL_SL_HIT = "SIGNAL_SL_HIT"     # 信号触达止损
    PRICE_SPIKE = "PRICE_SPIKE"         # 价格剧烈波动
    SPREAD_HIGH = "SPREAD_HIGH"         # 点差过大
    QUOTE_STALE = "QUOTE_STALE"         # 报价过旧
    DATA_ERROR = "DATA_ERROR"           # 数据采集异常


class AlertPriority(str, Enum):
    """预警优先级枚举"""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# 预警类型对应的优先级
ALERT_PRIORITY_MAP = {
    AlertType.SIGNAL_NEW: AlertPriority.HIGH,
    AlertType.SIGNAL_TP_HIT: AlertPriority.MEDIUM,
    AlertType.SIGNAL_SL_HIT: AlertPriority.MEDIUM,
    AlertType.PRICE_SPIKE: AlertPriority.HIGH,
    AlertType.SPREAD_HIGH: AlertPriority.MEDIUM,
    AlertType.QUOTE_STALE: AlertPriority.LOW,
    AlertType.DATA_ERROR: AlertPriority.HIGH,
}


class AlertEngine:
    """
    预警引擎
    负责检测各类预警条件并生成预警记录
    """
    
    def __init__(self):
        self._callbacks: List[Callable[[Alert], None]] = []
        self._last_price: Optional[Decimal] = None
        self._price_spike_threshold_bps: float = 50  # 1分钟涨跌幅阈值 (bps)
        
    def on_alert(self, callback: Callable[[Alert], None]):
        """注册预警回调"""
        self._callbacks.append(callback)
        
    async def _notify(self, alert: Alert):
        """通知所有回调"""
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(alert)
                else:
                    callback(alert)
            except Exception as e:
                logger.error(f"预警回调执行失败: {e}")
    
    def create_alert(
        self,
        db: Session,
        alert_type: AlertType,
        message: str,
        ticker: str = TICKER,
        data: Optional[Dict[str, Any]] = None,
        priority: Optional[AlertPriority] = None,
    ) -> Alert:
        """
        创建预警记录
        
        Args:
            db: 数据库会话
            alert_type: 预警类型
            message: 预警消息
            ticker: 代币符号
            data: 附加数据
            priority: 优先级（可选，默认根据类型自动设置）
            
        Returns:
            创建的预警记录
        """
        if priority is None:
            priority = ALERT_PRIORITY_MAP.get(alert_type, AlertPriority.MEDIUM)
            
        alert = Alert(
            ts=datetime.utcnow(),
            type=alert_type.value,
            priority=priority.value,
            ticker=ticker,
            message=message,
            data=json.dumps(data) if data else None,
            acknowledged=False,
        )
        
        db.add(alert)
        db.commit()
        db.refresh(alert)
        
        logger.info(f"预警生成: [{priority.value}] {alert_type.value} - {message}")
        
        return alert
    
    def check_signal_status(
        self,
        db: Session,
        current_price: Decimal,
        ticker: str = TICKER,
    ) -> List[Alert]:
        """
        检查信号状态（TP/SL命中）
        
        Args:
            db: 数据库会话
            current_price: 当前价格
            ticker: 代币符号
            
        Returns:
            生成的预警列表
        """
        alerts = []
        
        # 查询所有待处理的信号
        pending_signals = (
            db.query(Signal)
            .filter(Signal.ticker == ticker)
            .filter(Signal.status == "PENDING")
            .all()
        )
        
        for signal in pending_signals:
            entry_price = Decimal(str(signal.entry_price))
            tp_price = Decimal(str(signal.tp_price))
            sl_price = Decimal(str(signal.sl_price))
            
            hit_type = None
            pnl_bps = Decimal("0")
            
            if signal.side == "LONG":
                # 多头: 价格 >= TP 为止盈, 价格 <= SL 为止损
                if current_price >= tp_price:
                    hit_type = "TP_HIT"
                    pnl_bps = (tp_price - entry_price) / entry_price * 10000
                elif current_price <= sl_price:
                    hit_type = "SL_HIT"
                    pnl_bps = (sl_price - entry_price) / entry_price * 10000
            else:  # SHORT
                # 空头: 价格 <= TP 为止盈, 价格 >= SL 为止损
                if current_price <= tp_price:
                    hit_type = "TP_HIT"
                    pnl_bps = (entry_price - tp_price) / entry_price * 10000
                elif current_price >= sl_price:
                    hit_type = "SL_HIT"
                    pnl_bps = (entry_price - sl_price) / entry_price * 10000
            
            if hit_type:
                # 更新信号状态
                signal.status = hit_type
                signal.result_pnl_bps = pnl_bps
                signal.closed_at = datetime.utcnow()
                db.commit()
                
                # 创建预警
                alert_type = AlertType.SIGNAL_TP_HIT if hit_type == "TP_HIT" else AlertType.SIGNAL_SL_HIT
                message = (
                    f"信号 #{signal.id} {signal.side} {hit_type}: "
                    f"入场 {entry_price:.2f}, 当前 {current_price:.2f}, "
                    f"盈亏 {pnl_bps:.2f} bps"
                )
                
                alert = self.create_alert(
                    db=db,
                    alert_type=alert_type,
                    message=message,
                    ticker=ticker,
                    data={
                        "signal_id": signal.id,
                        "side": signal.side,
                        "entry_price": float(entry_price),
                        "exit_price": float(current_price),
                        "pnl_bps": float(pnl_bps),
                    },
                )
                alerts.append(alert)
                
        return alerts
    
    def check_price_spike(
        self,
        db: Session,
        current_price: Decimal,
        ticker: str = TICKER,
    ) -> Optional[Alert]:
        """
        检查价格剧烈波动
        
        Args:
            db: 数据库会话
            current_price: 当前价格
            ticker: 代币符号
            
        Returns:
            预警记录（如果触发）
        """
        if self._last_price is None:
            self._last_price = current_price
            return None
            
        change_bps = abs((current_price - self._last_price) / self._last_price * 10000)
        
        alert = None
        if change_bps >= self._price_spike_threshold_bps:
            direction = "上涨" if current_price > self._last_price else "下跌"
            message = (
                f"价格剧烈波动: {direction} {change_bps:.2f} bps, "
                f"从 {self._last_price:.2f} 到 {current_price:.2f}"
            )
            alert = self.create_alert(
                db=db,
                alert_type=AlertType.PRICE_SPIKE,
                message=message,
                ticker=ticker,
                data={
                    "prev_price": float(self._last_price),
                    "current_price": float(current_price),
                    "change_bps": float(change_bps),
                },
            )
            
        self._last_price = current_price
        return alert
    
    def check_spread(
        self,
        db: Session,
        spread_bps: Decimal,
        ticker: str = TICKER,
    ) -> Optional[Alert]:
        """
        检查点差是否过大
        
        Args:
            db: 数据库会话
            spread_bps: 当前点差 (bps)
            ticker: 代币符号
            
        Returns:
            预警记录（如果触发）
        """
        if spread_bps > SPREAD_MAX_BPS:
            message = f"点差过大: {spread_bps:.2f} bps (阈值: {SPREAD_MAX_BPS} bps)"
            return self.create_alert(
                db=db,
                alert_type=AlertType.SPREAD_HIGH,
                message=message,
                ticker=ticker,
                data={"spread_bps": float(spread_bps), "threshold": SPREAD_MAX_BPS},
            )
        return None
    
    def check_quote_age(
        self,
        db: Session,
        quote_age_ms: int,
        ticker: str = TICKER,
    ) -> Optional[Alert]:
        """
        检查报价是否过旧
        
        Args:
            db: 数据库会话
            quote_age_ms: 报价延迟 (ms)
            ticker: 代币符号
            
        Returns:
            预警记录（如果触发）
        """
        if quote_age_ms > QUOTE_AGE_MAX_MS:
            message = f"报价过旧: {quote_age_ms} ms (阈值: {QUOTE_AGE_MAX_MS} ms)"
            return self.create_alert(
                db=db,
                alert_type=AlertType.QUOTE_STALE,
                message=message,
                ticker=ticker,
                data={"quote_age_ms": quote_age_ms, "threshold": QUOTE_AGE_MAX_MS},
            )
        return None
    
    def create_signal_alert(
        self,
        db: Session,
        signal: Signal,
    ) -> Alert:
        """
        为新信号创建预警
        
        Args:
            db: 数据库会话
            signal: 信号对象
            
        Returns:
            预警记录
        """
        message = (
            f"新信号: {signal.side} ETH @ {signal.entry_price:.2f}, "
            f"TP: {signal.tp_price:.2f}, SL: {signal.sl_price:.2f}"
        )
        return self.create_alert(
            db=db,
            alert_type=AlertType.SIGNAL_NEW,
            message=message,
            ticker=signal.ticker,
            data=signal.to_dict(),
        )
    
    def create_data_error_alert(
        self,
        db: Session,
        error_message: str,
        ticker: str = TICKER,
    ) -> Alert:
        """
        创建数据采集异常预警
        
        Args:
            db: 数据库会话
            error_message: 错误信息
            ticker: 代币符号
            
        Returns:
            预警记录
        """
        return self.create_alert(
            db=db,
            alert_type=AlertType.DATA_ERROR,
            message=f"数据采集异常: {error_message}",
            ticker=ticker,
            data={"error": error_message},
        )
    
    async def process_snapshot(
        self,
        db: Session,
        snapshot: Snapshot,
    ) -> List[Alert]:
        """
        处理新快照，检查所有预警条件
        
        Args:
            db: 数据库会话
            snapshot: 快照数据
            
        Returns:
            生成的预警列表
        """
        alerts = []
        
        if snapshot.mid:
            current_price = Decimal(str(snapshot.mid))
            
            # 检查信号状态
            signal_alerts = self.check_signal_status(db, current_price, snapshot.ticker)
            alerts.extend(signal_alerts)
            
            # 检查价格波动
            spike_alert = self.check_price_spike(db, current_price, snapshot.ticker)
            if spike_alert:
                alerts.append(spike_alert)
        
        # 检查点差
        if snapshot.spread_bps:
            spread_alert = self.check_spread(
                db, Decimal(str(snapshot.spread_bps)), snapshot.ticker
            )
            if spread_alert:
                alerts.append(spread_alert)
        
        # 检查报价新鲜度
        if snapshot.quote_age_ms:
            quote_alert = self.check_quote_age(db, snapshot.quote_age_ms, snapshot.ticker)
            if quote_alert:
                alerts.append(quote_alert)
        
        # 通知回调
        for alert in alerts:
            await self._notify(alert)
        
        return alerts


# 需要导入 asyncio
import asyncio
