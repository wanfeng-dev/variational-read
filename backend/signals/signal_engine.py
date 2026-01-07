# -*- coding: utf-8 -*-
"""
信号引擎
整合信号检测、过滤和状态管理
"""
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List, Callable, Awaitable

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TICKER
from db.database import SessionLocal
from db.models import Signal, Feature
from signals.trap_signal import TrapSignalDetector, SignalCandidate, SignalSide
from signals.filters import (
    FilterChain,
    SpreadFilter,
    QuoteAgeFilter,
    ImpactFilter,
    VolatilityFilter,
    RSIFilter,
)

logger = logging.getLogger(__name__)


class SignalEngine:
    """
    信号引擎
    
    职责：
    1. 整合信号检测器和过滤器
    2. 管理信号生命周期（生成、存储、状态更新）
    3. 跟踪活跃信号的 TP/SL 状态
    4. 提供信号回调通知
    """
    
    def __init__(self, ticker: str = TICKER):
        """
        初始化信号引擎
        
        Args:
            ticker: 交易标的
        """
        self.ticker = ticker
        
        # 信号检测器
        self._detector = TrapSignalDetector()
        
        # 过滤器链
        self._filter_chain = self._create_filter_chain()
        
        # 活跃信号（用于状态跟踪）
        self._active_signals: Dict[int, Dict[str, Any]] = {}
        
        # 回调
        self._on_signal_callbacks: List[Callable[[dict], Awaitable[None]]] = []
        self._on_signal_close_callbacks: List[Callable[[dict], Awaitable[None]]] = []
    
    def _create_filter_chain(self) -> FilterChain:
        """创建过滤器链"""
        chain = FilterChain()
        
        # 添加过滤器
        chain.add(SpreadFilter())
        chain.add(QuoteAgeFilter())
        chain.add(ImpactFilter())
        chain.add(VolatilityFilter())
        
        # RSI 过滤器需要连接到检测器的 RSI 历史
        rsi_filter = RSIFilter()
        rsi_filter.set_rsi_history_getter(self._detector.get_recent_rsi_extreme)
        chain.add(rsi_filter)
        
        return chain
    
    def on_signal(self, callback: Callable[[dict], Awaitable[None]]):
        """注册新信号回调"""
        self._on_signal_callbacks.append(callback)
    
    def on_signal_close(self, callback: Callable[[dict], Awaitable[None]]):
        """注册信号关闭回调"""
        self._on_signal_close_callbacks.append(callback)
    
    async def _notify_signal(self, signal_dict: dict):
        """通知新信号"""
        for callback in self._on_signal_callbacks:
            try:
                await callback(signal_dict)
            except Exception as e:
                logger.error(f"信号回调执行失败: {e}")
    
    async def _notify_signal_close(self, signal_dict: dict):
        """通知信号关闭"""
        for callback in self._on_signal_close_callbacks:
            try:
                await callback(signal_dict)
            except Exception as e:
                logger.error(f"信号关闭回调执行失败: {e}")
    
    async def process(self, feature: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        处理新特征数据
        
        Args:
            feature: 特征数据字典
            
        Returns:
            如果生成了新信号，返回信号字典；否则返回 None
        """
        # 1. 检查活跃信号的 TP/SL 状态
        await self._check_active_signals(feature)
        
        # 2. 检测新信号
        candidate = self._detector.detect(feature)
        if not candidate:
            return None
        
        # 3. 应用过滤器
        passed, filter_results = self._filter_chain.check_all(candidate, feature)
        
        if not passed:
            failed_filters = self._filter_chain.get_failed_filters(filter_results)
            logger.info(f"信号未通过过滤器: {failed_filters}")
            return None
        
        # 4. 保存信号到数据库
        passed_filters = self._filter_chain.get_passed_filters(filter_results)
        signal_dict = await self._save_signal(candidate, passed_filters)
        
        if signal_dict:
            # 添加到活跃信号跟踪
            self._active_signals[signal_dict["id"]] = signal_dict
            
            # 通知回调
            await self._notify_signal(signal_dict)
            
            logger.info(
                f"生成新信号: id={signal_dict['id']}, "
                f"side={signal_dict['side']}, "
                f"entry={signal_dict['entry_price']:.2f}, "
                f"tp={signal_dict['tp_price']:.2f}, "
                f"sl={signal_dict['sl_price']:.2f}"
            )
        
        return signal_dict
    
    async def _check_active_signals(self, feature: Dict[str, Any]):
        """检查活跃信号的 TP/SL 状态"""
        if not self._active_signals:
            return
        
        mid = feature.get("mid")
        if mid is None:
            return
        
        ts = feature.get("ts")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace('Z', '+00:00').replace('+00:00', ''))
        elif ts is None:
            ts = datetime.utcnow()
        
        signals_to_close = []
        
        for signal_id, signal in list(self._active_signals.items()):
            entry_price = signal["entry_price"]
            tp_price = signal["tp_price"]
            sl_price = signal["sl_price"]
            side = signal["side"]
            
            status = None
            pnl_bps = None
            
            if side == "LONG":
                # 做多：价格涨到 TP 或跌到 SL
                if mid >= tp_price:
                    status = "TP_HIT"
                    pnl_bps = (mid - entry_price) / entry_price * 10000
                elif mid <= sl_price:
                    status = "SL_HIT"
                    pnl_bps = (mid - entry_price) / entry_price * 10000
            else:  # SHORT
                # 做空：价格跌到 TP 或涨到 SL
                if mid <= tp_price:
                    status = "TP_HIT"
                    pnl_bps = (entry_price - mid) / entry_price * 10000
                elif mid >= sl_price:
                    status = "SL_HIT"
                    pnl_bps = (entry_price - mid) / entry_price * 10000
            
            if status:
                signals_to_close.append({
                    "id": signal_id,
                    "status": status,
                    "pnl_bps": pnl_bps,
                    "closed_at": ts,
                    "close_price": mid,
                })
        
        # 更新并关闭信号
        for close_info in signals_to_close:
            await self._close_signal(close_info)
    
    async def _close_signal(self, close_info: Dict[str, Any]):
        """关闭信号"""
        signal_id = close_info["id"]
        
        db = SessionLocal()
        try:
            signal = db.query(Signal).filter(Signal.id == signal_id).first()
            if signal and signal.status == "PENDING":
                signal.status = close_info["status"]
                signal.result_pnl_bps = Decimal(str(close_info["pnl_bps"]))
                signal.closed_at = close_info["closed_at"]
                db.commit()
                
                signal_dict = signal.to_dict()
                signal_dict["close_price"] = close_info["close_price"]
                
                # 从活跃信号中移除
                self._active_signals.pop(signal_id, None)
                
                # 通知回调
                await self._notify_signal_close(signal_dict)
                
                logger.info(
                    f"信号关闭: id={signal_id}, "
                    f"status={close_info['status']}, "
                    f"pnl={close_info['pnl_bps']:.2f} bps"
                )
                
        except Exception as e:
            db.rollback()
            logger.error(f"关闭信号失败: {e}")
        finally:
            db.close()
    
    async def _save_signal(
        self,
        candidate: SignalCandidate,
        passed_filters: List[str],
    ) -> Optional[Dict[str, Any]]:
        """保存信号到数据库"""
        db = SessionLocal()
        try:
            signal = Signal(
                ts=datetime.utcnow(),
                ticker=self.ticker,
                side=candidate.side.value,
                entry_price=Decimal(str(candidate.entry_price)),
                tp_price=Decimal(str(candidate.tp_price)),
                sl_price=Decimal(str(candidate.sl_price)),
                confidence=Decimal(str(candidate.confidence)),
                rationale=candidate.rationale,
                filters_passed=json.dumps(passed_filters),
                breakout_price=Decimal(str(candidate.breakout_price)),
                reclaim_price=Decimal(str(candidate.reclaim_price)),
                status="PENDING",
            )
            
            db.add(signal)
            db.commit()
            db.refresh(signal)
            
            return signal.to_dict()
            
        except Exception as e:
            db.rollback()
            logger.error(f"保存信号失败: {e}")
            return None
        finally:
            db.close()
    
    def load_active_signals(self):
        """从数据库加载活跃信号"""
        db = SessionLocal()
        try:
            signals = (
                db.query(Signal)
                .filter(Signal.ticker == self.ticker)
                .filter(Signal.status == "PENDING")
                .all()
            )
            
            for signal in signals:
                self._active_signals[signal.id] = signal.to_dict()
            
            logger.info(f"加载了 {len(signals)} 个活跃信号")
            
        finally:
            db.close()
    
    def reset(self):
        """重置引擎状态"""
        self._detector.reset()
        self._active_signals.clear()
    
    @property
    def has_active_breakout(self) -> bool:
        """是否有活跃的突破状态"""
        return self._detector.has_active_breakout
    
    @property
    def active_signal_count(self) -> int:
        """活跃信号数量"""
        return len(self._active_signals)
    
    @property
    def active_signals(self) -> List[Dict[str, Any]]:
        """获取活跃信号列表"""
        return list(self._active_signals.values())
    
    def get_stats(self, db_session=None) -> Dict[str, Any]:
        """
        获取引擎统计信息
        
        Args:
            db_session: 可选的数据库会话
            
        Returns:
            统计信息字典
        """
        should_close = False
        if db_session is None:
            db_session = SessionLocal()
            should_close = True
        
        try:
            from sqlalchemy import func
            
            # 总信号数
            total = db_session.query(Signal).filter(Signal.ticker == self.ticker).count()
            
            # 各状态数量
            pending = db_session.query(Signal).filter(
                Signal.ticker == self.ticker,
                Signal.status == "PENDING"
            ).count()
            
            tp_hit = db_session.query(Signal).filter(
                Signal.ticker == self.ticker,
                Signal.status == "TP_HIT"
            ).count()
            
            sl_hit = db_session.query(Signal).filter(
                Signal.ticker == self.ticker,
                Signal.status == "SL_HIT"
            ).count()
            
            # 胜率
            closed = tp_hit + sl_hit
            win_rate = tp_hit / closed if closed > 0 else 0
            
            # 平均盈亏
            avg_pnl = db_session.query(func.avg(Signal.result_pnl_bps)).filter(
                Signal.ticker == self.ticker,
                Signal.result_pnl_bps.isnot(None)
            ).scalar() or 0
            
            return {
                "total_signals": total,
                "pending": pending,
                "tp_hit": tp_hit,
                "sl_hit": sl_hit,
                "win_rate": win_rate,
                "avg_pnl_bps": float(avg_pnl),
                "active_breakout": self.has_active_breakout,
            }
            
        finally:
            if should_close:
                db_session.close()
