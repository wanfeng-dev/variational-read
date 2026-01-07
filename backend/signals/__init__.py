# -*- coding: utf-8 -*-
"""
信号引擎模块
实现假突破回收信号及相关过滤器
"""
from signals.trap_signal import TrapSignalDetector
from signals.filters import (
    SpreadFilter,
    QuoteAgeFilter,
    ImpactFilter,
    VolatilityFilter,
    RSIFilter,
    FilterChain,
)
from signals.signal_engine import SignalEngine

__all__ = [
    "TrapSignalDetector",
    "SpreadFilter",
    "QuoteAgeFilter",
    "ImpactFilter",
    "VolatilityFilter",
    "RSIFilter",
    "FilterChain",
    "SignalEngine",
]
