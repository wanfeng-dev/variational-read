# -*- coding: utf-8 -*-
"""
Bybit API 客户端
获取 BTC/ETH 永续合约市场数据
"""
import httpx
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    BYBIT_API_BASE,
    BYBIT_CATEGORY,
    BYBIT_SYMBOLS,
    BYBIT_TIMEOUT_SEC,
)
from collector.base_client import DataSourceClient

logger = logging.getLogger(__name__)


class BybitClient(DataSourceClient):
    """Bybit API 客户端"""
    
    def __init__(self, base_url: str = BYBIT_API_BASE):
        self.base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def source_name(self) -> str:
        return "bybit"
    
    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(BYBIT_TIMEOUT_SEC),
                headers={"Accept": "application/json"}
            )
        return self._client
    
    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    async def fetch_stats(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        获取市场统计数据
        
        API: GET /v5/market/tickers?category=linear&symbol=BTCUSDT
        """
        try:
            symbol = BYBIT_SYMBOLS.get(ticker)
            if not symbol:
                logger.error(f"不支持的 ticker: {ticker}")
                return None
            
            client = await self._get_client()
            response = await client.get(
                "/v5/market/tickers",
                params={"category": BYBIT_CATEGORY, "symbol": symbol}
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("retCode") != 0:
                logger.error(f"Bybit API 错误: {data.get('retMsg')}")
                return None
            
            result = data.get("result", {})
            ticker_list = result.get("list", [])
            
            if not ticker_list:
                logger.warning(f"未找到 {symbol} 的数据")
                return None
            
            ticker_data = ticker_list[0]
            return self._parse_and_compute(ticker_data, ticker)
            
        except Exception as e:
            logger.error(f"Bybit 获取数据失败: {e}")
            return None
    
    def _parse_and_compute(self, data: Dict, ticker: str) -> Dict[str, Any]:
        """
        解析原始数据并计算派生字段
        
        Bybit 字段映射:
        - lastPrice -> mark_price
        - bid1Price -> bid_1k (近似)
        - ask1Price -> ask_1k (近似)
        - fundingRate -> funding_rate
        - openInterest -> long_oi (总持仓，无法区分多空)
        - volume24h -> volume_24h
        """
        now = datetime.now(timezone.utc)
        
        # 基础价格
        last_price = self._to_decimal(data.get("lastPrice"))
        bid_price = self._to_decimal(data.get("bid1Price"))
        ask_price = self._to_decimal(data.get("ask1Price"))
        
        # 计算派生字段
        mid = None
        spread_bps = None
        
        if bid_price and ask_price:
            mid = (bid_price + ask_price) / 2
            if mid > 0:
                spread_bps = (ask_price - bid_price) / mid * Decimal("10000")
        
        # 持仓量 (Bybit 只提供总持仓，无法区分多空)
        open_interest = self._to_decimal(data.get("openInterest"))
        
        return {
            "ts": now,
            "source": self.source_name,
            "ticker": ticker,
            "mark_price": self._to_decimal(data.get("markPrice")) or last_price,
            "bid_1k": bid_price,
            "ask_1k": ask_price,
            "bid_100k": None,  # Bybit tickers 不提供深度
            "ask_100k": None,
            "mid": mid,
            "spread_bps": spread_bps,
            "impact_buy_bps": None,  # 需要 orderbook 接口
            "impact_sell_bps": None,
            "quote_age_ms": 0,  # Bybit 实时数据
            "funding_rate": self._to_decimal(data.get("fundingRate")),
            "long_oi": open_interest,  # 总持仓
            "short_oi": None,
            "volume_24h": self._to_decimal(data.get("volume24h")),
            "quotes_updated_at": now,
            "raw_json": None,  # 可选存储
        }

    async def fetch_klines(
        self,
        ticker: str,
        interval: str = "1",
        limit: int = 200,
    ) -> list:
        """
        获取 K 线数据
        
        API: GET /v5/market/kline?category=linear&symbol=BTCUSDT&interval=1&limit=200
        
        Args:
            ticker: 代币符号 (BTC / ETH)
            interval: K线周期 (1/3/5/15/30/60/120/240/360/720/D/W/M)
            limit: 返回数量，最大 1000
            
        Returns:
            K线数据列表 [{time, open, high, low, close, volume}, ...]
        """
        try:
            symbol = BYBIT_SYMBOLS.get(ticker)
            if not symbol:
                logger.error(f"不支持的 ticker: {ticker}")
                return []
            
            client = await self._get_client()
            response = await client.get(
                "/v5/market/kline",
                params={
                    "category": BYBIT_CATEGORY,
                    "symbol": symbol,
                    "interval": interval,
                    "limit": min(limit, 1000),
                }
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("retCode") != 0:
                logger.error(f"Bybit K线 API 错误: {data.get('retMsg')}")
                return []
            
            result = data.get("result", {})
            kline_list = result.get("list", [])
            
            # Bybit 返回格式: [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
            # 转换为标准格式，并按时间升序排列
            klines = []
            for item in reversed(kline_list):  # Bybit 返回降序，需要反转
                klines.append({
                    "time": int(item[0]),  # 时间戳 (ms)
                    "open": float(item[1]),
                    "high": float(item[2]),
                    "low": float(item[3]),
                    "close": float(item[4]),
                    "volume": float(item[5]),
                })
            
            return klines
            
        except Exception as e:
            logger.error(f"Bybit 获取K线失败: {e}")
            return []
