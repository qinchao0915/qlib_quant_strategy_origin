#!/usr/bin/env python3
"""
数据获取模块
Tushare数据获取器
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
import sys

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.utils.logger import logger


class DataFetcher:
    """Tushare数据获取器"""

    def __init__(self, token, cache_path="./data/cache"):
        self.token = token
        self.cache_dir = Path(cache_path)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            import tushare as ts
            self.pro = ts.pro_api(token)
        except ImportError:
            logger.error("请先安装tushare: pip install tushare")
            raise

    def get_stock_list(self, market="csi500"):
        """获取股票列表"""
        cache_file = self.cache_dir / f"stock_list_{market}.pkl"

        if cache_file.exists():
            logger.info(f"从缓存加载{market}股票列表")
            return pd.read_pickle(cache_file)

        logger.info(f"获取{market}股票列表...")

        if market == "csi300":
            code = "000300.SH"
        elif market == "csi500":
            code = "000905.SH"
        elif market == "csi1000":
            code = "000852.SH"
        else:
            raise ValueError(f"不支持的市场: {market}")

        df = self.pro.index_weight(
            index_code=code,
            start_date="20230101",
            end_date=datetime.now().strftime("%Y%m%d")
        )
        stocks = df['con_code'].unique().tolist()
        pd.to_pickle(stocks, cache_file)
        logger.info(f"获取到 {len(stocks)} 只股票")
        return stocks

    def get_daily_price(self, ts_code, start_date, end_date):
        """获取日线行情"""
        cache_file = self.cache_dir / f"daily_{ts_code}_{start_date}_{end_date}.pkl"

        if cache_file.exists():
            return pd.read_pickle(cache_file)

        start = start_date.replace("-", "")
        end = end_date.replace("-", "")

        try:
            df = self.pro.daily(ts_code=ts_code, start_date=start, end_date=end)
            if df.empty:
                return pd.DataFrame()

            adj_df = self.pro.adj_factor(ts_code=ts_code, start_date=start, end_date=end)
            if not adj_df.empty:
                df = df.merge(adj_df[['trade_date', 'adj_factor']], on='trade_date', how='left')
                for col in ['open', 'high', 'low', 'close']:
                    df[col] = df[col] * df['adj_factor'] / df['adj_factor'].iloc[-1]

            df['trade_date'] = pd.to_datetime(df['trade_date'])
            df = df.sort_values('trade_date')
            df.to_pickle(cache_file)
            return df
        except Exception as e:
            logger.error(f"获取{ts_code}数据失败: {e}")
            return pd.DataFrame()

    def get_daily_prices_batch(self, stocks, start_date, end_date):
        """批量获取日线数据"""
        all_data = []
        total = len(stocks)

        for i, code in enumerate(stocks, 1):
            if i % 10 == 0:
                logger.info(f"进度: {i}/{total} ({i/total*100:.1f}%)")

            df = self.get_daily_price(code, start_date, end_date)
            if not df.empty:
                df['symbol'] = code.replace('.SH', '').replace('.SZ', '')
                all_data.append(df)

        if not all_data:
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)

        # 列名映射
        column_mapping = {
            'trade_date': 'date',
            'vol': 'volume',
        }
        result.rename(columns=column_mapping, inplace=True)
        result['date'] = pd.to_datetime(result['date'])

        return result[['date', 'symbol', 'open', 'high', 'low', 'close', 'volume', 'amount']]

    def load_data_extended(self, start_date, end_date, market='csi500'):
        """加载扩展股票池数据"""
        stocks = self.get_stock_list(market)
        logger.info(f"加载{market}的{len(stocks)}只股票数据...")

        # 计算数据加载起始日期（需要额外90天用于计算特征）
        load_start = (pd.to_datetime(start_date) - pd.Timedelta(days=90)).strftime('%Y-%m-%d')
        price_df = self.get_daily_prices_batch(stocks, load_start, end_date)

        # 获取市场数据
        try:
            market_start = load_start.replace('-', '')
            market_end = end_date.replace('-', '')

            # 沪深300作为市场指标
            market_df = self.pro.index_daily(ts_code='399300.SZ', start_date=market_start, end_date=market_end)
            market_df['date'] = pd.to_datetime(market_df['trade_date'])
            market_df = market_df[['date', 'close', 'open']].sort_values('date')
            market_df['symbol'] = 'MARKET'
            price_df = pd.concat([price_df, market_df], ignore_index=True)

            # 上证指数
            sh_df = self.pro.index_daily(ts_code='000001.SH', start_date=market_start, end_date=market_end)
            sh_df['date'] = pd.to_datetime(sh_df['trade_date'])
            sh_df = sh_df[['date', 'close', 'open']].sort_values('date')
            sh_df['symbol'] = 'SHINDEX'
            price_df = pd.concat([price_df, sh_df], ignore_index=True)
        except Exception as e:
            logger.warning(f"无法获取大盘数据: {e}")

        # 获取股票信息
        try:
            stock_info = self.pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,industry')
            stock_info['symbol'] = stock_info['ts_code'].str.replace('.SH', '').str.replace('.SZ', '')
            stock_names = dict(zip(stock_info['symbol'], stock_info['name']))
            stock_industries = dict(zip(stock_info['symbol'], stock_info['industry']))
            stock_tscodes = dict(zip(stock_info['symbol'], stock_info['ts_code']))

            for s in stocks:
                clean_s = s.replace('.SH', '').replace('.SZ', '')
                if clean_s not in stock_industries:
                    stock_industries[clean_s] = '其他'
                if clean_s not in stock_names:
                    stock_names[clean_s] = clean_s
                if clean_s not in stock_tscodes:
                    stock_tscodes[clean_s] = s

            stock_names['MARKET'] = '沪深300'
            stock_industries['MARKET'] = '大盘指数'
            stock_tscodes['MARKET'] = '399300.SZ'
            stock_names['SHINDEX'] = '上证指数'
            stock_industries['SHINDEX'] = '大盘指数'
            stock_tscodes['SHINDEX'] = '000001.SH'
        except Exception as e:
            logger.warning(f"无法获取股票信息: {e}")
            stock_names = {s.replace('.SH', '').replace('.SZ', ''): s.replace('.SH', '').replace('.SZ', '') for s in stocks}
            stock_industries = {s.replace('.SH', '').replace('.SZ', ''): '其他' for s in stocks}
            stock_tscodes = {s.replace('.SH', '').replace('.SZ', ''): s for s in stocks}

        return price_df, stock_names, stock_industries, stock_tscodes
