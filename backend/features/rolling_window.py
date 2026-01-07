# -*- coding: utf-8 -*-
"""
滚动窗口管理
基于 deque 的高效滚动窗口，支持按时间筛选数据
"""
import logging
from collections import deque
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from decimal import Decimal

logger = logging.getLogger(__name__)


class SnapshotData:
    """快照数据结构，用于滚动窗口存储"""
    
    __slots__ = ['ts', 'mid', 'bid_1k', 'ask_1k', 'spread_bps', 
                 'impact_buy_bps', 'impact_sell_bps', 'quote_age_ms',
                 'long_oi', 'short_oi']
    
    def __init__(self, data: Dict[str, Any]):
        self.ts: datetime = data.get('ts') or datetime.utcnow()
        if isinstance(self.ts, str):
            self.ts = datetime.fromisoformat(self.ts.replace('Z', '+00:00'))
        
        self.mid: Optional[float] = self._to_float(data.get('mid'))
        self.bid_1k: Optional[float] = self._to_float(data.get('bid_1k'))
        self.ask_1k: Optional[float] = self._to_float(data.get('ask_1k'))
        self.spread_bps: Optional[float] = self._to_float(data.get('spread_bps'))
        self.impact_buy_bps: Optional[float] = self._to_float(data.get('impact_buy_bps'))
        self.impact_sell_bps: Optional[float] = self._to_float(data.get('impact_sell_bps'))
        self.quote_age_ms: Optional[int] = data.get('quote_age_ms')
        self.long_oi: Optional[float] = self._to_float(data.get('long_oi'))
        self.short_oi: Optional[float] = self._to_float(data.get('short_oi'))
    
    @staticmethod
    def _to_float(value) -> Optional[float]:
        """安全转换为 float"""
        if value is None:
            return None
        try:
            if isinstance(value, Decimal):
                return float(value)
            return float(value)
        except (ValueError, TypeError):
            return None


class RollingWindow:
    """
    滚动窗口类
    维护固定时间长度的数据窗口，支持高效的时间范围查询
    """
    
    def __init__(self, max_duration_sec: int = 1200):
        """
        初始化滚动窗口
        
        Args:
            max_duration_sec: 窗口最大持续时间（秒），默认 20 分钟
        """
        self.max_duration_sec = max_duration_sec
        self._data: deque[SnapshotData] = deque()
        self._last_clean_time: Optional[datetime] = None
    
    def add(self, snapshot: Dict[str, Any]):
        """
        添加新的快照数据
        
        Args:
            snapshot: 快照数据字典
        """
        data = SnapshotData(snapshot)
        self._data.append(data)
        
        # 定期清理过期数据
        now = data.ts
        if self._last_clean_time is None or (now - self._last_clean_time).total_seconds() > 10:
            self._clean_expired(now)
            self._last_clean_time = now
    
    def _clean_expired(self, now: datetime):
        """清理过期数据"""
        cutoff = now - timedelta(seconds=self.max_duration_sec)
        while self._data and self._data[0].ts < cutoff:
            self._data.popleft()
    
    def get_data_in_window(self, seconds: int) -> List[SnapshotData]:
        """
        获取指定时间窗口内的数据
        
        Args:
            seconds: 时间窗口大小（秒）
            
        Returns:
            时间窗口内的快照数据列表
        """
        if not self._data:
            return []
        
        now = self._data[-1].ts
        cutoff = now - timedelta(seconds=seconds)
        
        result = []
        for item in reversed(self._data):
            if item.ts >= cutoff:
                result.append(item)
            else:
                break
        
        return list(reversed(result))
    
    def get_mids_in_window(self, seconds: int) -> List[float]:
        """获取指定时间窗口内的 mid 价格列表"""
        data = self.get_data_in_window(seconds)
        return [d.mid for d in data if d.mid is not None]
    
    def get_mid_at_offset(self, seconds: int) -> Optional[float]:
        """
        获取指定秒数之前的 mid 价格
        
        Args:
            seconds: 偏移秒数
            
        Returns:
            对应时间点的 mid 价格，如果没有数据返回 None
        """
        if not self._data:
            return None
        
        now = self._data[-1].ts
        target = now - timedelta(seconds=seconds)
        
        # 找到最接近 target 的数据点
        closest = None
        min_diff = float('inf')
        
        for item in reversed(self._data):
            diff = abs((item.ts - target).total_seconds())
            if diff < min_diff:
                min_diff = diff
                closest = item
            # 如果已经过了目标时间太多，停止搜索
            if item.ts < target - timedelta(seconds=5):
                break
        
        # 允许 3 秒的误差
        if closest and min_diff <= 3:
            return closest.mid
        return None
    
    def get_latest(self) -> Optional[SnapshotData]:
        """获取最新的快照数据"""
        return self._data[-1] if self._data else None
    
    @property
    def size(self) -> int:
        """返回当前窗口中的数据数量"""
        return len(self._data)
    
    def warmup(self, snapshots: List[Dict[str, Any]]):
        """
        从历史数据预热窗口
        
        Args:
            snapshots: 历史快照数据列表（按时间升序排列）
        """
        logger.info(f"预热滚动窗口，数据量: {len(snapshots)}")
        for snapshot in snapshots:
            data = SnapshotData(snapshot)
            self._data.append(data)
        
        # 清理过期数据
        if self._data:
            self._clean_expired(self._data[-1].ts)
        
        logger.info(f"预热完成，窗口数据量: {len(self._data)}")
