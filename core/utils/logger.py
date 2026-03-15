#!/usr/bin/env python3
"""
日志工具模块
统一日志配置
"""

import logging
import sys


def setup_logger(name='quant', level=logging.INFO):
    """
    设置日志配置
    
    Args:
        name: 日志名称
        level: 日志级别
        
    Returns:
        logger: 配置好的日志对象
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 避免重复添加handler
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


# 默认日志对象
logger = setup_logger()
