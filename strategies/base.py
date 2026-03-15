"""
策略基类模块
定义所有策略必须实现的接口
"""
from abc import ABC, abstractmethod
import pandas as pd
import numpy as np
from typing import Tuple, Dict, Any, Optional
from datetime import datetime


class BaseStrategy(ABC):
    """
    策略基类

    所有具体策略必须继承此类并实现所有抽象方法。
    主程序通过此接口与策略交互，无需关心具体实现细节。
    """

    def __init__(self):
        self.name = self.__class__.__name__
        self.models = {}
        self.weights = {}
        self.feature_cols = []

    @abstractmethod
    def load_models(self, pool_type: str) -> Tuple[Dict, Dict, list]:
        """
        加载模型

        Args:
            pool_type: 股票池类型 ('csi300', 'csi500', 'csi1000')

        Returns:
            models: 模型字典 {'model_name': model_object}
            weights: 权重字典 {'model_name': weight}
            feature_cols: 特征列列表
        """
        pass

    @abstractmethod
    def generate_signals(self, price_df: pd.DataFrame) -> pd.DataFrame:
        """
        生成交易信号

        Args:
            price_df: 价格数据DataFrame

        Returns:
            signals_df: 包含预测得分和排名的DataFrame
        """
        pass

    @abstractmethod
    def should_buy(self, row: pd.Series, regime: str,
                   industry_exposure: Dict, portfolio_value: float,
                   current_positions: int, cash: float) -> Tuple[bool, str]:
        """
        判断是否买入

        Args:
            row: 当前股票数据行
            regime: 市场状态
            industry_exposure: 当前行业敞口
            portfolio_value: 组合总价值
            current_positions: 当前持仓数量
            cash: 可用现金

        Returns:
            (是否买入, 原因)
        """
        pass

    @abstractmethod
    def should_sell(self, pos: Dict, current_price: float,
                    days: int, regime: str, day_data: pd.DataFrame) -> Tuple[bool, str, float]:
        """
        判断是否卖出

        Args:
            pos: 持仓信息字典
            current_price: 当前价格
            days: 持有天数
            regime: 市场状态
            day_data: 当日数据

        Returns:
            (是否卖出, 原因, 当前盈亏比例)
        """
        pass

    @abstractmethod
    def calculate_position_size(self, cash: float, slots: int,
                                portfolio_value: float, price: float,
                                max_per_stock: float) -> int:
        """
        计算买入股数

        Args:
            cash: 可用现金
            slots: 剩余持仓槽位
            portfolio_value: 组合价值
            price: 当前股价
            max_per_stock: 单只股票最大仓位比例

        Returns:
            shares: 买入股数（100的整数倍）
        """
        pass

    @abstractmethod
    def get_config(self) -> Dict[str, Any]:
        """
        获取策略配置

        Returns:
            config: 配置字典，包含风险参数、交易参数等
        """
        pass

    @abstractmethod
    def detect_market_regime(self, price_df: pd.DataFrame,
                             date: datetime) -> str:
        """
        检测市场状态

        Args:
            price_df: 价格数据
            date: 当前日期

        Returns:
            regime: 'BULL', 'CHOPPY', 或 'BEAR'
        """
        pass
