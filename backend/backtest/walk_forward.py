# -*- coding: utf-8 -*-
"""
走步验证模块
实现 Walk-Forward Validation 方法
"""
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.models import BacktestRun
from config import (
    TICKER,
    WALK_FORWARD_TRAIN_DAYS,
    WALK_FORWARD_TEST_DAYS,
)
from .backtester import Backtester, BacktestResult
from .metrics import TradeResult, calculate_metrics

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardWindow:
    """走步验证窗口"""
    window_id: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_result: Optional[BacktestResult] = None
    test_result: Optional[BacktestResult] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "window_id": self.window_id,
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "test_start": self.test_start.isoformat(),
            "test_end": self.test_end.isoformat(),
            "train_result": self.train_result.to_dict() if self.train_result else None,
            "test_result": self.test_result.to_dict() if self.test_result else None,
        }


@dataclass
class WalkForwardResult:
    """走步验证结果"""
    data_start: datetime
    data_end: datetime
    train_window_days: int
    test_window_days: int
    step_days: int
    windows: List[WalkForwardWindow] = field(default_factory=list)
    aggregate_metrics: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "data_start": self.data_start.isoformat(),
            "data_end": self.data_end.isoformat(),
            "train_window_days": self.train_window_days,
            "test_window_days": self.test_window_days,
            "step_days": self.step_days,
            "windows": [w.to_dict() for w in self.windows],
            "aggregate_metrics": self.aggregate_metrics,
        }


class WalkForwardValidator:
    """
    走步验证器
    
    实现滚动窗口的训练-测试验证方法：
    
    总数据: [===============================]
             训练窗口1  验证1
                   训练窗口2  验证2
                         训练窗口3  验证3
                               ...
    """
    
    def __init__(
        self,
        train_window_days: int = WALK_FORWARD_TRAIN_DAYS,
        test_window_days: int = WALK_FORWARD_TEST_DAYS,
        step_days: Optional[int] = None,
        params: Optional[Dict[str, Any]] = None,
    ):
        """
        初始化走步验证器
        
        Args:
            train_window_days: 训练窗口大小（天）
            test_window_days: 测试窗口大小（天）
            step_days: 步进大小（天），默认等于测试窗口
            params: 回测参数
        """
        self.train_window_days = train_window_days
        self.test_window_days = test_window_days
        self.step_days = step_days or test_window_days
        self.params = params or {}
        
    def run(
        self,
        db: Session,
        start: datetime,
        end: datetime,
        ticker: str = TICKER,
    ) -> WalkForwardResult:
        """
        运行走步验证
        
        Args:
            db: 数据库会话
            start: 起始时间
            end: 结束时间
            ticker: 代币符号
            
        Returns:
            走步验证结果
        """
        logger.info(
            f"开始走步验证: {start} 到 {end}, "
            f"训练窗口={self.train_window_days}天, "
            f"测试窗口={self.test_window_days}天, "
            f"步进={self.step_days}天"
        )
        
        # 生成窗口
        windows = self._generate_windows(start, end)
        
        if not windows:
            logger.warning("数据范围不足以生成任何验证窗口")
            return WalkForwardResult(
                data_start=start,
                data_end=end,
                train_window_days=self.train_window_days,
                test_window_days=self.test_window_days,
                step_days=self.step_days,
            )
        
        logger.info(f"生成了 {len(windows)} 个验证窗口")
        
        # 运行每个窗口
        for window in windows:
            logger.info(f"运行窗口 {window.window_id}: 训练 {window.train_start} - {window.train_end}")
            
            # 创建回测器
            backtester = Backtester(params=self.params)
            
            # 运行训练集回测（主要用于验证参数）
            window.train_result = backtester.run(
                db=db,
                start=window.train_start,
                end=window.train_end,
                ticker=ticker,
            )
            
            # 运行测试集回测（使用相同参数）
            logger.info(f"运行窗口 {window.window_id}: 测试 {window.test_start} - {window.test_end}")
            window.test_result = backtester.run(
                db=db,
                start=window.test_start,
                end=window.test_end,
                ticker=ticker,
            )
        
        # 聚合测试集结果
        aggregate_metrics = self._aggregate_test_results(windows)
        
        result = WalkForwardResult(
            data_start=start,
            data_end=end,
            train_window_days=self.train_window_days,
            test_window_days=self.test_window_days,
            step_days=self.step_days,
            windows=windows,
            aggregate_metrics=aggregate_metrics,
        )
        
        logger.info(
            f"走步验证完成: {len(windows)} 个窗口, "
            f"聚合胜率 {aggregate_metrics.get('win_rate', 0):.2%}"
        )
        
        return result
    
    def _generate_windows(
        self,
        start: datetime,
        end: datetime,
    ) -> List[WalkForwardWindow]:
        """
        生成验证窗口
        
        Args:
            start: 起始时间
            end: 结束时间
            
        Returns:
            窗口列表
        """
        windows = []
        window_id = 0
        
        train_start = start
        
        while True:
            train_end = train_start + timedelta(days=self.train_window_days)
            test_start = train_end
            test_end = test_start + timedelta(days=self.test_window_days)
            
            # 检查是否超出数据范围
            if test_end > end:
                break
                
            windows.append(WalkForwardWindow(
                window_id=window_id,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            ))
            
            window_id += 1
            train_start = train_start + timedelta(days=self.step_days)
            
        return windows
    
    def _aggregate_test_results(
        self,
        windows: List[WalkForwardWindow],
    ) -> Dict[str, Any]:
        """
        聚合所有测试集结果
        
        Args:
            windows: 窗口列表
            
        Returns:
            聚合指标
        """
        # 收集所有测试集交易
        all_trades = []
        for window in windows:
            if window.test_result and window.test_result.trades:
                for trade in window.test_result.trades:
                    all_trades.append(TradeResult(
                        pnl_bps=trade.pnl_bps,
                        is_win=trade.pnl_bps > 0,
                    ))
        
        if not all_trades:
            return {
                "total_signals": 0,
                "win_count": 0,
                "loss_count": 0,
                "win_rate": 0.0,
                "avg_win_bps": 0.0,
                "avg_loss_bps": 0.0,
                "total_pnl_bps": 0.0,
                "max_drawdown_bps": 0.0,
                "sharpe_ratio": 0.0,
                "total_windows": len(windows),
                "windows_with_trades": sum(
                    1 for w in windows 
                    if w.test_result and w.test_result.trades
                ),
            }
        
        # 计算聚合指标
        metrics = calculate_metrics(all_trades)
        
        # 添加额外统计
        metrics["total_windows"] = len(windows)
        metrics["windows_with_trades"] = sum(
            1 for w in windows 
            if w.test_result and w.test_result.trades
        )
        
        # 计算各窗口胜率的稳定性
        window_win_rates = []
        for window in windows:
            if window.test_result and window.test_result.metrics:
                win_rate = window.test_result.metrics.get("win_rate", 0)
                window_win_rates.append(win_rate)
        
        if window_win_rates:
            avg_win_rate = sum(window_win_rates) / len(window_win_rates)
            variance = sum((r - avg_win_rate) ** 2 for r in window_win_rates) / len(window_win_rates)
            std_win_rate = variance ** 0.5
            
            metrics["avg_window_win_rate"] = avg_win_rate
            metrics["std_window_win_rate"] = std_win_rate
            metrics["min_window_win_rate"] = min(window_win_rates)
            metrics["max_window_win_rate"] = max(window_win_rates)
        
        return metrics
    
    def save_result(
        self,
        db: Session,
        result: WalkForwardResult,
    ) -> BacktestRun:
        """
        保存走步验证结果到数据库
        
        Args:
            db: 数据库会话
            result: 走步验证结果
            
        Returns:
            数据库记录
        """
        run = BacktestRun(
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            params=json.dumps({
                "type": "walk_forward",
                "train_window_days": result.train_window_days,
                "test_window_days": result.test_window_days,
                "step_days": result.step_days,
                **self.params,
            }),
            data_start=result.data_start,
            data_end=result.data_end,
            total_signals=result.aggregate_metrics.get("total_signals", 0),
            win_count=result.aggregate_metrics.get("win_count", 0),
            loss_count=result.aggregate_metrics.get("loss_count", 0),
            win_rate=result.aggregate_metrics.get("win_rate", 0),
            avg_win_bps=result.aggregate_metrics.get("avg_win_bps", 0),
            avg_loss_bps=result.aggregate_metrics.get("avg_loss_bps", 0),
            total_pnl_bps=result.aggregate_metrics.get("total_pnl_bps", 0),
            max_drawdown_bps=result.aggregate_metrics.get("max_drawdown_bps", 0),
            sharpe_ratio=result.aggregate_metrics.get("sharpe_ratio", 0),
            results_json=json.dumps(result.to_dict()),
        )
        
        db.add(run)
        db.commit()
        db.refresh(run)
        
        logger.info(f"走步验证结果已保存, run_id={run.id}")
        
        return run
