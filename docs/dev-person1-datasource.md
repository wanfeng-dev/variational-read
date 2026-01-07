# 人员 1：数据源层改造

## 职责
Bybit 客户端 + Variational 多标的 + 数据库改造

## 产出文件
```
backend/
├── config.py                    # 更新：新增 Bybit 配置、多标的配置
├── collector/
│   ├── base_client.py           # 新增：数据源抽象基类
│   ├── variational_client.py    # 修改：继承基类，支持 BTC
│   ├── bybit_client.py          # 新增：Bybit API 客户端
│   └── scheduler.py             # 修改：支持多数据源多标的调度
├── db/
│   └── models.py                # 修改：Snapshot 增加 source 字段
```

---

## 详细任务

### 1. config.py 更新

新增以下配置：

```python
# === 多标的配置 ===
TICKERS = ["BTC", "ETH"]
DATA_SOURCES = ["variational", "bybit"]

# === Bybit 数据采集 ===
BYBIT_API_BASE = "https://api.bybit.com"
BYBIT_CATEGORY = "linear"  # USDT 永续合约
BYBIT_SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}
BYBIT_POLL_INTERVAL_SEC = 1  # Bybit 公开API无严格限流
BYBIT_TIMEOUT_SEC = 5
```

---

### 2. base_client.py（新建）

定义数据源抽象基类，统一接口：

```python
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
```

---

### 3. bybit_client.py（新建）

实现 Bybit API 客户端：

```python
# -*- coding: utf-8 -*-
"""
Bybit API 客户端
获取 BTC/ETH 永续合约市场数据
"""
import httpx
import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any

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
```

---

### 4. variational_client.py 修改

让现有客户端继承基类，并支持 BTC：

```python
# 主要修改点：

# 1. 导入基类
from collector.base_client import DataSourceClient

# 2. 继承基类
class VariationalClient(DataSourceClient):
    
    @property
    def source_name(self) -> str:
        return "variational"
    
    # 3. fetch_stats 返回值增加 source 字段
    def _parse_and_compute(self, data: Dict) -> Dict[str, Any]:
        # ... 现有逻辑 ...
        return {
            "ts": now,
            "source": self.source_name,  # 新增
            "ticker": data.get("ticker", "ETH"),
            # ... 其他字段保持不变 ...
        }
```

---

### 5. scheduler.py 修改

支持多数据源多标的调度：

```python
# 主要修改点：

from config import TICKERS, DATA_SOURCES, POLL_INTERVAL_SEC, BYBIT_POLL_INTERVAL_SEC
from collector.variational_client import VariationalClient
from collector.bybit_client import BybitClient

class DataCollectorScheduler:
    def __init__(self):
        self.clients = {
            "variational": VariationalClient(),
            "bybit": BybitClient(),
        }
        self.tasks: Dict[Tuple[str, str], asyncio.Task] = {}
        self._callbacks = []
    
    async def start(self):
        """启动所有数据源的所有标的采集任务"""
        for source in DATA_SOURCES:
            for ticker in TICKERS:
                task_key = (source, ticker)
                interval = BYBIT_POLL_INTERVAL_SEC if source == "bybit" else POLL_INTERVAL_SEC
                self.tasks[task_key] = asyncio.create_task(
                    self._collect_loop(source, ticker, interval)
                )
                logger.info(f"启动采集任务: {source}-{ticker}, 间隔: {interval}s")
    
    async def _collect_loop(self, source: str, ticker: str, interval: float):
        """单个采集循环"""
        client = self.clients[source]
        while self.is_running:
            try:
                snapshot = await client.fetch_stats(ticker)
                if snapshot:
                    await self._save_and_notify(snapshot)
            except Exception as e:
                logger.error(f"[{source}-{ticker}] 采集错误: {e}")
            await asyncio.sleep(interval)
```

---

### 6. models.py 修改

Snapshot 表增加 source 字段：

```python
class Snapshot(Base):
    __tablename__ = "snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    source = Column(String(20), nullable=False, default="variational", index=True)  # 新增
    ticker = Column(String(10), nullable=False, default="ETH", index=True)
    
    # ... 其他字段保持不变 ...
    
    # 更新复合索引
    __table_args__ = (
        Index("ix_snapshots_source_ticker_ts", "source", "ticker", "ts"),
    )
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ts": self.ts.isoformat() if self.ts else None,
            "source": self.source,  # 新增
            "ticker": self.ticker,
            # ... 其他字段 ...
        }
```

---

### 7. 数据库迁移脚本

```python
# backend/db/migrate_add_source.py
"""
数据库迁移：为 snapshots 表添加 source 字段
"""
from sqlalchemy import text
from db.database import engine

def migrate():
    with engine.connect() as conn:
        # 检查字段是否已存在
        result = conn.execute(text(
            "SELECT COUNT(*) FROM pragma_table_info('snapshots') WHERE name='source'"
        ))
        if result.scalar() == 0:
            # 添加 source 字段，默认值为 variational
            conn.execute(text(
                "ALTER TABLE snapshots ADD COLUMN source VARCHAR(20) DEFAULT 'variational'"
            ))
            conn.commit()
            print("成功添加 source 字段")
        else:
            print("source 字段已存在")

if __name__ == "__main__":
    migrate()
```

---

## 接口契约

统一快照输出格式：

```python
{
    "ts": datetime,                    # 采集时间 (UTC)
    "source": "variational" | "bybit", # 数据源
    "ticker": "BTC" | "ETH",           # 标的
    "mark_price": Decimal,             # 标记价格
    "bid_1k": Decimal,                 # 买一价
    "ask_1k": Decimal,                 # 卖一价
    "bid_100k": Decimal | None,        # 深度买价
    "ask_100k": Decimal | None,        # 深度卖价
    "mid": Decimal,                    # 中间价
    "spread_bps": Decimal,             # 点差 (bps)
    "impact_buy_bps": Decimal | None,  # 买入冲击 (bps)
    "impact_sell_bps": Decimal | None, # 卖出冲击 (bps)
    "quote_age_ms": int,               # 报价延迟 (ms)
    "funding_rate": Decimal,           # 资金费率
    "long_oi": Decimal,                # 多头/总持仓
    "short_oi": Decimal | None,        # 空头持仓
    "volume_24h": Decimal,             # 24h成交量
    "quotes_updated_at": datetime,     # 报价更新时间
}
```

---

## 检查清单

- [ ] config.py 新增 TICKERS、DATA_SOURCES、Bybit 配置
- [ ] base_client.py 定义 DataSourceClient 抽象基类
- [ ] bybit_client.py 实现 BybitClient
- [ ] bybit_client.py 字段映射与派生字段计算
- [ ] variational_client.py 继承基类，支持 BTC
- [ ] scheduler.py 多数据源多标的调度
- [ ] models.py Snapshot 增加 source 字段
- [ ] 数据库迁移脚本（添加 source 列）
- [ ] 单元测试：BybitClient 数据获取

---

## 对接说明

完成后通知：
- **人员 2**：base_client.py 接口定义、models.py source 字段
- **人员 3**：API 返回数据新增 source 字段

## Git 分支

```
feat/bybit-datasource
```
