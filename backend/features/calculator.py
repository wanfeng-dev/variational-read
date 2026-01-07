# -*- coding: utf-8 -*-
"""
特征计算器
整合滚动窗口和技术指标，计算完整特征集
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable, Awaitable, List
from decimal import Decimal

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import RSI_PERIOD, RANGE_WINDOW_MIN, TICKER
from features.rolling_window import RollingWindow
from features import indicators
from db.database import SessionLocal
from db.models import Feature, Snapshot

logger = logging.getLogger(__name__)


class FeatureCalculator:
    """
    特征计算器
    负责维护滚动窗口并计算技术特征
    """
    
    def __init__(self, ticker: str = TICKER):
        """
        初始化特征计算器
        
        Args:
            ticker: 交易标的，默认 ETH
        """
        self.ticker = ticker
        # 滚动窗口保持 20 分钟数据 + 缓冲
        self.window = RollingWindow(max_duration_sec=RANGE_WINDOW_MIN * 60 + 120)
        self._on_feature_callbacks: List[Callable[[dict], Awaitable[None]]] = []
        self._initialized = False
    
    def on_feature(self, callback: Callable[[dict], Awaitable[None]]):
        """注册特征计算完成回调"""
        self._on_feature_callbacks.append(callback)
    
    async def _notify_feature(self, feature_dict: dict):
        """通知所有回调"""
        for callback in self._on_feature_callbacks:
            try:
                await callback(feature_dict)
            except Exception as e:
                logger.error(f"特征回调执行失败: {e}")
    
    def warmup_from_db(self):
        """从数据库预热滚动窗口"""
        db = SessionLocal()
        try:
            # 获取最近 25 分钟的数据用于预热
            cutoff = datetime.utcnow() - timedelta(minutes=25)
            snapshots = (
                db.query(Snapshot)
                .filter(Snapshot.ticker == self.ticker)
                .filter(Snapshot.ts >= cutoff)
                .order_by(Snapshot.ts.asc())
                .all()
            )
            
            if snapshots:
                snapshot_dicts = [s.to_dict() for s in snapshots]
                self.window.warmup(snapshot_dicts)
                logger.info(f"特征计算器预热完成，加载 {len(snapshots)} 条快照")
            else:
                logger.info("没有历史数据可用于预热")
            
            self._initialized = True
            
        finally:
            db.close()
    
    async def compute(self, snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        计算特征
        
        Args:
            snapshot: 快照数据字典
            
        Returns:
            计算的特征字典，存储失败返回 None
        """
        # 添加到滚动窗口
        self.window.add(snapshot)
        
        # 获取当前数据
        latest = self.window.get_latest()
        if not latest or latest.mid is None:
            logger.warning("无法获取最新数据或 mid 为空")
            return None
        
        current_mid = latest.mid
        
        # 计算收益率
        mid_5s = self.window.get_mid_at_offset(5)
        mid_15s = self.window.get_mid_at_offset(15)
        mid_60s = self.window.get_mid_at_offset(60)
        
        return_5s = indicators.calc_return(current_mid, mid_5s)
        return_15s = indicators.calc_return(current_mid, mid_15s)
        return_60s = indicators.calc_return(current_mid, mid_60s)
        
        # 获取 60 秒窗口的 mid 数据
        mids_60s = self.window.get_mids_in_window(60)
        
        # 计算标准差
        std_60s = indicators.calc_std(mids_60s) if len(mids_60s) >= 2 else None
        
        # 计算 EMA 和 z-score
        ema_60s = indicators.calc_ema(mids_60s, min(len(mids_60s), 30)) if mids_60s else None
        z_score = None
        if ema_60s is not None and std_60s is not None and std_60s > 0:
            z_score = indicators.calc_z_score(current_mid, ema_60s, std_60s)
        
        # 计算 RSI（需要更多数据）
        # RSI 需要至少 period + 1 个数据点
        mids_for_rsi = self.window.get_mids_in_window(RANGE_WINDOW_MIN * 60)
        rsi_14 = indicators.calc_rsi(mids_for_rsi, RSI_PERIOD)
        
        # 计算 20 分钟区间高低点
        mids_20m = self.window.get_mids_in_window(RANGE_WINDOW_MIN * 60)
        range_high_20m = max(mids_20m) if mids_20m else None
        range_low_20m = min(mids_20m) if mids_20m else None
        
        # 计算多空比
        long_short_ratio = None
        if latest.long_oi and latest.short_oi and latest.short_oi > 0:
            long_short_ratio = latest.long_oi / latest.short_oi
        
        # 构建特征字典
        feature_data = {
            "ts": latest.ts,
            "ticker": self.ticker,
            "mid": current_mid,
            "return_5s": return_5s,
            "return_15s": return_15s,
            "return_60s": return_60s,
            "std_60s": std_60s,
            "rsi_14": rsi_14,
            "z_score": z_score,
            "range_high_20m": range_high_20m,
            "range_low_20m": range_low_20m,
            "spread_bps": latest.spread_bps,
            "impact_buy_bps": latest.impact_buy_bps,
            "impact_sell_bps": latest.impact_sell_bps,
            "quote_age_ms": latest.quote_age_ms,
            "long_short_ratio": long_short_ratio,
        }
        
        # 存储到数据库
        db = SessionLocal()
        try:
            feature = Feature(
                ts=feature_data["ts"],
                ticker=feature_data["ticker"],
                mid=self._to_decimal(feature_data["mid"]),
                return_5s=self._to_decimal(feature_data["return_5s"]),
                return_15s=self._to_decimal(feature_data["return_15s"]),
                return_60s=self._to_decimal(feature_data["return_60s"]),
                std_60s=self._to_decimal(feature_data["std_60s"]),
                rsi_14=self._to_decimal(feature_data["rsi_14"]),
                z_score=self._to_decimal(feature_data["z_score"]),
                range_high_20m=self._to_decimal(feature_data["range_high_20m"]),
                range_low_20m=self._to_decimal(feature_data["range_low_20m"]),
                spread_bps=self._to_decimal(feature_data["spread_bps"]),
                impact_buy_bps=self._to_decimal(feature_data["impact_buy_bps"]),
                impact_sell_bps=self._to_decimal(feature_data["impact_sell_bps"]),
                quote_age_ms=feature_data["quote_age_ms"],
                long_short_ratio=self._to_decimal(feature_data["long_short_ratio"]),
            )
            db.add(feature)
            db.commit()
            db.refresh(feature)
            
            result = feature.to_dict()
            logger.debug(f"特征计算完成: id={feature.id}, rsi={feature.rsi_14}")
            
            # 通知回调
            await self._notify_feature(result)
            
            return result
            
        except Exception as e:
            db.rollback()
            logger.error(f"特征存储失败: {e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def _to_decimal(value) -> Optional[Decimal]:
        """安全转换为 Decimal"""
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None
    
    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized
    
    @property
    def window_size(self) -> int:
        """获取当前窗口数据量"""
        return self.window.size
