#!/usr/bin/env python3
"""
文件操作工具模块
"""

from pathlib import Path


def ensure_dir(path):
    """确保目录存在"""
    Path(path).mkdir(parents=True, exist_ok=True)
