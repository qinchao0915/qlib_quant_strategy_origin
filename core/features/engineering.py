#!/usr/bin/env python3
"""
特征工程模块
计算v7增强版特征 (53个特征)
"""

import numpy as np
import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.utils import logger


class FeatureEngineer:
    """特征工程类"""
    
    def __init__(self):
        self.feature_cols = None
    
    def calculate_features(self, price_df):
        """
        计算v7增强版特征 (53个特征)
        
        Args:
            price_df: 价格数据DataFrame
            
        Returns:
            DataFrame: 带特征的数据
        """
        logger.info("🔧 开始计算特征...")
        results = []
        total = price_df['symbol'].nunique()
        
        for i, (symbol, group) in enumerate(price_df.groupby('symbol')):
            if i % 100 == 0:
                logger.info(f"  进度: {i}/{total} ({i/total*100:.1f}%)")
            
            group = group.sort_values('date').copy()
            group = self._calculate_price_momentum(group)
            group = self._calculate_volatility(group)
            group = self._calculate_moving_average(group)
            group = self._calculate_bollinger(group)
            group = self._calculate_rsi(group)
            group = self._calculate_macd(group)
            group = self._calculate_volume(group)
            group = self._calculate_amplitude(group)
            group = self._calculate_money_flow(group)
            group = self._calculate_market_cap(group)
            group = self._calculate_label(group)
            
            results.append(group)
        
        df = pd.concat(results, ignore_index=True)
        df['date'] = pd.to_datetime(df['date'])
        df = df[~df['symbol'].isin(['MARKET', 'SHINDEX'])]
        
        logger.info(f"✅ 特征计算完成！共 {len(self.get_feature_cols())} 个特征")
        return df
    
    def _calculate_price_momentum(self, group):
        """价格动量因子 (8个)"""
        for window in [1, 3, 5, 10, 20, 60]:
            group[f'return_{window}d'] = group['close'] / group['close'].shift(window) - 1
        group['return_accel'] = group['return_5d'] - group['return_20d']
        group['intraday_momentum'] = (group['close'] - group['open']) / group['open']
        return group
    
    def _calculate_volatility(self, group):
        """波动率因子 (6个)"""
        for window in [5, 10, 20, 60]:
            group[f'volatility_{window}d'] = group['close'].pct_change().rolling(window).std() * np.sqrt(252)
        group['vol_trend'] = group['volatility_20d'] / (group['volatility_60d'] + 1e-10) - 1
        group['realized_vol_5d'] = np.sqrt((group['close'].pct_change()**2).rolling(5).sum())
        return group
    
    def _calculate_moving_average(self, group):
        """均线因子 (8个)"""
        for window in [5, 10, 20, 30, 60, 120]:
            group[f'ma_{window}'] = group['close'].rolling(window).mean()
        group['price_to_ma20'] = group['close'] / group['ma_20'] - 1
        group['ma5_to_ma20'] = group['ma_5'] / group['ma_20'] - 1
        group['ma20_to_ma60'] = group['ma_20'] / group['ma_60'] - 1
        group['trend_up'] = (group['close'] > group['ma_20']).astype(int)
        group['golden_cross'] = ((group['ma_5'] > group['ma_20']) &
                                 (group['ma_5'].shift(1) <= group['ma_20'].shift(1))).astype(int)
        return group
    
    def _calculate_bollinger(self, group):
        """布林带 (5个)"""
        group['std_20'] = group['close'].rolling(20).std()
        group['bollinger_upper'] = group['ma_20'] + 2 * group['std_20']
        group['bollinger_lower'] = group['ma_20'] - 2 * group['std_20']
        group['bollinger_pos'] = (group['close'] - group['bollinger_lower']) / (group['bollinger_upper'] - group['bollinger_lower'] + 1e-10)
        group['bollinger_width'] = (group['bollinger_upper'] - group['bollinger_lower']) / group['ma_20']
        group['bollinger_squeeze'] = (group['bollinger_width'] < group['bollinger_width'].rolling(20).mean() * 0.8).astype(int)
        return group
    
    def _calculate_rsi(self, group):
        """RSI (4个)"""
        delta = group['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / (loss + 1e-10)
        group['rsi'] = 100 - (100 / (1 + rs))
        group['rsi_overbought'] = (group['rsi'] > 70).astype(int)
        group['rsi_oversold'] = (group['rsi'] < 30).astype(int)
        group['rsi_ma'] = group['rsi'].rolling(5).mean()
        group['price_ma'] = group['close'].rolling(5).mean()
        group['rsi_divergence'] = ((group['close'] > group['price_ma']) &
                                   (group['rsi'] < group['rsi_ma'])).astype(int)
        return group
    
    def _calculate_macd(self, group):
        """MACD (5个)"""
        ema_12 = group['close'].ewm(span=12).mean()
        ema_26 = group['close'].ewm(span=26).mean()
        group['macd'] = ema_12 - ema_26
        group['macd_signal'] = group['macd'].ewm(span=9).mean()
        group['macd_long'] = (group['macd'] > group['macd_signal']).astype(int)
        group['macd_hist'] = group['macd'] - group['macd_signal']
        group['macd_cross'] = ((group['macd'] > group['macd_signal']) &
                               (group['macd'].shift(1) <= group['macd_signal'].shift(1))).astype(int)
        return group
    
    def _calculate_volume(self, group):
        """成交量因子 (8个)"""
        for window in [5, 10, 20]:
            group[f'volume_ma{window}'] = group['volume'].rolling(window).mean()
        group['volume_ratio_5_20'] = group['volume_ma5'] / group['volume_ma20']
        group['volume_ratio'] = group['volume'] / group['volume_ma20'].shift(1)
        group['volume_trend'] = group['volume_ma5'] / group['volume_ma20'] - 1
        group['volume_breakout'] = (group['volume'] > group['volume_ma20'] * 2).astype(int)
        
        group['price_change'] = group['close'].diff()
        group['obv'] = (np.sign(group['price_change']) * group['volume']).cumsum()
        group['obv_ma'] = group['obv'].rolling(20).mean()
        
        price_change = group['close'].pct_change()
        volume_change = group['volume'].pct_change()
        group['price_volume_corr'] = price_change.rolling(20).corr(volume_change)
        group['volume_price_trend'] = ((group['volume'] > group['volume_ma20']) &
                                       (group['close'] > group['ma_20'])).astype(int)
        return group
    
    def _calculate_amplitude(self, group):
        """振幅因子 (5个)"""
        group['high_low_pct'] = (group['high'] - group['low']) / group['close']
        group['gap'] = (group['open'] - group['close'].shift(1)) / group['close'].shift(1)
        group['amplitude_20d'] = group['high_low_pct'].rolling(20).mean()
        group['upper_shadow'] = (group['high'] - group[['close', 'open']].max(axis=1)) / group['close']
        group['lower_shadow'] = (group[['close', 'open']].min(axis=1) - group['low']) / group['close']
        return group
    
    def _calculate_money_flow(self, group):
        """资金流因子 (5个)"""
        typical_price = (group['high'] + group['low'] + group['close']) / 3
        raw_money_flow = typical_price * group['volume']
        positive_flow = raw_money_flow.where(typical_price > typical_price.shift(1), 0)
        negative_flow = raw_money_flow.where(typical_price < typical_price.shift(1), 0)
        positive_sum = positive_flow.rolling(14).sum()
        negative_sum = negative_flow.rolling(14).sum()
        money_ratio = positive_sum / (negative_sum + 1e-10)
        group['mfi'] = 100 - (100 / (1 + money_ratio))
        
        group['turnover'] = group['close'] * group['volume']
        group['turnover_ma5'] = group['turnover'].rolling(5).mean()
        group['turnover_ma20'] = group['turnover'].rolling(20).mean()
        group['turnover_ratio'] = group['turnover'] / group['turnover_ma20']
        
        group['money_inflow'] = (group['close'] > group['open']) * group['turnover']
        group['money_outflow'] = (group['close'] <= group['open']) * group['turnover']
        group['net_money_flow'] = (group['money_inflow'].rolling(5).sum() -
                                   group['money_outflow'].rolling(5).sum()) / group['turnover_ma5']
        
        group['big_money'] = (group['turnover'] > group['turnover_ma20'] * 1.5).astype(int)
        group['big_money_ratio'] = group['big_money'].rolling(5).sum() / 5
        return group
    
    def _calculate_market_cap(self, group):
        """市值因子 (3个)"""
        group['market_cap_proxy'] = group['close'] * group['volume_ma20']
        group['size_rank'] = group['market_cap_proxy'].rank(pct=True)
        group['price_level'] = group['close']
        group['is_low_price'] = (group['close'] < 10).astype(int)
        group['avg_turnover_20d'] = group['turnover'].rolling(20).mean()
        group['liquidity_score'] = group['avg_turnover_20d'] / group['avg_turnover_20d'].median()
        return group
    
    def _calculate_label(self, group):
        """标签：未来5日收益率"""
        group['label'] = group['close'].shift(-5) / group['close'] - 1
        return group
    
    def get_feature_cols(self):
        """获取v7特征列列表"""
        if self.feature_cols is None:
            self.feature_cols = [
                'return_1d', 'return_3d', 'return_5d', 'return_10d', 'return_20d', 'return_60d',
                'return_accel', 'intraday_momentum',
                'volatility_5d', 'volatility_10d', 'volatility_20d', 'volatility_60d',
                'vol_trend', 'realized_vol_5d',
                'ma_5', 'ma_10', 'ma_20', 'ma_30', 'ma_60', 'ma_120',
                'price_to_ma20', 'ma5_to_ma20', 'ma20_to_ma60', 'trend_up', 'golden_cross',
                'bollinger_upper', 'bollinger_lower', 'bollinger_pos', 'bollinger_width', 'bollinger_squeeze',
                'rsi', 'rsi_overbought', 'rsi_oversold', 'rsi_divergence',
                'macd', 'macd_signal', 'macd_long', 'macd_hist', 'macd_cross',
                'volume_ma5', 'volume_ma10', 'volume_ma20',
                'volume_ratio_5_20', 'volume_ratio', 'volume_trend', 'volume_breakout',
                'obv', 'obv_ma', 'price_volume_corr', 'volume_price_trend',
                'high_low_pct', 'gap', 'amplitude_20d', 'upper_shadow', 'lower_shadow',
                'mfi', 'turnover', 'turnover_ma5', 'turnover_ma20', 'turnover_ratio',
                'net_money_flow', 'big_money', 'big_money_ratio',
                'market_cap_proxy', 'size_rank', 'is_low_price', 'liquidity_score'
            ]
        return self.feature_cols


# 保持向后兼容的函数接口
def calculate_features(price_df):
    """计算特征的兼容函数"""
    engine = FeatureEngineer()
    return engine.calculate_features(price_df)


def get_feature_cols():
    """获取特征列的兼容函数"""
    engine = FeatureEngineer()
    return engine.get_feature_cols()