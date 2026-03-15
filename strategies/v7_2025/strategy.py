#!/usr/bin/env python3
"""
v7_2025 策略实现

继承 BaseStrategy，实现具体的交易逻辑
"""
import sys
from pathlib import Path
from typing import Tuple, Dict, Any
from datetime import datetime
import pickle

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from strategies.base import BaseStrategy
from core.features.engineering import FeatureEngineer
from core.utils.logger import logger

from . import config


class V7Strategy(BaseStrategy):
    """
    v7.0 量化策略实现

    特点：
    - 集成学习（LightGBM + XGBoost）
    - 三状态市场 regime 自适应
    - 多层次风控体系
    """

    def __init__(self):
        super().__init__()
        self.name = 'v7_2025'
        self.feature_engineer = FeatureEngineer()
        self._models_loaded = False

    def load_models(self, pool_type: str) -> Tuple[Dict, Dict, list]:
        """加载模型"""
        if self._models_loaded:
            return self.models, self.weights, self.feature_cols

        model_file = config.MODEL_CONFIG.get(pool_type, {}).get('model_file')
        if not model_file:
            raise ValueError(f"不支持的模型类型: {pool_type}")

        model_path = Path('models') / model_file
        logger.info(f"加载v7模型: {model_path}")

        if not model_path.exists():
            raise FileNotFoundError(f"模型文件不存在: {model_path}")

        with open(model_path, 'rb') as f:
            data = pickle.load(f)

        self.models = data['models']
        self.weights = data['weights']
        self.feature_cols = data['features']
        self._models_loaded = True

        logger.info(f"  特征数: {len(self.feature_cols)}")
        logger.info(f"  模型权重: {self.weights}")
        logger.info(f"  集成IC: {data['ensemble_ic']:.4f}")

        return self.models, self.weights, self.feature_cols

    def generate_signals(self, price_df: pd.DataFrame) -> pd.DataFrame:
        """生成交易信号"""
        # 计算特征
        df = self.feature_engineer.calculate_features(price_df)
        df = df.dropna(subset=self.feature_cols)

        # 预测
        df['pred'], _ = self._predict_ensemble(df)
        df['pred_rank'] = df.groupby('date')['pred'].rank(ascending=False, pct=True)

        return df

    def _predict_ensemble(self, df: pd.DataFrame) -> Tuple[np.ndarray, Dict]:
        """集成预测"""
        predictions = {}
        for name, model in self.models.items():
            if hasattr(model, 'booster_'):
                predictions[name] = model.booster_.predict(df[self.feature_cols].values)
            else:
                predictions[name] = model.predict(df[self.feature_cols])

        ensemble_pred = np.zeros(len(df))
        for name, weight in self.weights.items():
            ensemble_pred += weight * predictions[name]

        return ensemble_pred, predictions

    def should_buy(self, row: pd.Series, regime: str,
                   industry_exposure: Dict, portfolio_value: float,
                   current_positions: int, cash: float) -> Tuple[bool, str]:
        """买入判断"""
        cfg = config.PARAMS[regime]

        # 检查日涨幅限制
        if row.get('return_1d', 0) > cfg['max_daily_return']:
            return False, '日涨幅超限'

        # 检查均线偏离
        if row.get('deviation_from_ma5', 0) > cfg['max_ma5_deviation']:
            return False, '均线偏离过大'

        # 检查行业集中度
        ind = row.get('industry', '其他')
        if industry_exposure.get(ind, 0) >= config.RISK_CONFIG['max_position_per_industry']:
            return False, '行业集中度超限'

        # 检查排名
        if row['pred_rank'] > cfg['top_n']:
            return False, '排名不在前N'

        return True, '符合条件'

    def should_sell(self, pos: Dict, current_price: float,
                    days: int, regime: str, day_data: pd.DataFrame) -> Tuple[bool, str, float]:
        """卖出判断"""
        cfg = config.PARAMS[regime]
        pnl = (current_price - pos['cost']) / pos['cost']

        # 更新最高价格
        highest_price = max(pos.get('highest_price', pos['cost']), current_price)
        highest_pnl = max(pos.get('highest_pnl', 0), pnl)

        # Hard Stop
        if pnl <= config.HARD_STOP_LOSS:
            return True, f"{regime} Hard stop ({pnl:.1%})", pnl

        # Trailing Stop
        if current_price < highest_price * (1 - cfg['trailing_stop']):
            pullback = (highest_price - current_price) / highest_price
            return True, f"{regime} trailing stop ({pullback * 100:.1f}%)", pnl

        # Rank Exit
        if days >= cfg['min_holding_days'] and highest_pnl <= 0.20:
            symbol = pos.get('symbol', '')
            current_rank = day_data[day_data['symbol'] == symbol]['pred_rank'].values
            if len(current_rank) > 0 and current_rank[0] > cfg['rank_exit_threshold']:
                return True, f"{regime} rank exit ({current_rank[0] * 100:.1f}%)", pnl

        return False, None, pnl

    def calculate_position_size(self, cash: float, slots: int,
                                portfolio_value: float, price: float,
                                max_per_stock: float) -> int:
        """计算仓位"""
        max_position_value = portfolio_value * max_per_stock
        planned = min(cash * 0.95 / max(slots, 1), max_position_value)
        shares = int(planned / price / 100) * 100
        return shares

    def detect_market_regime(self, price_df: pd.DataFrame,
                             date: datetime) -> str:
        """检测市场状态"""
        market_data = price_df[(price_df['symbol'] == 'MARKET') &
                               (price_df['date'] <= date)].copy()
        if len(market_data) < 60:
            return 'CHOPPY'

        market_data = market_data.sort_values('date')
        ma20 = market_data['close'].iloc[-20:].mean()
        ma60 = market_data['close'].iloc[-60:].mean()

        if ma20 > ma60:
            return 'BULL'
        elif ma20 < ma60:
            return 'BEAR'
        else:
            return 'CHOPPY'

    def get_config(self) -> Dict[str, Any]:
        """获取配置"""
        return {
            'risk': config.RISK_CONFIG,
            'params': config.PARAMS,
            'scenarios': config.SCENARIOS,
            'hard_stop_loss': config.HARD_STOP_LOSS,
        }
