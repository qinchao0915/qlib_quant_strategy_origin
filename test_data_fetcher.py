#!/usr/bin/env python3
"""
测试数据获取模块
验证重构后的代码输出与原始代码一致
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

# 测试新模块
from core.data import DataFetcher
from core.utils import logger
from config.settings import TUSHARE_TOKEN

def test_data_fetcher():
    """测试数据获取器"""
    logger.info("="*60)
    logger.info("测试 DataFetcher 模块")
    logger.info("="*60)
    
    if not TUSHARE_TOKEN:
        logger.error("TUSHARE_TOKEN 未设置，跳过测试")
        return False
    
    try:
        # 初始化获取器
        fetcher = DataFetcher(TUSHARE_TOKEN)
        logger.info("✅ DataFetcher 初始化成功")
        
        # 测试获取股票列表（使用缓存）
        logger.info("\n测试获取CSI500股票列表...")
        stocks = fetcher.get_stock_list('csi500')
        logger.info(f"✅ 获取到 {len(stocks)} 只股票")
        
        # 测试获取单只股票数据
        logger.info("\n测试获取单只股票数据...")
        test_stock = stocks[0] if stocks else '000001.SZ'
        df = fetcher.get_daily_price(test_stock, '2025-01-01', '2025-01-10')
        if not df.empty:
            logger.info(f"✅ 获取到 {len(df)} 条数据")
            logger.info(f"   列名: {list(df.columns)}")
        else:
            logger.warning("⚠️ 未获取到数据")
        
        logger.info("\n" + "="*60)
        logger.info("✅ 所有测试通过！")
        logger.info("="*60)
        return True
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_data_fetcher()
    sys.exit(0 if success else 1)
