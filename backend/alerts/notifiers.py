# -*- coding: utf-8 -*-
"""
通知器模块
实现各种预警通知渠道
"""
import json
import logging
from typing import List, Optional, Callable, Awaitable
from fastapi import WebSocket

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.models import Alert

logger = logging.getLogger(__name__)


class WebSocketNotifier:
    """
    WebSocket 通知器
    通过 WebSocket 推送预警消息
    """
    
    def __init__(self):
        self._connections: List[WebSocket] = []
        
    async def connect(self, websocket: WebSocket):
        """
        建立 WebSocket 连接
        
        Args:
            websocket: WebSocket 连接对象
        """
        await websocket.accept()
        self._connections.append(websocket)
        logger.info(f"预警 WebSocket 连接建立，当前连接数: {len(self._connections)}")
        
    def disconnect(self, websocket: WebSocket):
        """
        断开 WebSocket 连接
        
        Args:
            websocket: WebSocket 连接对象
        """
        if websocket in self._connections:
            self._connections.remove(websocket)
        logger.info(f"预警 WebSocket 连接断开，当前连接数: {len(self._connections)}")
        
    @property
    def connection_count(self) -> int:
        """获取当前连接数"""
        return len(self._connections)
        
    async def broadcast(self, message: dict):
        """
        广播消息到所有连接
        
        Args:
            message: 要广播的消息
        """
        disconnected = []
        
        for connection in self._connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"预警 WebSocket 发送失败: {e}")
                disconnected.append(connection)
        
        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn)
            
    async def send_alert(self, alert: Alert):
        """
        发送预警通知
        
        Args:
            alert: 预警对象
        """
        message = {
            "type": "alert",
            "data": alert.to_dict(),
        }
        await self.broadcast(message)
        logger.debug(f"预警已推送: {alert.type} - {alert.message}")
        
    async def notify(self, alert: Alert):
        """
        notify 方法，用作 AlertEngine 的回调
        
        Args:
            alert: 预警对象
        """
        await self.send_alert(alert)


class TelegramNotifier:
    """
    Telegram 通知器（可选实现）
    通过 Telegram Bot 推送预警消息
    """
    
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        """
        初始化 Telegram 通知器
        
        Args:
            bot_token: Telegram Bot Token
            chat_id: 目标聊天 ID
        """
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._enabled = bool(bot_token and chat_id)
        
        if not self._enabled:
            logger.warning("Telegram 通知器未配置，将跳过 Telegram 通知")
            
    @property
    def enabled(self) -> bool:
        """是否启用"""
        return self._enabled
        
    async def send_alert(self, alert: Alert):
        """
        发送预警通知到 Telegram
        
        Args:
            alert: 预警对象
        """
        if not self._enabled:
            return
            
        try:
            import aiohttp
            
            # 格式化消息
            priority_emoji = {
                "HIGH": "🔴",
                "MEDIUM": "🟡", 
                "LOW": "🟢",
            }
            emoji = priority_emoji.get(alert.priority, "⚪")
            
            text = (
                f"{emoji} *{alert.type}*\n"
                f"优先级: {alert.priority}\n"
                f"代币: {alert.ticker}\n"
                f"消息: {alert.message}\n"
                f"时间: {alert.ts.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
            payload = {
                "chat_id": self._chat_id,
                "text": text,
                "parse_mode": "Markdown",
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        logger.error(f"Telegram 发送失败: {await response.text()}")
                    else:
                        logger.debug(f"Telegram 预警已发送: {alert.type}")
                        
        except ImportError:
            logger.warning("aiohttp 未安装，无法使用 Telegram 通知")
        except Exception as e:
            logger.error(f"Telegram 发送异常: {e}")
            
    async def notify(self, alert: Alert):
        """
        notify 方法，用作 AlertEngine 的回调
        
        Args:
            alert: 预警对象
        """
        await self.send_alert(alert)


class CompositeNotifier:
    """
    组合通知器
    聚合多个通知器，统一发送
    """
    
    def __init__(self):
        self._notifiers: List[Callable[[Alert], Awaitable[None]]] = []
        
    def add_notifier(self, notifier: Callable[[Alert], Awaitable[None]]):
        """
        添加通知器
        
        Args:
            notifier: 通知器的 notify 方法
        """
        self._notifiers.append(notifier)
        
    async def notify(self, alert: Alert):
        """
        通知所有注册的通知器
        
        Args:
            alert: 预警对象
        """
        for notifier in self._notifiers:
            try:
                await notifier(alert)
            except Exception as e:
                logger.error(f"通知器执行失败: {e}")
