# -*- coding: utf-8 -*-
"""
技术指标计算
实现各类技术分析指标的计算函数
"""
from typing import List, Optional
import math


def calc_sma(prices: List[float], period: int) -> Optional[float]:
    """
    计算简单移动平均 (SMA)
    
    Args:
        prices: 价格序列
        period: 周期数
        
    Returns:
        SMA 值，数据不足返回 None
    """
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def calc_ema(prices: List[float], period: int) -> Optional[float]:
    """
    计算指数移动平均 (EMA)
    
    使用公式: EMA = Price * k + EMA_prev * (1 - k)
    其中 k = 2 / (period + 1)
    
    Args:
        prices: 价格序列
        period: 周期数
        
    Returns:
        EMA 值，数据不足返回 None
    """
    if len(prices) < period:
        return None
    
    k = 2 / (period + 1)
    
    # 使用前 period 个数据的 SMA 作为初始 EMA
    ema = sum(prices[:period]) / period
    
    # 从第 period 个数据开始计算 EMA
    for price in prices[period:]:
        ema = price * k + ema * (1 - k)
    
    return ema


def calc_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """
    计算相对强弱指数 (RSI)
    
    RSI = 100 - (100 / (1 + RS))
    RS = 平均涨幅 / 平均跌幅
    
    Args:
        prices: 价格序列
        period: 周期数，默认 14
        
    Returns:
        RSI 值 (0-100)，数据不足返回 None
    """
    if len(prices) < period + 1:
        return None
    
    # 计算价格变化
    changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    
    # 分离涨跌
    gains = [max(c, 0) for c in changes]
    losses = [abs(min(c, 0)) for c in changes]
    
    # 使用 Wilder 平滑方法计算平均涨跌幅
    # 初始平均值使用 SMA
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    # 后续使用 EMA 平滑
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def calc_std(prices: List[float]) -> Optional[float]:
    """
    计算标准差
    
    Args:
        prices: 价格序列
        
    Returns:
        标准差，数据不足返回 None
    """
    if len(prices) < 2:
        return None
    
    mean = sum(prices) / len(prices)
    variance = sum((p - mean) ** 2 for p in prices) / len(prices)
    
    return math.sqrt(variance)


def calc_atr(highs: List[float], lows: List[float], closes: List[float], 
             period: int = 14) -> Optional[float]:
    """
    计算平均真实范围 (ATR)
    
    True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
    ATR = TR 的移动平均
    
    Args:
        highs: 最高价序列
        lows: 最低价序列
        closes: 收盘价序列
        period: 周期数，默认 14
        
    Returns:
        ATR 值，数据不足返回 None
    """
    n = min(len(highs), len(lows), len(closes))
    if n < period + 1:
        return None
    
    # 计算 True Range
    true_ranges = []
    for i in range(1, n):
        high_low = highs[i] - lows[i]
        high_close = abs(highs[i] - closes[i-1])
        low_close = abs(lows[i] - closes[i-1])
        tr = max(high_low, high_close, low_close)
        true_ranges.append(tr)
    
    if len(true_ranges) < period:
        return None
    
    # 使用 Wilder 平滑方法计算 ATR
    atr = sum(true_ranges[:period]) / period
    
    for i in range(period, len(true_ranges)):
        atr = (atr * (period - 1) + true_ranges[i]) / period
    
    return atr


def calc_z_score(value: float, mean: float, std: float) -> Optional[float]:
    """
    计算 z-score（标准分数）
    
    z = (value - mean) / std
    
    Args:
        value: 当前值
        mean: 均值
        std: 标准差
        
    Returns:
        z-score，标准差为 0 返回 None
    """
    if std == 0 or std is None:
        return None
    
    return (value - mean) / std


def calc_return(current: float, previous: float) -> Optional[float]:
    """
    计算收益率
    
    return = (current - previous) / previous
    
    Args:
        current: 当前价格
        previous: 之前价格
        
    Returns:
        收益率，previous 为 0 返回 None
    """
    if previous is None or previous == 0:
        return None
    if current is None:
        return None
    
    return (current - previous) / previous
