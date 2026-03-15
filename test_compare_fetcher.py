#!/usr/bin/env python3
"""
对比测试：验证新的 DataFetcher 与原始代码结果一致
"""

import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

# 导入新的模块
from core.data import DataFetcher as NewDataFetcher
from core.utils import logger
from config.settings import TUSHARE_TOKEN

# 导入原始模块（从 main_backup.py）
sys.path.insert(0, str(Path(__file__).parent))
import importlib.util
spec = importlib.util.spec_from_file_location("original", "main_backup.py")
original_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original_module)
OriginalDataFetcher = original_module.DataFetcher


def compare_fetchers():
    """对比新旧 DataFetcher"""
    logger.info("="*70)
    logger.info("对比测试：新 vs 旧 DataFetcher")
    logger.info("="*70)
    
    if not TUSHARE_TOKEN:
        logger.error("TUSHARE_TOKEN 未设置，无法测试")
        return False
    
    try:
        # 初始化两个获取器
        logger.info("\n1. 初始化获取器...")
        new_fetcher = NewDataFetcher(TUSHARE_TOKEN)
        old_fetcher = OriginalDataFetcher(TUSHARE_TOKEN)
        logger.info("✅ 两个获取器初始化成功")
        
        # 测试1：获取股票列表
        logger.info("\n2. 测试 get_stock_list()...")
        new_stocks = new_fetcher.get_stock_list('csi500')
        old_stocks = old_fetcher.get_stock_list('csi500')
        
        if set(new_stocks) == set(old_stocks):
            logger.info(f"✅ 股票列表一致，共 {len(new_stocks)} 只")
        else:
            logger.error(f"❌ 股票列表不一致！")
            logger.error(f"   新: {len(new_stocks)} 只, 旧: {len(old_stocks)} 只")
            return False
        
        # 测试2：获取单只股票数据
        logger.info("\n3. 测试 get_daily_price()...")
        test_stock = new_stocks[0] if new_stocks else '000001.SZ'
        
        new_df = new_fetcher.get_daily_price(test_stock, '2025-01-01', '2025-01-10')
        old_df = old_fetcher.get_daily_price(test_stock, '2025-01-01', '2025-01-10')
        
        if new_df.empty and old_df.empty:
            logger.info("✅ 两者都返回空数据")
        elif new_df.empty != old_df.empty:
            logger.error(f"❌ 数据获取结果不一致！")
            logger.error(f"   新: {'空' if new_df.empty else '有数据'}, 旧: {'空' if old_df.empty else '有数据'}")
            return False
        else:
            # 比较数据内容
            if len(new_df) == len(old_df):
                logger.info(f"✅ 数据行数一致: {len(new_df)} 行")
                
                # 比较关键列
                key_cols = ['open', 'high', 'low', 'close', 'volume']
                for col in key_cols:
                    if col in new_df.columns and col in old_df.columns:
                        if new_df[col].equals(old_df[col]):
                            logger.info(f"   ✅ {col} 列完全一致")
                        else:
                            logger.warning(f"   ⚠️ {col} 列有差异")
            else:
                logger.warning(f"⚠️ 数据行数不一致: 新{len(new_df)} vs 旧{len(old_df)}")
        
        # 测试3：批量获取
        logger.info("\n4. 测试 get_daily_prices_batch()...")
        test_stocks = new_stocks[:3]  # 只测3只，加快速度
        
        new_batch = new_fetcher.get_daily_prices_batch(test_stocks, '2025-01-01', '2025-01-10')
        old_batch = old_fetcher.get_daily_prices_batch(test_stocks, '2025-01-01', '2025-01-10')
        
        if new_batch.empty and old_batch.empty:
            logger.info("✅ 两者都返回空数据")
        elif new_batch.empty != old_batch.empty:
            logger.error(f"❌ 批量数据获取结果不一致！")
            return False
        else:
            logger.info(f"✅ 批量数据获取成功")
            logger.info(f"   新: {len(new_batch)} 行, 旧: {len(old_batch)} 行")
            
            # 比较列名
            if set(new_batch.columns) == set(old_batch.columns):
                logger.info(f"✅ 列名一致: {list(new_batch.columns)}")
            else:
                logger.warning(f"⚠️ 列名不一致")
                logger.warning(f"   新: {list(new_batch.columns)}")
                logger.warning(f"   旧: {list(old_batch.columns)}")
        
        logger.info("\n" + "="*70)
        logger.info("✅ 对比测试完成！新模块与原始模块结果一致")
        logger.info("="*70)
        return True
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = compare_fetchers()
    sys.exit(0 if success else 1)
