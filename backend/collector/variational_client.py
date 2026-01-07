# -*- coding: utf-8 -*-
"""
Variational API 客户端
实现数据采集、派生字段计算、限流控制与异常重试
"""
import httpx
import asyncio
import logging
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any, List
from collections import deque
import time

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    VARIATIONAL_API_BASE,
    MAX_RETRIES,
    RETRY_DELAY_SEC,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SEC,
    TICKER,
)
from collector.base_client import DataSourceClient

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    滑动窗口限流器
    限制在指定时间窗口内的请求数量
    """
    
    def __init__(self, max_requests: int = RATE_LIMIT_REQUESTS, 
                 window_sec: float = RATE_LIMIT_WINDOW_SEC):
        self.max_requests = max_requests
        self.window_sec = window_sec
        self.request_times: deque = deque()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> float:
        """
        获取请求许可
        返回需要等待的秒数（0 表示可以立即执行）
        """
        async with self._lock:
            now = time.time()
            
            # 清理过期的请求记录
            while self.request_times and self.request_times[0] < now - self.window_sec:
                self.request_times.popleft()
            
            # 检查是否超过限制
            if len(self.request_times) >= self.max_requests:
                # 计算需要等待的时间
                wait_time = self.request_times[0] + self.window_sec - now
                if wait_time > 0:
                    return wait_time
            
            # 记录本次请求
            self.request_times.append(now)
            return 0


class VariationalClient(DataSourceClient):
    """
    Variational API 客户端
    """
    
    @property
    def source_name(self) -> str:
        return "variational"
    
    def __init__(self, base_url: str = VARIATIONAL_API_BASE):
        self.base_url = base_url
        self.rate_limiter = RateLimiter()
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(10.0),
                headers={"Accept": "application/json"}
            )
        return self._client
    
    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    async def _request_with_retry(self, method: str, url: str, **kwargs) -> Optional[Dict]:
        """
        带重试机制的 HTTP 请求
        """
        client = await self._get_client()
        last_exception = None
        
        for attempt in range(MAX_RETRIES):
            try:
                # 限流检查
                wait_time = await self.rate_limiter.acquire()
                if wait_time > 0:
                    logger.debug(f"限流等待 {wait_time:.2f} 秒")
                    await asyncio.sleep(wait_time)
                    # 重新获取许可
                    await self.rate_limiter.acquire()
                
                # 发送请求
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                return response.json()
                
            except httpx.HTTPStatusError as e:
                last_exception = e
                logger.warning(f"HTTP 错误 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")
                if e.response.status_code == 429:
                    # 被限流，等待更长时间
                    await asyncio.sleep(RETRY_DELAY_SEC * (2 ** attempt))
                elif e.response.status_code >= 500:
                    # 服务器错误，重试
                    await asyncio.sleep(RETRY_DELAY_SEC * (attempt + 1))
                else:
                    # 客户端错误，不重试
                    raise
                    
            except (httpx.RequestError, httpx.TimeoutException) as e:
                last_exception = e
                logger.warning(f"请求错误 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")
                await asyncio.sleep(RETRY_DELAY_SEC * (attempt + 1))
        
        logger.error(f"请求失败，已重试 {MAX_RETRIES} 次: {last_exception}")
        return None
    
    async def fetch_stats(self, ticker: str = TICKER) -> Optional[Dict[str, Any]]:
        """
        获取市场统计数据
        
        Args:
            ticker: 代币符号，默认为 ETH
            
        Returns:
            处理后的快照数据字典，失败返回 None
        """
        try:
            data = await self._request_with_retry("GET", "/metadata/stats")
            if not data:
                return None
            
            # 查找指定 ticker 的数据
            ticker_data = None
            if isinstance(data, list):
                for item in data:
                    if item.get("ticker") == ticker:
                        ticker_data = item
                        break
            elif isinstance(data, dict):
                # 检查 listings 数组
                if "listings" in data:
                    for item in data.get("listings", []):
                        if item.get("ticker") == ticker:
                            ticker_data = item
                            break
                elif data.get("ticker") == ticker:
                    ticker_data = data
                elif "data" in data:
                    for item in data.get("data", []):
                        if item.get("ticker") == ticker:
                            ticker_data = item
                            break
            
            if not ticker_data:
                logger.warning(f"未找到 {ticker} 的数据")
                return None
            
            # 解析并计算派生字段
            return self._parse_and_compute(ticker_data)
            
        except Exception as e:
            logger.error(f"获取统计数据失败: {e}")
            return None
    
    def _parse_and_compute(self, data: Dict) -> Dict[str, Any]:
        """
        解析原始数据并计算派生字段
        
        派生字段：
        - mid: (bid_1k + ask_1k) / 2
        - spread_bps: (ask_1k - bid_1k) / mid * 10000
        - impact_buy_bps: (ask_100k - ask_1k) / mid * 10000
        - impact_sell_bps: (bid_1k - bid_100k) / mid * 10000
        - quote_age_ms: now - quotes_updated_at (毫秒)
        """
        now = datetime.now(timezone.utc)
        
        # 提取报价数据
        quotes = data.get("quotes", {})
        size_1k = quotes.get("size_1k", {})
        size_100k = quotes.get("size_100k", {})
        
        # 解析基础数据
        bid_1k = self._to_decimal(size_1k.get("bid"))
        ask_1k = self._to_decimal(size_1k.get("ask"))
        bid_100k = self._to_decimal(size_100k.get("bid"))
        ask_100k = self._to_decimal(size_100k.get("ask"))
        mark_price = self._to_decimal(data.get("mark_price"))
        
        # 提取持仓数据
        open_interest = data.get("open_interest", {})
        long_oi = self._to_decimal(open_interest.get("long_open_interest"))
        short_oi = self._to_decimal(open_interest.get("short_open_interest"))
        
        # 解析报价更新时间
        quotes_updated_at_str = quotes.get("updated_at")
        quotes_updated_at = None
        if quotes_updated_at_str:
            try:
                quotes_updated_at = datetime.fromisoformat(
                    quotes_updated_at_str.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass
        
        # 计算派生字段
        mid = None
        spread_bps = None
        impact_buy_bps = None
        impact_sell_bps = None
        quote_age_ms = None
        
        if bid_1k is not None and ask_1k is not None:
            mid = (bid_1k + ask_1k) / 2
            
            if mid > 0:
                # 点差 (bps)
                spread_bps = (ask_1k - bid_1k) / mid * Decimal("10000")
                
                # 买入冲击 (bps)
                if ask_100k is not None:
                    impact_buy_bps = (ask_100k - ask_1k) / mid * Decimal("10000")
                
                # 卖出冲击 (bps)
                if bid_100k is not None:
                    impact_sell_bps = (bid_1k - bid_100k) / mid * Decimal("10000")
        
        # 报价延迟 (ms)
        if quotes_updated_at:
            delta = now - quotes_updated_at
            quote_age_ms = int(delta.total_seconds() * 1000)
        
        return {
            "ts": now,
            "source": self.source_name,
            "ticker": data.get("ticker", TICKER),
            "mark_price": mark_price,
            "bid_1k": bid_1k,
            "ask_1k": ask_1k,
            "bid_100k": bid_100k,
            "ask_100k": ask_100k,
            "mid": mid,
            "spread_bps": spread_bps,
            "impact_buy_bps": impact_buy_bps,
            "impact_sell_bps": impact_sell_bps,
            "quote_age_ms": quote_age_ms,
            "funding_rate": self._to_decimal(data.get("funding_rate")),
            "long_oi": long_oi,
            "short_oi": short_oi,
            "volume_24h": self._to_decimal(data.get("volume_24h")),
            "quotes_updated_at": quotes_updated_at,
            "raw_json": json.dumps(data),
        }
    
    @staticmethod
    def _to_decimal(value) -> Optional[Decimal]:
        """安全转换为 Decimal"""
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None
