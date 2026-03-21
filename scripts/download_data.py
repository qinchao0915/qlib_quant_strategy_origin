#!/usr/bin/env python3
"""
数据下载脚本

下载 walk-forward 训练所需的完整数据：
- 训练窗口：2016-2024（用于训练模型）
- 测试窗口：2020-2025（用于回测评估）
- 数据范围：2015-10 到 2025-12（考虑特征计算需要前置 90 天）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import TUSHARE_TOKEN, CACHE_PATH
from core.data.fetcher import DataFetcher
from core.utils.logger import logger


def main():
    """主函数"""
    logger.info("=" * 70)
    logger.info("Walk-Forward 数据下载")
    logger.info("=" * 70)

    # 数据范围：2015-10 到 2025-12
    # 2015-10 开始是为了满足 2016-01 开始的特征计算需要（需要 90 天前置数据）
    start_date = "2015-10-01"
    end_date = "2025-12-31"

    fetcher = DataFetcher(TUSHARE_TOKEN, str(CACHE_PATH))

    # 需要下载的股票池
    pools = [
        ("csi300", "沪深 300"),
        ("csi500", "中证 500"),
        ("csi1000", "中证 1000"),
    ]

    for pool_code, pool_name in pools:
        logger.info(f"\n开始下载 {pool_name} ({pool_code}) 数据...")
        logger.info(f"数据范围：{start_date} 到 {end_date}")

        try:
            # 这会下载股票列表和所有股票的日线数据
            price_df, stock_names, stock_industries, stock_tscodes = \
                fetcher.load_data_extended(start_date, end_date, pool_code)

            logger.info(f"  下载完成:")
            logger.info(f"    - 股票数量：{len(stock_names) - 2}")  # 减去 MARKET 和 SHINDEX
            logger.info(f"    - 价格记录数：{len(price_df)}")
            logger.info(f"    - 日期范围：{price_df['date'].min()} 到 {price_df['date'].max()}")

        except Exception as e:
            logger.error(f"下载 {pool_name} 数据失败：{e}")
            continue

    logger.info("\n" + "=" * 70)
    logger.info("数据下载完成!")
    logger.info(f"缓存目录：{CACHE_PATH}")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
