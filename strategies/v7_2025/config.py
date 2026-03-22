"""
v7_2025 策略配置
"""
from pathlib import Path

# 策略元信息
STRATEGY_INFO = {
    'name': 'v7_2025',
    'version': '7.0',
    'description': '集成学习多因子量化策略',
    'feature_count': 53,
}

# 风控配置
RISK_CONFIG = {
    'account': 200000,                # 初始资金
    'max_positions': 30,              # 最大持仓数
    'max_position_per_stock': 0.10,   # 单只股票最大仓位
    'max_position_per_industry': 0.30,  # 单行业最大仓位
}

# 三状态动态参数
PARAMS = {
    'BULL': {
        'top_n': 0.05,
        'min_holding_days': 18,
        'rank_exit_threshold': 0.35,
        'trailing_stop': 0.18,
        'max_daily_return': 0.09,
        'max_ma5_deviation': 0.08,
        'pos_ratio': 1.0,
    },
    'CHOPPY': {
        'top_n': 0.04,
        'min_holding_days': 12,
        'rank_exit_threshold': 0.25,
        'trailing_stop': 0.12,
        'max_daily_return': 0.06,
        'max_ma5_deviation': 0.05,
        'pos_ratio': 0.6,
    },
    'BEAR': {
        'top_n': 0.03,
        'min_holding_days': 8,
        'rank_exit_threshold': 0.20,
        'trailing_stop': 0.10,
        'max_daily_return': 0.04,
        'max_ma5_deviation': 0.03,
        'pos_ratio': 0.2,
    }
}

# 交易成本
SCENARIOS = {
    'normal': {
        'buy_cost': 0.0003,
        'sell_cost': 0.0013,
    }
}

# 硬性止损
HARD_STOP_LOSS = -0.10

# 模型配置
MODEL_CONFIG = {
    'csi500': {
        'model_file': 'model_enhanced_v7_csi500.pkl',
    },
    'csi300': {
        'model_file': 'model_enhanced_v7_csi300.pkl',
    },
    'csi1000': {
        'model_file': 'model_enhanced_v7_csi1000.pkl',
    }
}
