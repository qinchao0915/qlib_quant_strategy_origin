#!/usr/bin/env python3
"""
全局配置模块
集中管理所有配置参数
"""

import os
from pathlib import Path

# API 配置
TUSHARE_TOKEN = os.getenv('TUSHARE_TOKEN', '')

# 路径配置
BASE_DIR = Path(__file__).parent.parent
CACHE_PATH = BASE_DIR / 'data' / 'cache'
MODEL_DIR = BASE_DIR / 'models'
RESULTS_DIR = BASE_DIR / 'results'

# 风控配置
RISK_CONFIG = {
    'max_positions': 30,              # 最大持仓数
    'max_position_per_stock': 0.20,   # 单只股票最大仓位
    'max_position_per_industry': 0.30,  # 单行业最大仓位
    'hard_stop_loss': -0.08,          # 硬性止损
    'trailing_stop': 0.10,            # 移动止损回撤比例
}

# 市场状态参数
PARAMS = {
    'BULL': {
        'min_holding_days': 5,
        'rank_exit_threshold': 0.15,
        'max_daily_return': 0.10,
        'max_ma5_deviation': 0.05,
    },
    'BEAR': {
        'min_holding_days': 3,
        'rank_exit_threshold': 0.10,
        'max_daily_return': 0.05,
        'max_ma5_deviation': 0.03,
    },
    'OSCILLATION': {
        'min_holding_days': 4,
        'rank_exit_threshold': 0.12,
        'max_daily_return': 0.08,
        'max_ma5_deviation': 0.04,
    }
}

# 交易成本配置
SCENARIOS = {
    'normal': {
        'buy_cost': 0.0013,   # 买入成本（滑点+手续费）
        'sell_cost': 0.0013,  # 卖出成本
    },
    'high_volatility': {
        'buy_cost': 0.0020,
        'sell_cost': 0.0020,
    }
}

# 模型配置
MODEL_CONFIG = {
    'csi500': {
        'model_file': 'model_enhanced_v7_csi500.pkl',
        'stock_list_file': 'stock_list_csi500.pkl',
    },
    'csi300': {
        'model_file': 'model_enhanced_v7_csi300.pkl',
        'stock_list_file': 'stock_list_csi300.pkl',
    },
    'csi1000': {
        'model_file': 'model_enhanced_v7_csi1000.pkl',
        'stock_list_file': 'stock_list_csi1000.pkl',
    }
}


def load_env_file(env_path='./api_keys/.env'):
    """加载 .env 配置文件"""
    env_file = Path(env_path)
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value
        return True
    return False


# 初始化时尝试加载环境变量
load_env_file()
if not TUSHARE_TOKEN:
    TUSHARE_TOKEN = os.getenv('TUSHARE_TOKEN', '')
