# -*- coding: utf-8 -*-
"""
指标计算单元测试
测试 indicators.py 中各函数的正确性
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from features import indicators


class TestSMA:
    """SMA 计算测试"""
    
    def test_sma_basic(self):
        """基本 SMA 计算"""
        prices = [10, 20, 30, 40, 50]
        result = indicators.calc_sma(prices, 3)
        assert result == 40.0  # (30 + 40 + 50) / 3
    
    def test_sma_insufficient_data(self):
        """数据不足"""
        prices = [10, 20]
        result = indicators.calc_sma(prices, 5)
        assert result is None
    
    def test_sma_exact_period(self):
        """数据量等于周期"""
        prices = [10, 20, 30]
        result = indicators.calc_sma(prices, 3)
        assert result == 20.0


class TestEMA:
    """EMA 计算测试"""
    
    def test_ema_basic(self):
        """基本 EMA 计算"""
        prices = [10, 20, 30, 40, 50]
        result = indicators.calc_ema(prices, 3)
        # 初始 EMA = (10+20+30)/3 = 20
        # k = 2/(3+1) = 0.5
        # EMA = 40 * 0.5 + 20 * 0.5 = 30
        # EMA = 50 * 0.5 + 30 * 0.5 = 40
        assert result == 40.0
    
    def test_ema_insufficient_data(self):
        """数据不足"""
        prices = [10, 20]
        result = indicators.calc_ema(prices, 5)
        assert result is None


class TestRSI:
    """RSI 计算测试"""
    
    def test_rsi_all_up(self):
        """全部上涨"""
        prices = [i for i in range(1, 20)]  # 1, 2, 3, ..., 19
        result = indicators.calc_rsi(prices, 14)
        assert result == 100.0
    
    def test_rsi_all_down(self):
        """全部下跌"""
        prices = [i for i in range(20, 0, -1)]  # 20, 19, ..., 1
        result = indicators.calc_rsi(prices, 14)
        # avg_loss > 0, avg_gain = 0, so RSI should be close to 0
        assert result is not None
        assert result < 10  # 应该接近 0
    
    def test_rsi_insufficient_data(self):
        """数据不足"""
        prices = [10, 20, 30]
        result = indicators.calc_rsi(prices, 14)
        assert result is None
    
    def test_rsi_mixed(self):
        """涨跌混合"""
        prices = [100, 102, 101, 103, 102, 104, 103, 105, 
                  104, 106, 105, 107, 106, 108, 107, 109]
        result = indicators.calc_rsi(prices, 14)
        assert result is not None
        assert 0 <= result <= 100


class TestStd:
    """标准差计算测试"""
    
    def test_std_basic(self):
        """基本标准差计算"""
        prices = [10, 20, 30, 40, 50]
        result = indicators.calc_std(prices)
        # mean = 30
        # variance = ((10-30)^2 + (20-30)^2 + (30-30)^2 + (40-30)^2 + (50-30)^2) / 5
        #          = (400 + 100 + 0 + 100 + 400) / 5 = 200
        # std = sqrt(200) = 14.142...
        assert result is not None
        assert abs(result - 14.142135623730951) < 0.0001
    
    def test_std_constant(self):
        """常数序列"""
        prices = [10, 10, 10, 10]
        result = indicators.calc_std(prices)
        assert result == 0.0
    
    def test_std_insufficient_data(self):
        """数据不足"""
        prices = [10]
        result = indicators.calc_std(prices)
        assert result is None


class TestATR:
    """ATR 计算测试"""
    
    def test_atr_basic(self):
        """基本 ATR 计算"""
        highs = [11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 
                 21, 22, 23, 24, 25, 26]
        lows = [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 
                19, 20, 21, 22, 23, 24]
        closes = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 
                  20, 21, 22, 23, 24, 25]
        result = indicators.calc_atr(highs, lows, closes, 14)
        assert result is not None
        assert result > 0
    
    def test_atr_insufficient_data(self):
        """数据不足"""
        highs = [11, 12, 13]
        lows = [9, 10, 11]
        closes = [10, 11, 12]
        result = indicators.calc_atr(highs, lows, closes, 14)
        assert result is None


class TestZScore:
    """Z-Score 计算测试"""
    
    def test_z_score_basic(self):
        """基本 z-score 计算"""
        result = indicators.calc_z_score(30, 20, 5)
        assert result == 2.0  # (30 - 20) / 5
    
    def test_z_score_negative(self):
        """负 z-score"""
        result = indicators.calc_z_score(10, 20, 5)
        assert result == -2.0
    
    def test_z_score_zero_std(self):
        """标准差为 0"""
        result = indicators.calc_z_score(30, 20, 0)
        assert result is None


class TestReturn:
    """收益率计算测试"""
    
    def test_return_positive(self):
        """正收益"""
        result = indicators.calc_return(110, 100)
        assert result == 0.1  # 10% 涨幅
    
    def test_return_negative(self):
        """负收益"""
        result = indicators.calc_return(90, 100)
        assert result == -0.1  # 10% 跌幅
    
    def test_return_zero_previous(self):
        """前值为 0"""
        result = indicators.calc_return(100, 0)
        assert result is None
    
    def test_return_none_values(self):
        """None 值"""
        assert indicators.calc_return(None, 100) is None
        assert indicators.calc_return(100, None) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
