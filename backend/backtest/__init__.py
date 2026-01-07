# -*- coding: utf-8 -*-
"""
回测模块
提供回测框架、走步验证和绩效指标计算
"""
from .metrics import calculate_metrics, calculate_sharpe_ratio, calculate_max_drawdown
from .backtester import Backtester, BacktestResult, Trade
from .walk_forward import WalkForwardValidator

__all__ = [
    "calculate_metrics",
    "calculate_sharpe_ratio", 
    "calculate_max_drawdown",
    "Backtester",
    "BacktestResult",
    "Trade",
    "WalkForwardValidator",
]
