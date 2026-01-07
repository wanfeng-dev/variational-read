# -*- coding: utf-8 -*-
"""
绩效指标计算模块
实现胜率、最大回撤、夏普率等核心指标
"""
import math
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class TradeResult:
    """交易结果"""
    pnl_bps: float  # 盈亏 (bps)
    is_win: bool    # 是否盈利


def calculate_win_rate(trades: List[TradeResult]) -> float:
    """
    计算胜率
    
    公式: win_rate = win_count / total_signals
    
    Args:
        trades: 交易结果列表
        
    Returns:
        胜率 (0-1)
    """
    if not trades:
        return 0.0
    
    win_count = sum(1 for t in trades if t.is_win)
    return win_count / len(trades)


def calculate_avg_win(trades: List[TradeResult]) -> float:
    """
    计算平均盈利
    
    公式: avg_win = sum(win_pnl) / win_count
    
    Args:
        trades: 交易结果列表
        
    Returns:
        平均盈利 (bps)
    """
    wins = [t.pnl_bps for t in trades if t.is_win]
    if not wins:
        return 0.0
    return sum(wins) / len(wins)


def calculate_avg_loss(trades: List[TradeResult]) -> float:
    """
    计算平均亏损
    
    公式: avg_loss = sum(loss_pnl) / loss_count
    
    Args:
        trades: 交易结果列表
        
    Returns:
        平均亏损 (bps，负值)
    """
    losses = [t.pnl_bps for t in trades if not t.is_win]
    if not losses:
        return 0.0
    return sum(losses) / len(losses)


def calculate_profit_factor(trades: List[TradeResult]) -> float:
    """
    计算盈亏比
    
    公式: profit_factor = |avg_win| / |avg_loss|
    
    Args:
        trades: 交易结果列表
        
    Returns:
        盈亏比
    """
    avg_win = calculate_avg_win(trades)
    avg_loss = calculate_avg_loss(trades)
    
    if avg_loss == 0:
        return float('inf') if avg_win > 0 else 0.0
    
    return abs(avg_win / avg_loss)


def calculate_total_pnl(trades: List[TradeResult]) -> float:
    """
    计算总盈亏
    
    Args:
        trades: 交易结果列表
        
    Returns:
        总盈亏 (bps)
    """
    return sum(t.pnl_bps for t in trades)


def calculate_max_drawdown(pnl_series: List[float]) -> float:
    """
    计算最大回撤
    
    公式: max_drawdown = max(peak - trough) for all peaks
    
    最大回撤表示从任意高点到随后低点的最大跌幅
    
    Args:
        pnl_series: 累计盈亏序列
        
    Returns:
        最大回撤 (bps，正值表示回撤幅度)
    """
    if not pnl_series:
        return 0.0
    
    max_drawdown = 0.0
    peak = pnl_series[0]
    
    for pnl in pnl_series:
        if pnl > peak:
            peak = pnl
        drawdown = peak - pnl
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            
    return max_drawdown


def calculate_cumulative_pnl(trades: List[TradeResult]) -> List[float]:
    """
    计算累计盈亏序列
    
    Args:
        trades: 交易结果列表
        
    Returns:
        累计盈亏序列
    """
    cumulative = []
    total = 0.0
    
    for trade in trades:
        total += trade.pnl_bps
        cumulative.append(total)
        
    return cumulative


def calculate_sharpe_ratio(
    trades: List[TradeResult],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252 * 24 * 60,  # 1分钟级别，每年约 365,000+ 个周期
) -> float:
    """
    计算夏普率
    
    公式: sharpe = (avg_return - risk_free) / std(returns) * sqrt(periods_per_year)
    
    夏普率衡量单位风险的超额收益，值越高表示风险调整后收益越好
    
    Args:
        trades: 交易结果列表
        risk_free_rate: 无风险利率 (年化)
        periods_per_year: 每年交易周期数
        
    Returns:
        年化夏普率
    """
    if len(trades) < 2:
        return 0.0
    
    returns = [t.pnl_bps for t in trades]
    
    # 计算平均收益
    avg_return = sum(returns) / len(returns)
    
    # 计算标准差
    variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
    std_dev = math.sqrt(variance)
    
    if std_dev == 0:
        return 0.0
    
    # 计算每周期无风险收益
    risk_free_per_period = risk_free_rate / periods_per_year
    
    # 计算夏普率并年化
    sharpe = (avg_return - risk_free_per_period) / std_dev
    annualized_sharpe = sharpe * math.sqrt(periods_per_year)
    
    return annualized_sharpe


def calculate_sortino_ratio(
    trades: List[TradeResult],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252 * 24 * 60,
) -> float:
    """
    计算索提诺比率
    
    与夏普率类似，但只考虑下行风险（负收益的波动）
    
    Args:
        trades: 交易结果列表
        risk_free_rate: 无风险利率 (年化)
        periods_per_year: 每年交易周期数
        
    Returns:
        年化索提诺比率
    """
    if len(trades) < 2:
        return 0.0
    
    returns = [t.pnl_bps for t in trades]
    avg_return = sum(returns) / len(returns)
    
    # 只计算负收益的标准差（下行波动）
    negative_returns = [r for r in returns if r < 0]
    
    if not negative_returns:
        return float('inf') if avg_return > 0 else 0.0
    
    downside_variance = sum(r ** 2 for r in negative_returns) / len(negative_returns)
    downside_std = math.sqrt(downside_variance)
    
    if downside_std == 0:
        return 0.0
    
    risk_free_per_period = risk_free_rate / periods_per_year
    sortino = (avg_return - risk_free_per_period) / downside_std
    annualized_sortino = sortino * math.sqrt(periods_per_year)
    
    return annualized_sortino


def calculate_calmar_ratio(
    trades: List[TradeResult],
    periods_per_year: int = 252 * 24 * 60,
) -> float:
    """
    计算卡玛比率
    
    公式: calmar = annualized_return / max_drawdown
    
    衡量收益与最大回撤的关系
    
    Args:
        trades: 交易结果列表
        periods_per_year: 每年交易周期数
        
    Returns:
        卡玛比率
    """
    if not trades:
        return 0.0
    
    # 计算年化收益
    total_pnl = calculate_total_pnl(trades)
    avg_pnl_per_trade = total_pnl / len(trades)
    # 假设每个交易周期产生一笔交易
    annualized_return = avg_pnl_per_trade * periods_per_year
    
    # 计算最大回撤
    cumulative = calculate_cumulative_pnl(trades)
    max_dd = calculate_max_drawdown(cumulative)
    
    if max_dd == 0:
        return float('inf') if annualized_return > 0 else 0.0
    
    return annualized_return / max_dd


def calculate_metrics(trades: List[TradeResult]) -> Dict[str, Any]:
    """
    计算所有绩效指标
    
    Args:
        trades: 交易结果列表
        
    Returns:
        包含所有指标的字典
    """
    if not trades:
        return {
            "total_signals": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate": 0.0,
            "avg_win_bps": 0.0,
            "avg_loss_bps": 0.0,
            "profit_factor": 0.0,
            "total_pnl_bps": 0.0,
            "max_drawdown_bps": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "calmar_ratio": 0.0,
        }
    
    win_count = sum(1 for t in trades if t.is_win)
    loss_count = len(trades) - win_count
    cumulative = calculate_cumulative_pnl(trades)
    
    return {
        "total_signals": len(trades),
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": calculate_win_rate(trades),
        "avg_win_bps": calculate_avg_win(trades),
        "avg_loss_bps": calculate_avg_loss(trades),
        "profit_factor": calculate_profit_factor(trades),
        "total_pnl_bps": calculate_total_pnl(trades),
        "max_drawdown_bps": calculate_max_drawdown(cumulative),
        "sharpe_ratio": calculate_sharpe_ratio(trades),
        "sortino_ratio": calculate_sortino_ratio(trades),
        "calmar_ratio": calculate_calmar_ratio(trades),
    }
