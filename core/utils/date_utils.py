#!/usr/bin/env python3
"""
日期工具模块
"""

from datetime import datetime, timedelta


def format_date(date_obj, fmt='%Y-%m-%d'):
    """格式化日期"""
    if isinstance(date_obj, str):
        return date_obj
    return date_obj.strftime(fmt)


def parse_date(date_str, fmt='%Y-%m-%d'):
    """解析日期字符串"""
    if isinstance(date_str, datetime):
        return date_str
    return datetime.strptime(date_str, fmt)


def get_date_range(start_date, end_date):
    """获取日期范围列表"""
    start = parse_date(start_date)
    end = parse_date(end_date)
    
    dates = []
    current = start
    while current <= end:
        dates.append(current)
        current += timedelta(days=1)
    
    return dates
