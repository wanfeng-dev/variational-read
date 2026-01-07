# -*- coding: utf-8 -*-
"""
数据源抽象基类
所有数据源客户端必须继承此类
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from decimal import Decimal


class DataSourceClient(ABC):
    """数据源客户端抽象基类"""
    
    @property
    @abstractmethod
    def source_name(self) -> str:
        """数据源名称"""
        pass
    
    @abstractmethod
    async def fetch_stats(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        获取市场统计数据
        
        Args:
            ticker: 代币符号 (BTC / ETH)
            
        Returns:
            标准化的快照数据字典，失败返回 None
            必须包含以下字段：
            {
                "ts": datetime,
                "source": str,
                "ticker": str,
                "mark_price": Decimal,
                "bid_1k": Decimal,
                "ask_1k": Decimal,
                "mid": Decimal,
                "spread_bps": Decimal,
                "funding_rate": Decimal,
                "long_oi": Decimal,
                "short_oi": Decimal,
                "volume_24h": Decimal,
                "quote_age_ms": int,
                ...
            }
        """
        pass
    
    @abstractmethod
    async def close(self):
        """关闭客户端连接"""
        pass
    
    @staticmethod
    def _to_decimal(value) -> Optional[Decimal]:
        """安全转换为 Decimal"""
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None
