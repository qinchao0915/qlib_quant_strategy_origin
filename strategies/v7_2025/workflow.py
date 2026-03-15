#!/usr/bin/env python3
"""
Qlib量化策略 v7.0 工作流模块
使用已拆分的模块化架构

重构后的主程序入口 - 使用 config/ 和 core/ 下的模块
"""

import sys
import pandas as pd
import numpy as np
import pickle
from pathlib import Path
from datetime import datetime

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# ============================================
# 导入已拆分的模块
# ============================================
from config.settings import (
    TUSHARE_TOKEN, CACHE_PATH, MODEL_DIR, RESULTS_DIR,
    RISK_CONFIG, PARAMS, SCENARIOS
)
from core.data.fetcher import DataFetcher
from core.features.engineering import FeatureEngineer
from core.utils.logger import logger

# 硬编码配置
HARD_STOP_LOSS = -0.08


# ============================================
# 任务1: 解析命令行参数
# ============================================
def parse_args():
    """解析命令行参数"""
    import argparse

    parser = argparse.ArgumentParser(description='v7量化策略工作流')
    parser.add_argument('--start', type=str, default='2025-01-01',
                        help='开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default='2025-03-31',
                        help='结束日期 (YYYY-MM-DD)')
    parser.add_argument('--pool', type=str, default='csi500',
                        choices=['csi300', 'csi500', 'csi1000'],
                        help='股票池: csi300, csi500, csi1000')
    parser.add_argument('--mode', type=str, default='backtest',
                        choices=['backtest', 'predict'],
                        help='运行模式: backtest(回测), predict(预测)')

    return parser.parse_args()


# ============================================
# 任务2: 初始化模型和数据获取器
# ============================================
def initialize_components(args):
    """初始化模型和数据获取器"""
    models, weights, feature_cols = load_v7_model(args.pool)
    fetcher = DataFetcher(TUSHARE_TOKEN, str(CACHE_PATH))
    feature_engineer = FeatureEngineer()

    return models, weights, feature_cols, fetcher, feature_engineer


def load_v7_model(pool_type='csi500'):
    """加载v7模型"""
    model_path = Path(MODEL_DIR) / f"model_enhanced_v7_{pool_type}.pkl"
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
# 任务3: 加载市场数据
# ============================================
def load_market_data(fetcher, args):
    """加载市场数据"""
    logger.info("\n加载市场数据...")
    price_df, stock_names, stock_industries, stock_tscodes = fetcher.load_data_extended(
        args.start, args.end, args.pool
    )
    return price_df, stock_names, stock_industries, stock_tscodes


# ============================================
# 任务4: 执行回测
# ============================================
def execute_backtest(price_df, models, weights, feature_cols, feature_engineer,
                     stock_names, stock_industries, args):
    """执行回测"""
    result, trades, pf = run_backtest(
        price_df, models, weights, feature_cols, feature_engineer,
        stock_names, stock_industries, args.pool, args.start, args.end
    )
    return result, trades, pf


def detect_market_regime(price_df, date):
    """检测市场环境"""
    market_data = price_df[(price_df['symbol'] == 'MARKET') &
                           (price_df['date'] <= date)].copy()
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


def run_backtest(price_df, models, weights, feature_cols, feature_engineer,
                 stock_names, stock_industries, pool_type, start_date, end_date):
    """运行回测"""
    logger.info(f"\n{'='*60}")
    logger.info(f" v7 Backtest - {pool_type.upper()}")
    logger.info(f" Period: {start_date} to {end_date}")
    logger.info(f"{'='*60}")

    # 计算特征
    df = feature_engineer.calculate_features(price_df)

    # 只保留模型期望的特征列（避免FeatureEngineer的额外列影响预测）
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
                    '买入日期': pos['entry_date'].strftime('%Y%m%d'),
                    '买入价': round(pos['cost'], 2),
                    '卖出日期': date.strftime('%Y%m%d'),
                    '卖出价': round(current_price, 2),
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
                industry_exposure[ind] = industry_exposure.get(ind, 0) + \
                    pos['shares'] * price[0] / portfolio_value

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
                    '买入日期': pos['entry_date'].strftime('%Y%m%d'),
                    '买入价': round(pos['cost'], 2),
                    '卖出日期': final_date.strftime('%Y%m%d'),
                    '卖出价': round(price[0], 2),
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
        profit_factor = abs(profits.sum() / losses.sum()) \
            if len(losses) > 0 and losses.sum() != 0 else float('inf')
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
# 任务5: 保存回测结果
# ============================================
def save_backtest_results(trades, pf, args):
    """保存回测结果"""
    out_dir = Path(RESULTS_DIR) / f"v7_{args.pool}"
    out_dir.mkdir(exist_ok=True, parents=True)
    trades.to_csv(out_dir / f"trades_{args.start[:4]}.csv",
                  index=False, encoding='utf-8-sig')
    pf.to_csv(out_dir / f"portfolio_{args.start[:4]}.csv", index=False)
    logger.info(f"\n结果已保存到: {out_dir}")


# ============================================
# 任务6: 生成选股预测
# ============================================
def generate_predictions(price_df, models, weights, feature_cols,
                         feature_engineer, stock_names, args):
    """生成选股预测"""
    logger.info("\n计算特征...")
    df = feature_engineer.calculate_features(price_df)
    df = df.dropna(subset=feature_cols)

    logger.info("运行预测...")
    df['pred'], _ = predict_ensemble(models, weights, df, feature_cols)

    # 获取最新日期的预测
    latest_date = df['date'].max()
    latest_df = df[df['date'] == latest_date].copy()
    latest_df = latest_df.sort_values('pred', ascending=False)

    return latest_df, latest_date


# ============================================
# 任务7: 展示预测结果
# ============================================
def display_predictions(latest_df, latest_date, stock_names, stock_industries):
    """展示预测结果"""
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


# ============================================
# 任务8: 保存预测结果
# ============================================
def save_predictions(latest_df, latest_date):
    """保存预测结果"""
    out_dir = Path(RESULTS_DIR)
    out_dir.mkdir(exist_ok=True, parents=True)
    latest_df[['symbol', 'pred']].to_csv(
        out_dir / f"predictions_{latest_date.strftime('%Y%m%d')}.csv",
        index=False
    )


# ============================================
# 主函数：协调各模块
# ============================================
def main():
    """主函数：协调各模块"""
    args = parse_args()

    logger.info("="*70)
    logger.info(" v7.0 量化策略系统 (模块化版本)")
    logger.info(f" 模式: {args.mode}, 股票池: {args.pool}")
    logger.info(f" 时间范围: {args.start} 至 {args.end}")
    logger.info("="*70)

    # 初始化组件
    models, weights, feature_cols, fetcher, feature_engineer = initialize_components(args)

    # 加载市场数据
    price_df, stock_names, stock_industries, _ = load_market_data(fetcher, args)

    # 根据模式执行
    if args.mode == 'backtest':
        result, trades, pf = execute_backtest(
            price_df, models, weights, feature_cols, feature_engineer,
            stock_names, stock_industries, args
        )
        save_backtest_results(trades, pf, args)
    elif args.mode == 'predict':
        latest_df, latest_date = generate_predictions(
            price_df, models, weights, feature_cols,
            feature_engineer, stock_names, args
        )
        display_predictions(latest_df, latest_date, stock_names, stock_industries)
        save_predictions(latest_df, latest_date)


if __name__ == "__main__":
    main()
