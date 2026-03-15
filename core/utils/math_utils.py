#!/usr/bin/env python3
"""
数学计算工具模块
"""

import numpy as np
from scipy.stats import spearmanr


def calculate_return(start_value, end_value):
    """计算收益率"""
    if start_value == 0:
        return 0
    return (end_value - start_value) / start_value


def calculate_ic(y_true, y_pred):
    """计算IC（Pearson相关系数）"""
    m = ~(np.isnan(y_true) | np.isnan(y_pred))
    if m.sum() < 10:
        return 0
    return np.corrcoef(y_true[m], y_pred[m])[0, 1]


def calculate_rank_ic(y_true, y_pred):
    """计算Rank IC（Spearman秩相关系数）"""
    m = ~(np.isnan(y_true) | np.isnan(y_pred))
    if m.sum() < 10:
        return 0
    corr, _ = spearmanr(y_true[m], y_pred[m])
    return corr
