# -*- coding: utf-8 -*-
"""
定时任务调度器
负责按固定间隔采集数据并存储
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional, Callable, List, Awaitable

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    POLL_INTERVAL_SEC,
    BYBIT_POLL_INTERVAL_SEC,
    TICKERS,
    DATA_SOURCES,
)
from collector.variational_client import VariationalClient
from collector.bybit_client import BybitClient
from collector.base_client import DataSourceClient
from db.database import SessionLocal
from db.models import Snapshot

logger = logging.getLogger(__name__)


class DataCollectorScheduler:
    """
    数据采集调度器
    支持多数据源多标的的并行采集
    """
    
    def __init__(
        self,
        tickers: List[str] = None,
        sources: List[str] = None,
    ):
        self.tickers = tickers or TICKERS
        self.sources = sources or DATA_SOURCES
        
        # 创建客户端实例
        self.clients: Dict[str, DataSourceClient] = {
            "variational": VariationalClient(),
            "bybit": BybitClient(),
        }
        
        # 采集间隔配置
        self.intervals: Dict[str, float] = {
            "variational": POLL_INTERVAL_SEC,
            "bybit": BYBIT_POLL_INTERVAL_SEC,
        }
        
        self._running = False
        self._tasks: Dict[tuple, asyncio.Task] = {}
        self._on_snapshot_callbacks: List[Callable[[dict], Awaitable[None]]] = []
    
    def on_snapshot(self, callback: Callable[[dict], Awaitable[None]]):
        """
        注册快照回调函数
        用于 WebSocket 推送等场景
        """
        self._on_snapshot_callbacks.append(callback)
    
    async def _notify_snapshot(self, snapshot_dict: dict):
        """通知所有回调"""
        for callback in self._on_snapshot_callbacks:
            try:
                await callback(snapshot_dict)
            except Exception as e:
                logger.error(f"快照回调执行失败: {e}")
    
    async def collect_once(self, source: str, ticker: str) -> Optional[dict]:
        """
        执行一次数据采集
        
        Args:
            source: 数据源名称
            ticker: 标的符号
        
        Returns:
            采集的快照数据字典，失败返回 None
        """
        try:
            client = self.clients.get(source)
            if not client:
                logger.error(f"未知数据源: {source}")
                return None
            
            # 从 API 获取数据
            data = await client.fetch_stats(ticker)
            if not data:
                logger.warning(f"[{source}-{ticker}] 未获取到数据")
                return None
            
            # 存储到数据库
            db = SessionLocal()
            try:
                snapshot = Snapshot(
                    ts=data["ts"],
                    source=data["source"],
                    ticker=data["ticker"],
                    mark_price=data["mark_price"],
                    bid_1k=data["bid_1k"],
                    ask_1k=data["ask_1k"],
                    bid_100k=data.get("bid_100k"),
                    ask_100k=data.get("ask_100k"),
                    mid=data["mid"],
                    spread_bps=data["spread_bps"],
                    impact_buy_bps=data.get("impact_buy_bps"),
                    impact_sell_bps=data.get("impact_sell_bps"),
                    quote_age_ms=data["quote_age_ms"],
                    funding_rate=data["funding_rate"],
                    long_oi=data["long_oi"],
                    short_oi=data.get("short_oi"),
                    volume_24h=data["volume_24h"],
                    quotes_updated_at=data["quotes_updated_at"],
                    raw_json=data.get("raw_json"),
                )
                db.add(snapshot)
                db.commit()
                db.refresh(snapshot)
                
                snapshot_dict = snapshot.to_dict()
                logger.info(f"[{source}-{ticker}] 采集成功: id={snapshot.id}, mid={snapshot.mid}")
                
                # 通知回调
                await self._notify_snapshot(snapshot_dict)
                
                return snapshot_dict
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"[{source}-{ticker}] 数据采集失败: {e}")
            return None
    
    async def _collect_loop(self, source: str, ticker: str):
        """单个采集循环"""
        interval = self.intervals.get(source, POLL_INTERVAL_SEC)
        logger.info(f"[{source}-{ticker}] 采集任务启动，间隔 {interval} 秒")
        
        while self._running:
            start_time = asyncio.get_event_loop().time()
            
            # 执行采集
            await self.collect_once(source, ticker)
            
            # 计算下次执行时间
            elapsed = asyncio.get_event_loop().time() - start_time
            sleep_time = max(0, interval - elapsed)
            
            if self._running and sleep_time > 0:
                await asyncio.sleep(sleep_time)
        
        logger.info(f"[{source}-{ticker}] 采集任务已停止")
    
    async def start(self):
        """启动所有数据源的所有标的采集任务"""
        if self._running:
            logger.warning("调度器已在运行")
            return
        
        self._running = True
        
        for source in self.sources:
            for ticker in self.tickers:
                task_key = (source, ticker)
                self._tasks[task_key] = asyncio.create_task(
                    self._collect_loop(source, ticker)
                )
                logger.info(f"启动采集任务: {source}-{ticker}")
    
    async def stop(self):
        """停止所有采集任务"""
        if not self._running:
            return
        
        self._running = False
        
        # 取消所有任务
        for task_key, task in self._tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        
        # 关闭所有客户端
        for client in self.clients.values():
            await client.close()
    
    @property
    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._running
