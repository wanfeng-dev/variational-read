# -*- coding: utf-8 -*-
"""
ORM 模型定义
"""
from sqlalchemy import Column, Integer, String, DateTime, Numeric, Text, Index, Boolean
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class Snapshot(Base):
    """
    快照数据模型
    存储从 Variational API 采集的 ETH 市场数据
    """
    __tablename__ = "snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    source = Column(String(20), nullable=False, default="variational", index=True)
    ticker = Column(String(10), nullable=False, default="ETH", index=True)
    
    # 原始数据
    mark_price = Column(Numeric(20, 8), nullable=True)
    bid_1k = Column(Numeric(20, 8), nullable=True)
    ask_1k = Column(Numeric(20, 8), nullable=True)
    bid_100k = Column(Numeric(20, 8), nullable=True)
    ask_100k = Column(Numeric(20, 8), nullable=True)
    
    # 派生字段
    mid = Column(Numeric(20, 8), nullable=True)
    spread_bps = Column(Numeric(10, 4), nullable=True)
    impact_buy_bps = Column(Numeric(10, 4), nullable=True)
    impact_sell_bps = Column(Numeric(10, 4), nullable=True)
    quote_age_ms = Column(Integer, nullable=True)
    
    # 其他数据
    funding_rate = Column(Numeric(20, 10), nullable=True)
    long_oi = Column(Numeric(20, 8), nullable=True)
    short_oi = Column(Numeric(20, 8), nullable=True)
    volume_24h = Column(Numeric(30, 8), nullable=True)
    quotes_updated_at = Column(DateTime, nullable=True)
    
    # 原始 JSON（可选）
    raw_json = Column(Text, nullable=True)

    # 复合索引
    __table_args__ = (
        Index("ix_snapshots_source_ticker_ts", "source", "ticker", "ts"),
    )

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "ts": self.ts.isoformat() if self.ts else None,
            "source": self.source,
            "ticker": self.ticker,
            "mark_price": float(self.mark_price) if self.mark_price else None,
            "bid_1k": float(self.bid_1k) if self.bid_1k else None,
            "ask_1k": float(self.ask_1k) if self.ask_1k else None,
            "bid_100k": float(self.bid_100k) if self.bid_100k else None,
            "ask_100k": float(self.ask_100k) if self.ask_100k else None,
            "mid": float(self.mid) if self.mid else None,
            "spread_bps": float(self.spread_bps) if self.spread_bps else None,
            "impact_buy_bps": float(self.impact_buy_bps) if self.impact_buy_bps else None,
            "impact_sell_bps": float(self.impact_sell_bps) if self.impact_sell_bps else None,
            "quote_age_ms": self.quote_age_ms,
            "funding_rate": float(self.funding_rate) if self.funding_rate else None,
            "long_oi": float(self.long_oi) if self.long_oi else None,
            "short_oi": float(self.short_oi) if self.short_oi else None,
            "volume_24h": float(self.volume_24h) if self.volume_24h else None,
            "quotes_updated_at": self.quotes_updated_at.isoformat() if self.quotes_updated_at else None,
        }

    def __repr__(self):
        return f"<Snapshot(id={self.id}, source={self.source}, ticker={self.ticker}, ts={self.ts}, mid={self.mid})>"


class Signal(Base):
    """
    交易信号模型
    存储信号引擎生成的交易信号
    """
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    ticker = Column(String(10), nullable=False, default="ETH", index=True)
    
    # 信号方向与价格
    side = Column(String(10), nullable=False)  # LONG / SHORT
    entry_price = Column(Numeric(20, 8), nullable=False)
    tp_price = Column(Numeric(20, 8), nullable=False)  # 止盈价
    sl_price = Column(Numeric(20, 8), nullable=False)  # 止损价
    
    # 信号详情
    confidence = Column(Numeric(5, 4), nullable=True)  # 置信度 0-1
    rationale = Column(Text, nullable=True)  # 信号理由
    filters_passed = Column(Text, nullable=True)  # 通过的过滤器列表 JSON
    
    # 突破回收数据
    breakout_price = Column(Numeric(20, 8), nullable=True)
    reclaim_price = Column(Numeric(20, 8), nullable=True)
    
    # 信号状态
    status = Column(String(20), nullable=False, default="PENDING")  # PENDING/TP_HIT/SL_HIT/EXPIRED
    result_pnl_bps = Column(Numeric(10, 4), nullable=True)  # 结果盈亏 (bps)
    closed_at = Column(DateTime, nullable=True)  # 平仓时间

    __table_args__ = (
        Index("ix_signals_ticker_ts", "ticker", "ts"),
        Index("ix_signals_status", "status"),
    )

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "ts": self.ts.isoformat() if self.ts else None,
            "ticker": self.ticker,
            "side": self.side,
            "entry_price": float(self.entry_price) if self.entry_price else None,
            "tp_price": float(self.tp_price) if self.tp_price else None,
            "sl_price": float(self.sl_price) if self.sl_price else None,
            "confidence": float(self.confidence) if self.confidence else None,
            "rationale": self.rationale,
            "filters_passed": self.filters_passed,
            "breakout_price": float(self.breakout_price) if self.breakout_price else None,
            "reclaim_price": float(self.reclaim_price) if self.reclaim_price else None,
            "status": self.status,
            "result_pnl_bps": float(self.result_pnl_bps) if self.result_pnl_bps else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
        }

    def __repr__(self):
        return f"<Signal(id={self.id}, side={self.side}, status={self.status})>"


class Alert(Base):
    """
    预警记录模型
    存储各类预警信息
    """
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    type = Column(String(50), nullable=False, index=True)  # 预警类型
    priority = Column(String(10), nullable=False, default="MEDIUM")  # HIGH/MEDIUM/LOW
    ticker = Column(String(10), nullable=False, default="ETH")
    message = Column(Text, nullable=False)  # 预警内容
    data = Column(Text, nullable=True)  # 关联数据 JSON
    acknowledged = Column(Boolean, nullable=False, default=False)  # 是否已确认

    __table_args__ = (
        Index("ix_alerts_type_ts", "type", "ts"),
        Index("ix_alerts_priority", "priority"),
    )

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "ts": self.ts.isoformat() if self.ts else None,
            "type": self.type,
            "priority": self.priority,
            "ticker": self.ticker,
            "message": self.message,
            "data": self.data,
            "acknowledged": self.acknowledged,
        }

    def __repr__(self):
        return f"<Alert(id={self.id}, type={self.type}, priority={self.priority})>"


class Feature(Base):
    """
    特征数据模型
    存储计算的技术特征
    """
    __tablename__ = "features"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    ticker = Column(String(10), nullable=False, default="ETH", index=True)
    
    # 基础价格
    mid = Column(Numeric(20, 8), nullable=True)
    
    # 收益率
    return_5s = Column(Numeric(20, 10), nullable=True)
    return_15s = Column(Numeric(20, 10), nullable=True)
    return_60s = Column(Numeric(20, 10), nullable=True)
    
    # 波动率
    std_60s = Column(Numeric(20, 10), nullable=True)
    
    # 技术指标
    rsi_14 = Column(Numeric(10, 4), nullable=True)
    z_score = Column(Numeric(10, 4), nullable=True)
    
    # 区间
    range_high_20m = Column(Numeric(20, 8), nullable=True)
    range_low_20m = Column(Numeric(20, 8), nullable=True)
    
    # 流动性指标（从 snapshot 复制）
    spread_bps = Column(Numeric(10, 4), nullable=True)
    impact_buy_bps = Column(Numeric(10, 4), nullable=True)
    impact_sell_bps = Column(Numeric(10, 4), nullable=True)
    quote_age_ms = Column(Integer, nullable=True)
    
    # 多空比
    long_short_ratio = Column(Numeric(10, 4), nullable=True)

    __table_args__ = (
        Index("ix_features_ticker_ts", "ticker", "ts"),
    )

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "ts": self.ts.isoformat() if self.ts else None,
            "ticker": self.ticker,
            "mid": float(self.mid) if self.mid else None,
            "return_5s": float(self.return_5s) if self.return_5s else None,
            "return_15s": float(self.return_15s) if self.return_15s else None,
            "return_60s": float(self.return_60s) if self.return_60s else None,
            "std_60s": float(self.std_60s) if self.std_60s else None,
            "rsi_14": float(self.rsi_14) if self.rsi_14 else None,
            "z_score": float(self.z_score) if self.z_score else None,
            "range_high_20m": float(self.range_high_20m) if self.range_high_20m else None,
            "range_low_20m": float(self.range_low_20m) if self.range_low_20m else None,
            "spread_bps": float(self.spread_bps) if self.spread_bps else None,
            "impact_buy_bps": float(self.impact_buy_bps) if self.impact_buy_bps else None,
            "impact_sell_bps": float(self.impact_sell_bps) if self.impact_sell_bps else None,
            "quote_age_ms": self.quote_age_ms,
            "long_short_ratio": float(self.long_short_ratio) if self.long_short_ratio else None,
        }

    def __repr__(self):
        return f"<Feature(id={self.id}, ticker={self.ticker}, ts={self.ts}, rsi_14={self.rsi_14})>"


class BacktestRun(Base):
    """
    回测运行记录模型
    存储回测参数和结果
    """
    __tablename__ = "backtest_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    
    # 参数
    params = Column(Text, nullable=True)  # 参数 JSON
    data_start = Column(DateTime, nullable=False)  # 数据起始时间
    data_end = Column(DateTime, nullable=False)  # 数据结束时间
    
    # 结果统计
    total_signals = Column(Integer, nullable=True, default=0)
    win_count = Column(Integer, nullable=True, default=0)
    loss_count = Column(Integer, nullable=True, default=0)
    win_rate = Column(Numeric(5, 4), nullable=True)  # 胜率
    avg_win_bps = Column(Numeric(10, 4), nullable=True)  # 平均盈利 bps
    avg_loss_bps = Column(Numeric(10, 4), nullable=True)  # 平均亏损 bps
    total_pnl_bps = Column(Numeric(15, 4), nullable=True)  # 总盈亏 bps
    max_drawdown_bps = Column(Numeric(10, 4), nullable=True)  # 最大回撤 bps
    sharpe_ratio = Column(Numeric(10, 4), nullable=True)  # 夏普率
    
    # 详细结果
    results_json = Column(Text, nullable=True)  # 详细结果 JSON

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "params": self.params,
            "data_start": self.data_start.isoformat() if self.data_start else None,
            "data_end": self.data_end.isoformat() if self.data_end else None,
            "total_signals": self.total_signals,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "win_rate": float(self.win_rate) if self.win_rate else None,
            "avg_win_bps": float(self.avg_win_bps) if self.avg_win_bps else None,
            "avg_loss_bps": float(self.avg_loss_bps) if self.avg_loss_bps else None,
            "total_pnl_bps": float(self.total_pnl_bps) if self.total_pnl_bps else None,
            "max_drawdown_bps": float(self.max_drawdown_bps) if self.max_drawdown_bps else None,
            "sharpe_ratio": float(self.sharpe_ratio) if self.sharpe_ratio else None,
            "results_json": self.results_json,
        }

    def __repr__(self):
        return f"<BacktestRun(id={self.id}, win_rate={self.win_rate})>"
