#!/usr/bin/env python3
"""
Qlib量化策略 v7.0 主程序
功能：模型加载、数据获取、特征工程、预测、回测
"""

import sys
import pandas as pd
import numpy as np
import yaml
import pickle
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_env_file(env_path='./api_keys/.env'):
    """从 .env 文件加载环境变量"""
    env_vars = {}
    if Path(env_path).exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    else:
        logger.warning(f"未找到 {env_path} 文件，将使用示例配置")
    return env_vars


# 加载 API keys
_env = load_env_file()

# ============================================
# 配置
# ============================================
CONFIG = {
    'tushare_token': _env.get('TUSHARE_TOKEN', ''),
    'cache_path': './data/cache',
    'model_dir': './models',
    'results_dir': './results',
}

# 风控配置
RISK_CONFIG = {
    'account': 200000,
    'max_position_per_stock': 0.10,
    'max_position_per_industry': 0.30,
    'max_positions': 30,
}

# 三状态动态参数
PARAMS = {
    'BULL': {
        'top_n': 0.05, 'min_holding_days': 10, 'rank_exit_threshold': 0.40,
        'trailing_stop': 0.15, 'max_daily_return': 0.09, 'max_ma5_deviation': 0.08,
        'pos_ratio': 1.0,
    },
    'CHOPPY': {
        'top_n': 0.04, 'min_holding_days': 7, 'rank_exit_threshold': 0.30,
        'trailing_stop': 0.10, 'max_daily_return': 0.06, 'max_ma5_deviation': 0.05,
        'pos_ratio': 0.6,
    },
    'BEAR': {
        'top_n': 0.03, 'min_holding_days': 5, 'rank_exit_threshold': 0.20,
        'trailing_stop': 0.08, 'max_daily_return': 0.04, 'max_ma5_deviation': 0.03,
        'pos_ratio': 0.3,
    }
}

HARD_STOP_LOSS = -0.08
SCENARIOS = {'normal': {'buy_cost': 0.0003, 'sell_cost': 0.0013}}


# ============================================
# 数据获取模块
# ============================================
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


# ============================================
# 模型加载
# ============================================
def load_v7_model(pool_type='csi500'):
    """加载v7模型"""
    model_path = Path(CONFIG['model_dir']) / f"model_enhanced_v7_{pool_type}.pkl"
    logger.info(f"加载v7模型: {model_path}")

    if not model_path.exists():
        raise FileNotFoundError(f"模型文件不存在: {model_path}")

    with open(model_path, 'rb') as f:
        data = pickle.load(f)

    logger.info(f"  特征数: {len(data['features'])}")
    logger.info(f"  模型权重: {data['weights']}")
    logger.info(f"  集成IC: {data['ensemble_ic']:.4f}")

    return data['models'], data['weights'], data['features']


# ============================================
# 特征工程
# ============================================
def calculate_features(price_df):
    """计算v7增强版特征 (53个特征)"""
    results = []

    for symbol, group in price_df.groupby('symbol'):
        group = group.sort_values('date').copy()

        # ========== 价格动量因子 (8个) ==========
        for window in [1, 3, 5, 10, 20, 60]:
            group[f'return_{window}d'] = group['close'] / group['close'].shift(window) - 1
        group['return_accel'] = group['return_5d'] - group['return_20d']
        group['intraday_momentum'] = (group['close'] - group['open']) / group['open']

        # ========== 波动率因子 (6个) ==========
        for window in [5, 10, 20, 60]:
            group[f'volatility_{window}d'] = group['close'].pct_change().rolling(window).std() * np.sqrt(252)
        group['vol_trend'] = group['volatility_20d'] / (group['volatility_60d'] + 1e-10) - 1
        group['realized_vol_5d'] = np.sqrt((group['close'].pct_change()**2).rolling(5).sum())

        # ========== 均线因子 (8个) ==========
        for window in [5, 10, 20, 30, 60, 120]:
            group[f'ma_{window}'] = group['close'].rolling(window).mean()
        group['price_to_ma20'] = group['close'] / group['ma_20'] - 1
        group['ma5_to_ma20'] = group['ma_5'] / group['ma_20'] - 1
        group['ma20_to_ma60'] = group['ma_20'] / group['ma_60'] - 1
        group['trend_up'] = (group['close'] > group['ma_20']).astype(int)
        group['golden_cross'] = ((group['ma_5'] > group['ma_20']) &
                                 (group['ma_5'].shift(1) <= group['ma_20'].shift(1))).astype(int)

        # ========== 布林带 (3个) ==========
        group['std_20'] = group['close'].rolling(20).std()
        group['bollinger_upper'] = group['ma_20'] + 2 * group['std_20']
        group['bollinger_lower'] = group['ma_20'] - 2 * group['std_20']
        group['bollinger_pos'] = (group['close'] - group['bollinger_lower']) / (group['bollinger_upper'] - group['bollinger_lower'] + 1e-10)
        group['bollinger_width'] = (group['bollinger_upper'] - group['bollinger_lower']) / group['ma_20']
        group['bollinger_squeeze'] = (group['bollinger_width'] < group['bollinger_width'].rolling(20).mean() * 0.8).astype(int)

        # ========== RSI (4个) ==========
        delta = group['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / (loss + 1e-10)
        group['rsi'] = 100 - (100 / (1 + rs))
        group['rsi_overbought'] = (group['rsi'] > 70).astype(int)
        group['rsi_oversold'] = (group['rsi'] < 30).astype(int)
        group['rsi_ma'] = group['rsi'].rolling(5).mean()
        group['price_ma'] = group['close'].rolling(5).mean()
        group['rsi_divergence'] = ((group['close'] > group['price_ma']) &
                                   (group['rsi'] < group['rsi_ma'])).astype(int)

        # ========== MACD (5个) ==========
        ema_12 = group['close'].ewm(span=12).mean()
        ema_26 = group['close'].ewm(span=26).mean()
        group['macd'] = ema_12 - ema_26
        group['macd_signal'] = group['macd'].ewm(span=9).mean()
        group['macd_long'] = (group['macd'] > group['macd_signal']).astype(int)
        group['macd_hist'] = group['macd'] - group['macd_signal']
        group['macd_cross'] = ((group['macd'] > group['macd_signal']) &
                               (group['macd'].shift(1) <= group['macd_signal'].shift(1))).astype(int)

        # ========== 成交量因子 (8个) ==========
        for window in [5, 10, 20]:
            group[f'volume_ma{window}'] = group['volume'].rolling(window).mean()
        group['volume_ratio_5_20'] = group['volume_ma5'] / group['volume_ma20']
        group['volume_ratio'] = group['volume'] / group['volume_ma20'].shift(1)
        group['volume_trend'] = group['volume_ma5'] / group['volume_ma20'] - 1
        group['volume_breakout'] = (group['volume'] > group['volume_ma20'] * 2).astype(int)

        group['price_change'] = group['close'].diff()
        group['obv'] = (np.sign(group['price_change']) * group['volume']).cumsum()
        group['obv_ma'] = group['obv'].rolling(20).mean()

        price_change = group['close'].pct_change()
        volume_change = group['volume'].pct_change()
        group['price_volume_corr'] = price_change.rolling(20).corr(volume_change)
        group['volume_price_trend'] = ((group['volume'] > group['volume_ma20']) &
                                       (group['close'] > group['ma_20'])).astype(int)

        # ========== 振幅因子 (5个) ==========
        group['high_low_pct'] = (group['high'] - group['low']) / group['close']
        group['gap'] = (group['open'] - group['close'].shift(1)) / group['close'].shift(1)
        group['amplitude_20d'] = group['high_low_pct'].rolling(20).mean()
        group['upper_shadow'] = (group['high'] - group[['close', 'open']].max(axis=1)) / group['close']
        group['lower_shadow'] = (group[['close', 'open']].min(axis=1) - group['low']) / group['close']

        # ========== 资金流因子 (5个) ==========
        typical_price = (group['high'] + group['low'] + group['close']) / 3
        raw_money_flow = typical_price * group['volume']
        positive_flow = raw_money_flow.where(typical_price > typical_price.shift(1), 0)
        negative_flow = raw_money_flow.where(typical_price < typical_price.shift(1), 0)
        positive_sum = positive_flow.rolling(14).sum()
        negative_sum = negative_flow.rolling(14).sum()
        money_ratio = positive_sum / (negative_sum + 1e-10)
        group['mfi'] = 100 - (100 / (1 + money_ratio))

        group['turnover'] = group['close'] * group['volume']
        group['turnover_ma5'] = group['turnover'].rolling(5).mean()
        group['turnover_ma20'] = group['turnover'].rolling(20).mean()
        group['turnover_ratio'] = group['turnover'] / group['turnover_ma20']

        group['money_inflow'] = (group['close'] > group['open']) * group['turnover']
        group['money_outflow'] = (group['close'] <= group['open']) * group['turnover']
        group['net_money_flow'] = (group['money_inflow'].rolling(5).sum() -
                                   group['money_outflow'].rolling(5).sum()) / group['turnover_ma5']

        group['big_money'] = (group['turnover'] > group['turnover_ma20'] * 1.5).astype(int)
        group['big_money_ratio'] = group['big_money'].rolling(5).sum() / 5

        # ========== 市值因子 (3个) ==========
        group['market_cap_proxy'] = group['close'] * group['volume_ma20']
        group['size_rank'] = group['market_cap_proxy'].rank(pct=True)
        group['price_level'] = group['close']
        group['is_low_price'] = (group['close'] < 10).astype(int)
        group['avg_turnover_20d'] = group['turnover'].rolling(20).mean()
        group['liquidity_score'] = group['avg_turnover_20d'] / group['avg_turnover_20d'].median()

        # 标签：未来5日收益率
        group['label'] = group['close'].shift(-5) / group['close'] - 1

        results.append(group)

    df = pd.concat(results, ignore_index=True)
    df['date'] = pd.to_datetime(df['date'])
    df = df[~df['symbol'].isin(['MARKET', 'SHINDEX'])]

    return df


def get_feature_cols():
    """获取v7特征列列表"""
    return [
        'return_1d', 'return_3d', 'return_5d', 'return_10d', 'return_20d', 'return_60d',
        'return_accel', 'intraday_momentum',
        'volatility_5d', 'volatility_10d', 'volatility_20d', 'volatility_60d',
        'vol_trend', 'realized_vol_5d',
        'price_to_ma20', 'ma5_to_ma20', 'ma20_to_ma60', 'trend_up', 'golden_cross',
        'bollinger_pos', 'bollinger_width', 'bollinger_squeeze',
        'rsi', 'rsi_overbought', 'rsi_oversold', 'rsi_divergence',
        'macd', 'macd_signal', 'macd_long', 'macd_hist', 'macd_cross',
        'volume_ratio_5_20', 'volume_ratio', 'volume_trend', 'volume_breakout',
        'obv', 'price_volume_corr', 'volume_price_trend',
        'high_low_pct', 'gap', 'amplitude_20d', 'upper_shadow', 'lower_shadow',
        'mfi', 'turnover_ratio', 'net_money_flow', 'big_money', 'big_money_ratio',
        'market_cap_proxy', 'size_rank', 'price_level', 'is_low_price', 'liquidity_score'
    ]


# ============================================
# 预测
# ============================================
def predict_ensemble(models, weights, df, feature_cols):
    """集成预测"""
    predictions = {}
    for name, model in models.items():
        # 使用booster预测避免sklearn API版本兼容问题
        if hasattr(model, 'booster_'):
            predictions[name] = model.booster_.predict(df[feature_cols].values)
        else:
            predictions[name] = model.predict(df[feature_cols])

    ensemble_pred = np.zeros(len(df))
    for name, weight in weights.items():
        ensemble_pred += weight * predictions[name]

    return ensemble_pred, predictions


# ============================================
# 市场环境检测
# ============================================
def detect_market_regime(price_df, date):
    """检测市场环境"""
    market_data = price_df[(price_df['symbol'] == 'MARKET') & (price_df['date'] <= date)].copy()
    if len(market_data) < 60:
        return 'CHOPPY'

    market_data = market_data.sort_values('date')
    ma20 = market_data['close'].iloc[-20:].mean()
    ma60 = market_data['close'].iloc[-60:].mean()

    if ma20 > ma60:
        return 'BULL'
    elif ma20 < ma60:
        return 'BEAR'
    else:
        return 'CHOPPY'


# ============================================
# 回测
# ============================================
def run_backtest(price_df, models, weights, feature_cols, stock_names, stock_industries,
                 pool_type, start_date, end_date):
    """运行回测"""
    logger.info(f"\n{'='*60}")
    logger.info(f" v7 Backtest - {pool_type.upper()}")
    logger.info(f" Period: {start_date} to {end_date}")
    logger.info(f"{'='*60}")

    # 计算特征
    df = calculate_features(price_df)
    df = df.dropna(subset=feature_cols)

    # 预测
    logger.info("Running predictions...")
    df['pred'], _ = predict_ensemble(models, weights, df, feature_cols)
    df['pred_rank'] = df.groupby('date')['pred'].rank(ascending=False, pct=True)

    test_df = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()
    test_df = test_df.sort_values(['date', 'symbol'])
    dates = sorted(test_df['date'].unique())

    logger.info(f"交易日: {len(dates)}, 股票数: {test_df['symbol'].nunique()}")

    # 回测变量
    initial_cash = RISK_CONFIG['account']
    cash = initial_cash
    positions = {}
    trades = []
    portfolio_values = []

    for i, date in enumerate(dates):
        if i % 50 == 0:
            logger.info(f"进度: {i}/{len(dates)} {date.strftime('%Y-%m-%d')}")

        day_data = test_df[test_df['date'] == date].copy()
        regime = detect_market_regime(price_df, date)
        cfg = PARAMS[regime]

        max_positions = int(RISK_CONFIG['max_positions'] * cfg['pos_ratio'])
        max_positions = max(2, max_positions)

        # ========== 卖出逻辑 ==========
        to_remove = []
        for sym, pos in positions.items():
            price_data = day_data[day_data['symbol'] == sym]['close'].values
            if len(price_data) == 0:
                continue

            current_price = price_data[0]
            pnl = (current_price - pos['cost']) / pos['cost']
            days = (date - pos['entry_date']).days

            highest_price = max(pos.get('highest_price', pos['cost']), current_price)
            positions[sym]['highest_price'] = highest_price
            highest_pnl = max(pos.get('highest_pnl', 0), pnl)
            positions[sym]['highest_pnl'] = highest_pnl

            reason = None
            if pnl <= HARD_STOP_LOSS:
                reason = f"{regime} Hard stop ({pnl:.1%})"
            elif current_price < highest_price * (1 - cfg['trailing_stop']):
                pullback = (highest_price - current_price) / highest_price
                reason = f"{regime} trailing stop ({pullback * 100:.1f}%)"
            elif days >= cfg['min_holding_days']:
                if highest_pnl <= 0.20:
                    current_rank = day_data[day_data['symbol'] == sym]['pred_rank'].values
                    if len(current_rank) > 0 and current_rank[0] > cfg['rank_exit_threshold']:
                        reason = f"{regime} rank exit ({current_rank[0] * 100:.1f}%)"

            if reason:
                amount = pos['shares'] * current_price * (1 - SCENARIOS['normal']['sell_cost'])
                profit = amount - pos['shares'] * pos['cost']
                trades.append({
                    '代码': sym, '名称': stock_names.get(sym, sym), '行业': pos['industry'],
                    '买入日期': pos['entry_date'].strftime('%Y%m%d'), '买入价': round(pos['cost'], 2),
                    '卖出日期': date.strftime('%Y%m%d'), '卖出价': round(current_price, 2),
                    '股数': pos['shares'], '盈亏金额': round(profit, 1),
                    '盈亏比例': f"{pnl * 100:.2f}%", '持有天数': days,
                    '买入信号': pos.get('buy_signal', 'Top Rank'),
                    '买入原因': pos.get('buy_reason', 'Top Rank'),
                    '卖出信号': reason, '卖出原因': reason,
                    '市场状态': regime, '股票池': pool_type,
                })
                cash += amount
                to_remove.append(sym)

        for sym in to_remove:
            if sym in positions:
                del positions[sym]

        # ========== 计算净值 ==========
        portfolio_value = cash
        for sym, pos in positions.items():
            price = day_data[day_data['symbol'] == sym]['close'].values
            if len(price) > 0:
                portfolio_value += pos['shares'] * price[0]

        # 行业敞口
        industry_exposure = {}
        for sym, pos in positions.items():
            price = day_data[day_data['symbol'] == sym]['close'].values
            if len(price) > 0:
                ind = pos['industry']
                industry_exposure[ind] = industry_exposure.get(ind, 0) + pos['shares'] * price[0] / portfolio_value

        # ========== 买入逻辑 ==========
        slots = max_positions - len(positions)
        if slots > 0 and cash > 0:
            candidates = day_data[~day_data['symbol'].isin(positions.keys())]
            if len(candidates) > 0:
                candidates = candidates.sort_values('pred', ascending=False)
                top = candidates[candidates['pred_rank'] <= cfg['top_n']]

                for _, row in top.iterrows():
                    if len(positions) >= max_positions:
                        break

                    sym = row['symbol']
                    price = row['close']
                    ind = stock_industries.get(sym, '其他')

                    # 风控检查
                    if row.get('return_1d', 0) > cfg['max_daily_return']:
                        continue
                    if row.get('deviation_from_ma5', 0) > cfg['max_ma5_deviation']:
                        continue

                    max_per_stock = portfolio_value * RISK_CONFIG['max_position_per_stock']
                    planned = min(cash * 0.95 / max(slots, 1), max_per_stock)

                    current_ind = industry_exposure.get(ind, 0)
                    if current_ind >= RISK_CONFIG['max_position_per_industry']:
                        continue

                    shares = int(planned / price / 100) * 100
                    if shares >= 100:
                        cost = shares * price * (1 + SCENARIOS['normal']['buy_cost'])
                        if cost <= cash:
                            cash -= cost
                            buy_signal_detail = f"Rank {row['pred_rank']:.2%}, Score {row['pred']:.4f}, {regime}"
                            positions[sym] = {
                                'shares': shares, 'cost': price, 'entry_date': date,
                                'industry': ind, 'highest_price': price, 'highest_pnl': 0,
                                'buy_signal': f"Rank {row['pred_rank']:.2%}",
                                'buy_reason': buy_signal_detail,
                                'market_regime_at_entry': regime,
                            }
                            industry_exposure[ind] = current_ind + shares * price / portfolio_value

        portfolio_values.append({
            'date': date, 'portfolio_value': portfolio_value, 'cash': cash,
            'positions': len(positions), 'market_regime': regime,
        })

    # ========== 清仓 ==========
    if positions:
        final_date = dates[-1]
        final_data = test_df[test_df['date'] == final_date]
        for sym, pos in list(positions.items()):
            price = final_data[final_data['symbol'] == sym]['close'].values
            if len(price) > 0:
                amount = pos['shares'] * price[0] * (1 - SCENARIOS['normal']['sell_cost'])
                profit = amount - pos['shares'] * pos['cost']
                days = (final_date - pos['entry_date']).days
                trades.append({
                    '代码': sym, '名称': stock_names.get(sym, sym), '行业': pos['industry'],
                    '买入日期': pos['entry_date'].strftime('%Y%m%d'), '买入价': round(pos['cost'], 2),
                    '卖出日期': final_date.strftime('%Y%m%d'), '卖出价': round(price[0], 2),
                    '股数': pos['shares'], '盈亏金额': round(profit, 1),
                    '盈亏比例': f"{(price[0] / pos['cost'] - 1) * 100:.2f}%",
                    '持有天数': days,
                    '买入信号': pos.get('buy_signal', 'Top Rank'),
                    '买入原因': pos.get('buy_reason', 'Top Rank'),
                    '卖出信号': 'Close all', '卖出原因': 'Close all',
                    '市场状态': 'END', '股票池': pool_type,
                })
                cash += amount

    # ========== 计算结果 ==========
    final_value = cash
    total_return = (final_value - initial_cash) / initial_cash

    pf = pd.DataFrame(portfolio_values)
    pf['cum_return'] = (pf['portfolio_value'] / initial_cash) - 1
    pf['max_drawdown'] = pf['cum_return'] - pf['cum_return'].cummax()
    max_dd = pf['max_drawdown'].min()

    trades_df = pd.DataFrame(trades)
    win_rate = (trades_df['盈亏金额'].astype(float) > 0).mean() if len(trades_df) > 0 else 0
    avg_holding = trades_df['持有天数'].mean() if len(trades_df) > 0 else 0

    if len(trades_df) > 0:
        profits = trades_df[trades_df['盈亏金额'].astype(float) > 0]['盈亏金额'].astype(float)
        losses = trades_df[trades_df['盈亏金额'].astype(float) < 0]['盈亏金额'].astype(float)
        profit_factor = abs(profits.sum() / losses.sum()) if len(losses) > 0 and losses.sum() != 0 else float('inf')
    else:
        profit_factor = 0

    logger.info(f"\n{'='*60}")
    logger.info(f" {pool_type.upper()} v7 回测结果:")
    logger.info(f"  总收益率: {total_return:.2%}")
    logger.info(f"  最大回撤: {max_dd:.2%}")
    logger.info(f"  胜率: {win_rate:.2%}")
    logger.info(f"  盈亏比: {profit_factor:.2f}")
    logger.info(f"  交易次数: {len(trades)}")
    logger.info(f"{'='*60}")

    return {
        'pool': pool_type, 'total_return': total_return, 'max_drawdown': max_dd,
        'win_rate': win_rate, 'profit_factor': profit_factor,
        'total_trades': len(trades), 'avg_holding_days': avg_holding,
    }, trades_df, pf


# ============================================
# 主程序
# ============================================
def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='v7量化策略主程序')
    parser.add_argument('--start', type=str, default='2025-01-01', help='开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default='2025-03-31', help='结束日期 (YYYY-MM-DD)')
    parser.add_argument('--pool', type=str, default='csi500', choices=['csi300', 'csi500', 'csi1000'],
                        help='股票池: csi300, csi500, csi1000')
    parser.add_argument('--mode', type=str, default='backtest', choices=['backtest', 'predict'],
                        help='运行模式: backtest(回测), predict(预测)')

    args = parser.parse_args()

    logger.info("="*70)
    logger.info(" v7.0 量化策略系统")
    logger.info(f" 模式: {args.mode}, 股票池: {args.pool}")
    logger.info(f" 时间范围: {args.start} 至 {args.end}")
    logger.info("="*70)

    # 加载模型
    models, weights, feature_cols = load_v7_model(args.pool)

    # 初始化数据获取器
    fetcher = DataFetcher(CONFIG['tushare_token'], CONFIG['cache_path'])

    # 加载数据
    logger.info("\n加载市场数据...")
    price_df, stock_names, stock_industries, stock_tscodes = fetcher.load_data_extended(
        args.start, args.end, args.pool
    )

    if args.mode == 'backtest':
        # 运行回测
        result, trades, pf = run_backtest(
            price_df, models, weights, feature_cols, stock_names, stock_industries,
            args.pool, args.start, args.end
        )

        # 保存结果
        out_dir = Path(CONFIG['results_dir']) / f"v7_{args.pool}"
        out_dir.mkdir(exist_ok=True, parents=True)
        trades.to_csv(out_dir / f"trades_{args.start[:4]}.csv", index=False, encoding='utf-8-sig')
        pf.to_csv(out_dir / f"portfolio_{args.start[:4]}.csv", index=False)
        logger.info(f"\n结果已保存到: {out_dir}")

    elif args.mode == 'predict':
        # 预测模式：输出今日选股
        logger.info("\n计算特征...")
        df = calculate_features(price_df)
        df = df.dropna(subset=feature_cols)

        logger.info("运行预测...")
        df['pred'], _ = predict_ensemble(models, weights, df, feature_cols)

        # 获取最新日期的预测
        latest_date = df['date'].max()
        latest_df = df[df['date'] == latest_date].copy()
        latest_df = latest_df.sort_values('pred', ascending=False)

        logger.info(f"\n{'='*60}")
        logger.info(f" {latest_date.strftime('%Y-%m-%d')} 选股推荐 (Top 20)")
        logger.info(f"{'='*60}")
        logger.info(f"{'排名':<6}{'代码':<10}{'名称':<12}{'预测得分':<12}{'行业':<10}")
        logger.info("-"*60)

        for i, (_, row) in enumerate(latest_df.head(20).iterrows(), 1):
            sym = row['symbol']
            name = stock_names.get(sym, sym)
            industry = stock_industries.get(sym, '其他')
            score = row['pred']
            logger.info(f"{i:<6}{sym:<10}{name:<12}{score:<12.4f}{industry:<10}")

        # 保存预测结果
        out_dir = Path(CONFIG['results_dir'])
        out_dir.mkdir(exist_ok=True, parents=True)
        latest_df[['symbol', 'pred']].to_csv(
            out_dir / f"predictions_{latest_date.strftime('%Y%m%d')}.csv",
            index=False
        )


if __name__ == "__main__":
    main()