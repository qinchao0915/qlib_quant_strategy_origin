"""
策略注册表模块
管理所有可用策略的注册和加载
"""
import importlib
from typing import Dict, Type
from .base import BaseStrategy


# 策略注册表
# key: 策略标识名
# value: 模块路径
REGISTERED_STRATEGIES = {
    'v7_2025': 'strategies.v7_2025.V7Strategy',
}


def register_strategy(name: str, module_path: str):
    """
    注册新策略

    Args:
        name: 策略名称
        module_path: 策略类完整模块路径，如 'strategies.v7_2025.V7Strategy'
    """
    REGISTERED_STRATEGIES[name] = module_path


def load_strategy(name: str) -> BaseStrategy:
    """
    动态加载策略

    Args:
        name: 策略名称

    Returns:
        strategy: 策略实例

    Raises:
        ValueError: 策略不存在
        ImportError: 策略模块加载失败
    """
    if name not in REGISTERED_STRATEGIES:
        available = ', '.join(REGISTERED_STRATEGIES.keys())
        raise ValueError(f"策略 '{name}' 未注册。可用策略: {available}")

    module_path = REGISTERED_STRATEGIES[name]

    try:
        # 分割模块路径和类名
        module_name, class_name = module_path.rsplit('.', 1)

        # 动态导入模块
        module = importlib.import_module(module_name)

        # 获取策略类
        strategy_class = getattr(module, class_name)

        # 实例化策略
        strategy = strategy_class()

        return strategy

    except Exception as e:
        raise ImportError(f"加载策略 '{name}' 失败: {e}")


def list_strategies() -> Dict[str, str]:
    """
    列出所有可用策略

    Returns:
        策略名称和描述的映射
    """
    return REGISTERED_STRATEGIES.copy()


def unregister_strategy(name: str):
    """
    注销策略

    Args:
        name: 策略名称
    """
    if name in REGISTERED_STRATEGIES:
        del REGISTERED_STRATEGIES[name]
