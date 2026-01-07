# -*- coding: utf-8 -*-
"""
FastAPI 主入口
整合所有路由和启动逻辑
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import LOG_LEVEL, LOG_FORMAT, TICKER, BACKTEST_DEFAULT_DAYS
from datetime import datetime as dt
from db.database import get_db, engine
from db.models import Base, Snapshot, Alert, BacktestRun, Signal, Feature
from collector.scheduler import DataCollectorScheduler
from collector.bybit_client import BybitClient
from features.calculator import FeatureCalculator
from alerts.alert_engine import AlertEngine
from alerts.notifiers import WebSocketNotifier
from backtest.backtester import Backtester
from backtest.walk_forward import WalkForwardValidator
from signals.signal_engine import SignalEngine

# 配置日志
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__)

# 全局调度器
scheduler = DataCollectorScheduler()

# Bybit 客户端（用于 K 线查询）
bybit_client = BybitClient()

# 特征计算器
feature_calculator = FeatureCalculator()

# 预警引擎和通知器
alert_engine = AlertEngine()
alert_ws_notifier = WebSocketNotifier()

# 信号引擎
signal_engine = SignalEngine()

# 信号 WebSocket 连接管理
signal_ws_connections: List[WebSocket] = []

# WebSocket 连接管理
class ConnectionManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket 连接建立，当前连接数: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket 连接断开，当前连接数: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """广播消息到所有连接"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"WebSocket 发送失败: {e}")
                disconnected.append(connection)
        
        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn)


ws_manager = ConnectionManager()


async def broadcast_snapshot(snapshot_dict: dict):
    """广播快照数据"""
    await ws_manager.broadcast({
        "type": "snapshot",
        "data": snapshot_dict
    })


async def broadcast_signal(signal_dict: dict):
    """广播信号数据"""
    message = {"type": "signal", "data": signal_dict}
    disconnected = []
    for ws in signal_ws_connections:
        try:
            await ws.send_json(message)
        except Exception as e:
            logger.warning(f"信号 WebSocket 发送失败: {e}")
            disconnected.append(ws)
    for ws in disconnected:
        if ws in signal_ws_connections:
            signal_ws_connections.remove(ws)


async def broadcast_signal_close(signal_dict: dict):
    """广播信号关闭"""
    message = {"type": "signal_close", "data": signal_dict}
    disconnected = []
    for ws in signal_ws_connections:
        try:
            await ws.send_json(message)
        except Exception as e:
            logger.warning(f"信号关闭 WebSocket 发送失败: {e}")
            disconnected.append(ws)
    for ws in disconnected:
        if ws in signal_ws_connections:
            signal_ws_connections.remove(ws)


async def on_new_feature(feature_dict: dict):
    """新特征回调：触发信号引擎处理"""
    await signal_engine.process(feature_dict)


async def on_new_snapshot(snapshot_dict: dict):
    """新快照回调：触发特征计算"""
    # 广播快照
    await broadcast_snapshot(snapshot_dict)
    # 计算特征
    await feature_calculator.compute(snapshot_dict)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("正在初始化数据库...")
    Base.metadata.create_all(bind=engine)
    
    # 预热特征计算器
    logger.info("正在预热特征计算器...")
    feature_calculator.warmup_from_db()
    
    # 初始化信号引擎
    logger.info("正在初始化信号引擎...")
    signal_engine.load_active_signals()
    signal_engine.on_signal(broadcast_signal)
    signal_engine.on_signal_close(broadcast_signal_close)
    
    # 注册特征计算完成回调（触发信号引擎）
    feature_calculator.on_feature(on_new_feature)
    
    # 注册快照回调（触发特征计算）
    scheduler.on_snapshot(on_new_snapshot)
    
    # 启动数据采集
    logger.info("正在启动数据采集调度器...")
    await scheduler.start()
    
    yield
    
    # 关闭时
    logger.info("正在停止数据采集调度器...")
    await scheduler.stop()


# 创建 FastAPI 应用
app = FastAPI(
    title="Variational ETH 交易系统",
    description="ETH 1分钟级交易信号系统 - 数据采集模块",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === REST API 端点 ===

@app.get("/api/snapshots")
async def get_snapshots(
    limit: int = Query(default=100, ge=1, le=1000),
    source: Optional[str] = Query(default=None, description="数据源: variational/bybit"),
    ticker: str = Query(default=TICKER),
    db: Session = Depends(get_db),
):
    """
    获取快照列表
    
    - **limit**: 返回数量限制，默认 100，最大 1000
    - **source**: 数据源 (variational/bybit)
    - **ticker**: 代币符号，默认 ETH
    """
    query = db.query(Snapshot).filter(Snapshot.ticker == ticker)
    
    if source:
        query = query.filter(Snapshot.source == source)
    
    snapshots = query.order_by(desc(Snapshot.ts)).limit(limit).all()
    total = query.count()
    
    return {
        "snapshots": [s.to_dict() for s in snapshots],
        "total": total,
    }


@app.get("/api/snapshots/latest")
async def get_latest_snapshot(
    source: Optional[str] = Query(default=None, description="数据源: variational/bybit"),
    ticker: str = Query(default=TICKER),
    db: Session = Depends(get_db),
):
    """
    获取最新快照
    
    - **source**: 数据源 (variational/bybit)
    - **ticker**: 代币符号，默认 ETH
    """
    query = db.query(Snapshot).filter(Snapshot.ticker == ticker)
    
    if source:
        query = query.filter(Snapshot.source == source)
    
    snapshot = query.order_by(desc(Snapshot.ts)).first()
    
    if not snapshot:
        return {"snapshot": None}
    
    return {"snapshot": snapshot.to_dict()}


@app.get("/api/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "ok",
        "scheduler_running": scheduler.is_running,
        "feature_calculator_initialized": feature_calculator.is_initialized,
        "feature_window_size": feature_calculator.window_size,
        "ws_connections": len(ws_manager.active_connections),
        "alert_ws_connections": alert_ws_notifier.connection_count,
        "signal_ws_connections": len(signal_ws_connections),
        "signal_engine_active_signals": signal_engine.active_signal_count,
        "signal_engine_has_breakout": signal_engine.has_active_breakout,
    }


# === Features API 端点 ===

@app.get("/api/features/latest")
async def get_latest_feature(
    source: Optional[str] = Query(default=None, description="数据源: variational/bybit"),
    ticker: str = Query(default=TICKER),
    db: Session = Depends(get_db),
):
    """
    获取最新特征
    
    - **source**: 数据源 (variational/bybit)
    - **ticker**: 代币符号，默认 ETH
    """
    query = db.query(Feature).filter(Feature.ticker == ticker)
    
    if source:
        query = query.filter(Feature.source == source)
    
    feature = query.order_by(desc(Feature.ts)).first()
    
    if not feature:
        return {"feature": None}
    
    return {"feature": feature.to_dict()}


@app.get("/api/features/history")
async def get_feature_history(
    source: Optional[str] = Query(default=None, description="数据源: variational/bybit"),
    ticker: str = Query(default=TICKER),
    start: Optional[str] = Query(default=None, description="开始时间 ISO 格式"),
    end: Optional[str] = Query(default=None, description="结束时间 ISO 格式"),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """
    获取历史特征
    
    - **source**: 数据源 (variational/bybit)
    - **ticker**: 代币符号，默认 ETH
    - **start**: 开始时间
    - **end**: 结束时间
    - **limit**: 返回数量限制，默认 100，最大 1000
    """
    query = db.query(Feature).filter(Feature.ticker == ticker)
    
    if source:
        query = query.filter(Feature.source == source)
    
    if start:
        try:
            start_dt = dt.fromisoformat(start.replace('Z', '+00:00'))
            query = query.filter(Feature.ts >= start_dt)
        except ValueError:
            pass
    
    if end:
        try:
            end_dt = dt.fromisoformat(end.replace('Z', '+00:00'))
            query = query.filter(Feature.ts <= end_dt)
        except ValueError:
            pass
    
    features = (
        query
        .order_by(desc(Feature.ts))
        .limit(limit)
        .all()
    )
    
    total = query.count()
    
    return {
        "features": [f.to_dict() for f in features],
        "total": total,
    }


# === 预警 API 端点 ===

@app.get("/api/alerts/history")
async def get_alert_history(
    type: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """
    获取预警历史
    
    - **type**: 预警类型过滤
    - **priority**: 优先级过滤 (HIGH/MEDIUM/LOW)
    - **start**: 起始时间 (ISO 格式)
    - **end**: 结束时间 (ISO 格式)
    - **limit**: 返回数量限制
    """
    from datetime import datetime as dt
    
    query = db.query(Alert)
    
    if type:
        query = query.filter(Alert.type == type)
    if priority:
        query = query.filter(Alert.priority == priority)
    if start:
        query = query.filter(Alert.ts >= dt.fromisoformat(start))
    if end:
        query = query.filter(Alert.ts <= dt.fromisoformat(end))
    
    alerts = query.order_by(desc(Alert.ts)).limit(limit).all()
    total = query.count()
    
    return {
        "alerts": [a.to_dict() for a in alerts],
        "total": total,
    }


@app.put("/api/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: int,
    db: Session = Depends(get_db),
):
    """
    确认预警
    
    - **alert_id**: 预警 ID
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.acknowledged = True
    db.commit()
    
    return {"success": True, "alert": alert.to_dict()}


# === 回测 API 端点 ===

@app.post("/api/backtest/run")
async def run_backtest(
    start: str = Query(..., description="起始时间 (ISO 格式)"),
    end: str = Query(..., description="结束时间 (ISO 格式)"),
    params: Optional[str] = Query(default=None, description="参数 JSON"),
    db: Session = Depends(get_db),
):
    """
    运行回测
    
    - **start**: 起始时间
    - **end**: 结束时间
    - **params**: 自定义参数 (JSON 格式)
    """
    from datetime import datetime as dt
    import json
    
    start_dt = dt.fromisoformat(start)
    end_dt = dt.fromisoformat(end)
    custom_params = json.loads(params) if params else {}
    
    backtester = Backtester(params=custom_params)
    result = backtester.run(db, start_dt, end_dt)
    run = backtester.save_result(db, result)
    
    return {"run_id": run.id, "metrics": result.metrics}


@app.get("/api/backtest/results/{run_id}")
async def get_backtest_result(
    run_id: int,
    db: Session = Depends(get_db),
):
    """
    获取回测结果
    
    - **run_id**: 回测运行 ID
    """
    import json
    
    run = db.query(BacktestRun).filter(BacktestRun.id == run_id).first()
    if not run:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Backtest run not found")
    
    result = run.to_dict()
    if run.results_json:
        result["details"] = json.loads(run.results_json)
    
    return {"run": result}


@app.get("/api/backtest/list")
async def list_backtest_runs(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    获取回测运行列表
    
    - **limit**: 返回数量限制
    """
    runs = (
        db.query(BacktestRun)
        .order_by(desc(BacktestRun.started_at))
        .limit(limit)
        .all()
    )
    
    return {"runs": [r.to_dict() for r in runs]}


@app.post("/api/backtest/walk-forward")
async def run_walk_forward(
    start: str = Query(..., description="起始时间 (ISO 格式)"),
    end: str = Query(..., description="结束时间 (ISO 格式)"),
    train_window: int = Query(default=7, description="训练窗口（天）"),
    test_window: int = Query(default=1, description="测试窗口（天）"),
    step_size: int = Query(default=1, description="步进大小（天）"),
    params: Optional[str] = Query(default=None, description="参数 JSON"),
    db: Session = Depends(get_db),
):
    """
    运行走步验证
    
    - **start**: 起始时间
    - **end**: 结束时间
    - **train_window**: 训练窗口大小（天）
    - **test_window**: 测试窗口大小（天）
    - **step_size**: 步进大小（天）
    - **params**: 自定义参数 (JSON 格式)
    """
    from datetime import datetime as dt
    import json
    
    start_dt = dt.fromisoformat(start)
    end_dt = dt.fromisoformat(end)
    custom_params = json.loads(params) if params else {}
    
    validator = WalkForwardValidator(
        train_window_days=train_window,
        test_window_days=test_window,
        step_days=step_size,
        params=custom_params,
    )
    result = validator.run(db, start_dt, end_dt)
    run = validator.save_result(db, result)
    
    return {
        "run_id": run.id,
        "aggregate_metrics": result.aggregate_metrics,
        "total_windows": len(result.windows),
    }


# === 信号 API 端点 ===

@app.get("/api/signals/latest")
async def get_latest_signal(
    source: Optional[str] = Query(default=None, description="数据源: variational/bybit"),
    ticker: str = Query(default=TICKER),
    db: Session = Depends(get_db),
):
    """
    获取最新信号
    
    - **source**: 数据源 (variational/bybit)
    - **ticker**: 代币符号，默认 ETH
    """
    query = db.query(Signal).filter(Signal.ticker == ticker)
    
    if source:
        query = query.filter(Signal.source == source)
    
    signal = query.order_by(desc(Signal.ts)).first()
    
    return {"signal": signal.to_dict() if signal else None}


@app.get("/api/signals/history")
async def get_signal_history(
    source: Optional[str] = Query(default=None, description="数据源: variational/bybit"),
    ticker: Optional[str] = Query(default=None, description="代币符号"),
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """
    获取信号历史
    
    - **source**: 数据源 (variational/bybit)
    - **ticker**: 代币符号
    """
    from datetime import datetime as dt
    
    query = db.query(Signal)
    
    if source:
        query = query.filter(Signal.source == source)
    if ticker:
        query = query.filter(Signal.ticker == ticker)
    if start:
        query = query.filter(Signal.ts >= dt.fromisoformat(start))
    if end:
        query = query.filter(Signal.ts <= dt.fromisoformat(end))
    if status:
        query = query.filter(Signal.status == status)
    
    signals = query.order_by(desc(Signal.ts)).limit(limit).all()
    total = query.count()
    
    return {
        "signals": [s.to_dict() for s in signals],
        "total": total,
    }


@app.get("/api/signals/stats")
async def get_signal_stats(
    source: Optional[str] = Query(default=None, description="数据源: variational/bybit"),
    ticker: Optional[str] = Query(default=None, description="代币符号"),
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    获取信号统计
    
    - **source**: 数据源 (variational/bybit)
    - **ticker**: 代币符号
    """
    from datetime import datetime as dt
    from sqlalchemy import func
    
    query = db.query(Signal)
    
    if source:
        query = query.filter(Signal.source == source)
    if ticker:
        query = query.filter(Signal.ticker == ticker)
    if start:
        query = query.filter(Signal.ts >= dt.fromisoformat(start))
    if end:
        query = query.filter(Signal.ts <= dt.fromisoformat(end))
    
    total = query.count()
    
    if total == 0:
        return {
            "total_signals": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate": 0,
            "avg_pnl_bps": 0,
        }
    
    win_count = query.filter(Signal.status == "TP_HIT").count()
    loss_count = query.filter(Signal.status == "SL_HIT").count()
    closed_count = win_count + loss_count
    
    avg_pnl = db.query(func.avg(Signal.result_pnl_bps)).filter(
        Signal.result_pnl_bps.isnot(None)
    ).scalar() or 0
    
    return {
        "total_signals": total,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": win_count / closed_count if closed_count > 0 else 0,
        "avg_pnl_bps": float(avg_pnl),
    }


# === K线数据 API ===

@app.get("/api/klines")
async def get_klines(
    ticker: str = Query(default="BTC", description="代币符号: BTC/ETH"),
    interval: str = Query(default="1", description="K线周期: 1/5/15/60/240/D"),
    limit: int = Query(default=200, ge=1, le=1000, description="返回数量"),
):
    """
    获取 Bybit K 线数据
    
    - **ticker**: 代币符号 (BTC/ETH)
    - **interval**: K线周期
      - 1: 1分钟
      - 5: 5分钟
      - 15: 15分钟
      - 60: 1小时
      - 240: 4小时
      - D: 1天
    - **limit**: 返回数量，最大 1000
    
    返回格式: [{time, open, high, low, close, volume}, ...]
    """
    klines = await bybit_client.fetch_klines(ticker, interval, limit)
    return {
        "klines": klines,
        "ticker": ticker,
        "interval": interval,
        "source": "bybit",
    }


# === 数据源状态 API ===

@app.get("/api/sources/status")
async def get_sources_status():
    """
    获取所有数据源状态
    
    返回各数据源的连接状态和延迟
    """
    sources = []
    
    # Variational 状态
    var_latency = getattr(scheduler, 'get_latency', lambda x: None)("variational")
    sources.append({
        "name": "variational",
        "status": "ok" if scheduler.is_running else "error",
        "latency_ms": var_latency or 0,
        "tickers": ["BTC", "ETH"],
    })
    
    # Bybit 状态
    bybit_latency = getattr(scheduler, 'get_latency', lambda x: None)("bybit")
    sources.append({
        "name": "bybit",
        "status": "ok" if scheduler.is_running else "error",
        "latency_ms": bybit_latency or 0,
        "tickers": ["BTC", "ETH"],
    })
    
    return {"sources": sources}


# === WebSocket 端点 ===

@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """
    WebSocket 预警推送
    
    连接后自动接收预警数据
    消息格式: { "type": "alert", "data": {...} }
    """
    await alert_ws_notifier.connect(websocket)
    
    try:
        while True:
            # 等待客户端消息（保持连接）
            data = await websocket.receive_json()
            
            if data.get("action") == "subscribe":
                await websocket.send_json({
                    "type": "subscribed",
                    "channel": "alerts",
                })
                
    except WebSocketDisconnect:
        alert_ws_notifier.disconnect(websocket)
    except Exception as e:
        logger.error(f"预警 WebSocket 错误: {e}")
        alert_ws_notifier.disconnect(websocket)


@app.websocket("/ws/signals")
async def websocket_signals(websocket: WebSocket):
    """
    WebSocket 信号推送
    
    连接后自动接收信号数据
    消息格式: 
    - 新信号: { "type": "signal", "data": {...} }
    - 信号关闭: { "type": "signal_close", "data": {...} }
    """
    await websocket.accept()
    signal_ws_connections.append(websocket)
    logger.info(f"信号 WebSocket 连接建立，当前连接数: {len(signal_ws_connections)}")
    
    try:
        while True:
            data = await websocket.receive_json()
            
            if data.get("action") == "subscribe":
                await websocket.send_json({
                    "type": "subscribed",
                    "channel": "signals",
                })
            elif data.get("action") == "get_active":
                # 获取当前活跃信号
                await websocket.send_json({
                    "type": "active_signals",
                    "data": signal_engine.active_signals,
                })
                
    except WebSocketDisconnect:
        if websocket in signal_ws_connections:
            signal_ws_connections.remove(websocket)
        logger.info(f"信号 WebSocket 连接断开，当前连接数: {len(signal_ws_connections)}")
    except Exception as e:
        logger.error(f"信号 WebSocket 错误: {e}")
        if websocket in signal_ws_connections:
            signal_ws_connections.remove(websocket)


@app.websocket("/ws/snapshots")
async def websocket_snapshots(websocket: WebSocket):
    """
    WebSocket 快照推送
    
    连接后自动接收新快照数据
    消息格式: { "type": "snapshot", "data": {...} }
    
    订阅消息: { "action": "subscribe", "source": "bybit", "ticker": "BTC" }
    """
    await ws_manager.connect(websocket)
    
    subscribed_sources = set()
    subscribed_tickers = set()
    
    try:
        while True:
            # 等待客户端消息（主要用于保持连接和处理订阅）
            data = await websocket.receive_json()
            
            # 处理订阅消息
            if data.get("action") == "subscribe":
                source = data.get("source")  # 可选
                ticker = data.get("ticker", TICKER)
                
                if source:
                    subscribed_sources.add(source)
                subscribed_tickers.add(ticker)
                
                await websocket.send_json({
                    "type": "subscribed",
                    "source": source,
                    "ticker": ticker,
                })
                
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket 错误: {e}")
        ws_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
