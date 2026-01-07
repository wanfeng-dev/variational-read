# -*- coding: utf-8 -*-
"""
信号过滤器
实现各类过滤条件，确保信号质量
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    SPREAD_MAX_BPS,
    QUOTE_AGE_MAX_MS,
    IMPACT_MAX_BPS,
    VOL_MIN,
    VOL_MAX,
    RSI_OVERBOUGHT,
    RSI_OVERSOLD,
    RSI_CONFIRM_BUFFER,
)
from signals.trap_signal import SignalCandidate, SignalSide

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """过滤器结果"""
    passed: bool
    filter_name: str
    reason: Optional[str] = None
    
    def __repr__(self):
        if self.passed:
            return f"✓ {self.filter_name}"
        return f"✗ {self.filter_name}: {self.reason}"


class BaseFilter(ABC):
    """过滤器基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """过滤器名称"""
        pass
    
    @abstractmethod
    def check(self, signal: SignalCandidate, feature: Dict[str, Any]) -> FilterResult:
        """
        检查信号是否通过过滤器
        
        Args:
            signal: 信号候选
            feature: 特征数据
            
        Returns:
            过滤器结果
        """
        pass


class SpreadFilter(BaseFilter):
    """
    点差过滤器
    点差过大时不交易，避免滑点损失
    """
    
    def __init__(self, max_spread_bps: float = SPREAD_MAX_BPS):
        self.max_spread_bps = max_spread_bps
    
    @property
    def name(self) -> str:
        return "SpreadFilter"
    
    def check(self, signal: SignalCandidate, feature: Dict[str, Any]) -> FilterResult:
        spread_bps = feature.get("spread_bps")
        
        if spread_bps is None:
            return FilterResult(
                passed=False,
                filter_name=self.name,
                reason="点差数据缺失"
            )
        
        if spread_bps > self.max_spread_bps:
            return FilterResult(
                passed=False,
                filter_name=self.name,
                reason=f"点差过大: {spread_bps:.2f} > {self.max_spread_bps} bps"
            )
        
        return FilterResult(passed=True, filter_name=self.name)


class QuoteAgeFilter(BaseFilter):
    """
    报价新鲜度过滤器
    报价过旧时不交易，确保使用最新数据
    """
    
    def __init__(self, max_age_ms: int = QUOTE_AGE_MAX_MS):
        self.max_age_ms = max_age_ms
    
    @property
    def name(self) -> str:
        return "QuoteAgeFilter"
    
    def check(self, signal: SignalCandidate, feature: Dict[str, Any]) -> FilterResult:
        quote_age_ms = feature.get("quote_age_ms")
        
        if quote_age_ms is None:
            return FilterResult(
                passed=False,
                filter_name=self.name,
                reason="报价延迟数据缺失"
            )
        
        if quote_age_ms > self.max_age_ms:
            return FilterResult(
                passed=False,
                filter_name=self.name,
                reason=f"报价过旧: {quote_age_ms}ms > {self.max_age_ms}ms"
            )
        
        return FilterResult(passed=True, filter_name=self.name)


class ImpactFilter(BaseFilter):
    """
    冲击成本过滤器
    市场冲击过大时不交易，避免大滑点
    """
    
    def __init__(self, max_impact_bps: float = IMPACT_MAX_BPS):
        self.max_impact_bps = max_impact_bps
    
    @property
    def name(self) -> str:
        return "ImpactFilter"
    
    def check(self, signal: SignalCandidate, feature: Dict[str, Any]) -> FilterResult:
        # 根据信号方向选择对应的冲击
        if signal.side == SignalSide.LONG:
            impact = feature.get("impact_buy_bps")
            direction = "买入"
        else:
            impact = feature.get("impact_sell_bps")
            direction = "卖出"
        
        if impact is None:
            return FilterResult(
                passed=False,
                filter_name=self.name,
                reason=f"{direction}冲击数据缺失"
            )
        
        if impact > self.max_impact_bps:
            return FilterResult(
                passed=False,
                filter_name=self.name,
                reason=f"{direction}冲击过大: {impact:.2f} > {self.max_impact_bps} bps"
            )
        
        return FilterResult(passed=True, filter_name=self.name)


class VolatilityFilter(BaseFilter):
    """
    波动率过滤器
    波动率过高或过低时不交易
    """
    
    def __init__(self, min_vol: float = VOL_MIN, max_vol: float = VOL_MAX):
        self.min_vol = min_vol
        self.max_vol = max_vol
    
    @property
    def name(self) -> str:
        return "VolatilityFilter"
    
    def check(self, signal: SignalCandidate, feature: Dict[str, Any]) -> FilterResult:
        std_60s = feature.get("std_60s")
        
        if std_60s is None:
            # 波动率数据缺失时，允许通过（可能数据刚开始收集）
            return FilterResult(
                passed=True,
                filter_name=self.name,
                reason="波动率数据缺失，跳过检查"
            )
        
        if std_60s < self.min_vol:
            return FilterResult(
                passed=False,
                filter_name=self.name,
                reason=f"波动率过低: {std_60s:.6f} < {self.min_vol}"
            )
        
        if std_60s > self.max_vol:
            return FilterResult(
                passed=False,
                filter_name=self.name,
                reason=f"波动率过高: {std_60s:.6f} > {self.max_vol}"
            )
        
        return FilterResult(passed=True, filter_name=self.name)


class RSIFilter(BaseFilter):
    """
    RSI 确认过滤器
    要求 RSI 曾达到极值后回归，确认反转
    
    做空信号：RSI 曾 > overbought，当前 < overbought - buffer
    做多信号：RSI 曾 < oversold，当前 > oversold + buffer
    """
    
    def __init__(
        self,
        overbought: float = RSI_OVERBOUGHT,
        oversold: float = RSI_OVERSOLD,
        confirm_buffer: float = RSI_CONFIRM_BUFFER,
        rsi_history_getter=None,
    ):
        self.overbought = overbought
        self.oversold = oversold
        self.confirm_buffer = confirm_buffer
        self._rsi_history_getter = rsi_history_getter
    
    @property
    def name(self) -> str:
        return "RSIFilter"
    
    def set_rsi_history_getter(self, getter):
        """设置 RSI 历史获取函数"""
        self._rsi_history_getter = getter
    
    def check(self, signal: SignalCandidate, feature: Dict[str, Any]) -> FilterResult:
        current_rsi = feature.get("rsi_14")
        
        if current_rsi is None:
            # RSI 数据缺失时，允许通过
            return FilterResult(
                passed=True,
                filter_name=self.name,
                reason="RSI 数据缺失，跳过检查"
            )
        
        # 获取近期 RSI 极值
        rsi_extreme = None
        if self._rsi_history_getter:
            rsi_extreme = self._rsi_history_getter()
        
        if signal.side == SignalSide.SHORT:
            # 做空：检查 RSI 是否曾超买并回落
            if rsi_extreme and rsi_extreme.get("max_rsi"):
                max_rsi = rsi_extreme["max_rsi"]
                if max_rsi < self.overbought:
                    return FilterResult(
                        passed=False,
                        filter_name=self.name,
                        reason=f"RSI 未达到超买区域: max={max_rsi:.1f} < {self.overbought}"
                    )
                
                # 检查是否已回落
                if current_rsi > self.overbought - self.confirm_buffer:
                    return FilterResult(
                        passed=False,
                        filter_name=self.name,
                        reason=f"RSI 尚未充分回落: {current_rsi:.1f} > {self.overbought - self.confirm_buffer}"
                    )
            else:
                # 没有历史数据，使用当前 RSI 做简单判断
                if current_rsi < self.overbought - self.confirm_buffer * 2:
                    # 当前 RSI 已经较低，可能错过了超买
                    return FilterResult(
                        passed=True,
                        filter_name=self.name,
                        reason="无 RSI 历史，当前 RSI 在合理范围"
                    )
        
        else:  # LONG
            # 做多：检查 RSI 是否曾超卖并回升
            if rsi_extreme and rsi_extreme.get("min_rsi"):
                min_rsi = rsi_extreme["min_rsi"]
                if min_rsi > self.oversold:
                    return FilterResult(
                        passed=False,
                        filter_name=self.name,
                        reason=f"RSI 未达到超卖区域: min={min_rsi:.1f} > {self.oversold}"
                    )
                
                # 检查是否已回升
                if current_rsi < self.oversold + self.confirm_buffer:
                    return FilterResult(
                        passed=False,
                        filter_name=self.name,
                        reason=f"RSI 尚未充分回升: {current_rsi:.1f} < {self.oversold + self.confirm_buffer}"
                    )
            else:
                # 没有历史数据，使用当前 RSI 做简单判断
                if current_rsi > self.oversold + self.confirm_buffer * 2:
                    return FilterResult(
                        passed=True,
                        filter_name=self.name,
                        reason="无 RSI 历史，当前 RSI 在合理范围"
                    )
        
        return FilterResult(passed=True, filter_name=self.name)


class FilterChain:
    """
    过滤器链
    管理和执行一组过滤器
    """
    
    def __init__(self, filters: Optional[List[BaseFilter]] = None):
        self.filters = filters or []
    
    def add(self, filter_: BaseFilter):
        """添加过滤器"""
        self.filters.append(filter_)
        return self
    
    def check_all(
        self,
        signal: SignalCandidate,
        feature: Dict[str, Any],
    ) -> tuple[bool, List[FilterResult]]:
        """
        检查所有过滤器
        
        Args:
            signal: 信号候选
            feature: 特征数据
            
        Returns:
            (是否全部通过, 过滤器结果列表)
        """
        results = []
        all_passed = True
        
        for f in self.filters:
            result = f.check(signal, feature)
            results.append(result)
            if not result.passed:
                all_passed = False
                logger.debug(f"过滤器未通过: {result}")
        
        return all_passed, results
    
    def get_passed_filters(self, results: List[FilterResult]) -> List[str]:
        """获取通过的过滤器名称列表"""
        return [r.filter_name for r in results if r.passed]
    
    def get_failed_filters(self, results: List[FilterResult]) -> List[str]:
        """获取未通过的过滤器名称列表"""
        return [r.filter_name for r in results if not r.passed]
    
    @classmethod
    def create_default(cls) -> "FilterChain":
        """创建默认过滤器链"""
        chain = cls()
        chain.add(SpreadFilter())
        chain.add(QuoteAgeFilter())
        chain.add(ImpactFilter())
        chain.add(VolatilityFilter())
        chain.add(RSIFilter())
        return chain
