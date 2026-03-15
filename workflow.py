#!/usr/bin/env python3
"""
通用策略工作流

支持任意策略的加载和执行
使用方式:
    python workflow.py --strategy v7_2025 --pool csi500 --mode backtest
    python workflow.py --strategy v7_2025 --pool csi500 --mode predict
"""
import sys
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies import load_strategy, list_strategies
from core.data.fetcher import DataFetcher
from core.utils.logger import logger
from config.settings import TUSHARE_TOKEN, CACHE_PATH, RESULTS_DIR


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='量化策略通用工作流')

    parser.add_argument('--strategy', type=str, default='v7_2025',
                        help=f'策略名称。可用: {", ".join(list_strategies().keys())}')
    parser.add_argument('--pool', type=str, default='csi500',
                        choices=['csi300', 'csi500', 'csi1000'],
                        help='股票池')
    parser.add_argument('--mode', type=str, default='backtest',
                        choices=['backtest', 'predict'],
                        help='运行模式')
    parser.add_argument('--start', type=str, default='2025-01-01',
                        help='开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default='2025-12-31',
                        help='结束日期 (YYYY-MM-DD)')
    parser.add_argument('--sell-price', type=str, default='open',
                        choices=['open', 'close'],
                        help='卖出价格类型: open=开盘价, close=收盘价 (默认: open)')

    return parser.parse_args()


def load_data(args):
    """加载数据"""
    logger.info("\n加载市场数据...")
    fetcher = DataFetcher(TUSHARE_TOKEN, str(CACHE_PATH))
    return fetcher.load_data_extended(args.start, args.end, args.pool)


def run_backtest_strategy(strategy, price_df, stock_names, stock_industries,
                          pool_type, start_date, end_date, sell_price_type='open'):
    """
    执行策略回测

    通用回测引擎，通过策略接口执行具体逻辑

    参数:
        sell_price_type: 'open' 或 'close', 卖出时使用的价格
    """
    logger.info(f"\n{'='*60}")
    logger.info(f" {strategy.name} Backtest - {pool_type.upper()}")
    logger.info(f" Period: {start_date} to {end_date}")
    logger.info(f"{'='*60}")

    # 加载模型
    strategy.load_models(pool_type)

    # 生成信号
    logger.info("生成交易信号...")
    signals_df = strategy.generate_signals(price_df)

    # 筛选回测区间
    test_df = signals_df[(signals_df['date'] >= start_date) &
                         (signals_df['date'] <= end_date)].copy()
    test_df = test_df.sort_values(['date', 'symbol'])
    dates = sorted(test_df['date'].unique())

    logger.info(f"交易日: {len(dates)}, 股票数: {test_df['symbol'].nunique()}")

    # 获取配置
    cfg = strategy.get_config()
    risk_config = cfg['risk']
    scenarios = cfg['scenarios']

    # 回测变量
    initial_cash = risk_config['account']
    cash = initial_cash
    positions = {}
    trades = []
    portfolio_values = []

    for i, date in enumerate(dates):
        if i % 50 == 0:
            logger.info(f"进度: {i}/{len(dates)} {date.strftime('%Y-%m-%d')}")

        day_data = test_df[test_df['date'] == date].copy()
        regime = strategy.detect_market_regime(price_df, date)
        params = cfg['params'][regime]

        max_positions = int(risk_config['max_positions'] * params['pos_ratio'])
        max_positions = max(2, max_positions)

        # ========== 卖出逻辑 ==========
        to_remove = []
        for sym, pos in positions.items():
            stock_day_data = day_data[day_data['symbol'] == sym]
            if len(stock_day_data) == 0:
                continue

            # 使用当天开盘价卖出
            open_price = stock_day_data['open'].values[0]
            high_price = stock_day_data['high'].values[0]
            low_price = stock_day_data['low'].values[0]
            pre_close = stock_day_data['pre_close'].values[0] if 'pre_close' in stock_day_data.columns else pos['cost']

            # 一字跌停判断：开盘价<=跌停价 且 开盘价==最低价（无法卖出）
            跌停价 = pre_close * 0.9  # 10%跌停板
            is_一字跌停 = (open_price <= 跌停价 * 1.001) and (abs(open_price - low_price) < 0.001)

            if is_一字跌停:
                continue  # 一字跌停无法卖出

            # 卖出价格选择：开盘价或收盘价
            if sell_price_type == 'close':
                sell_price = stock_day_data['close'].values[0]
                current_price = sell_price
            else:
                sell_price = open_price
                current_price = open_price

            days = (date - pos['entry_date']).days

            # 使用策略的卖出判断
            should_sell, reason, pnl = strategy.should_sell(
                pos, current_price, days, regime, day_data
            )

            if should_sell:
                # 计算卖出金额
                amount = pos['shares'] * current_price * (1 - scenarios['normal']['sell_cost'])
                profit = amount - pos['shares'] * pos['cost']

                trades.append({
                    '代码': sym,
                    '名称': stock_names.get(sym, sym),
                    '行业': pos['industry'],
                    '买入日期': pos['entry_date'].strftime('%Y%m%d'),
                    '买入价': round(pos['cost'], 2),
                    '卖出日期': date.strftime('%Y%m%d'),
                    '卖出价': round(current_price, 2),
                    '股数': pos['shares'],
                    '盈亏金额': round(profit, 1),
                    '盈亏比例': f"{pnl * 100:.2f}%",
                    '持有天数': days,
                    '买入信号': pos.get('buy_signal', ''),
                    '买入原因': pos.get('buy_reason', ''),
                    '卖出信号': reason,
                    '卖出原因': reason,
                    '市场状态': regime,
                    '股票池': pool_type,
                })

                cash += amount
                to_remove.append(sym)
            else:
                # 更新最高价格
                positions[sym]['highest_price'] = max(
                    pos.get('highest_price', pos['cost']),
                    current_price
                )
                positions[sym]['highest_pnl'] = max(
                    pos.get('highest_pnl', 0),
                    pnl
                )

        for sym in to_remove:
            if sym in positions:
                del positions[sym]

        # ========== 计算净值 ==========
        portfolio_value = cash
        for sym, pos in positions.items():
            # 使用当天开盘价计算持仓市值
            stock_data = day_data[day_data['symbol'] == sym]
            if len(stock_data) > 0:
                open_price = stock_data['open'].values[0]
                portfolio_value += pos['shares'] * open_price

        # 行业敞口（使用开盘价计算）
        industry_exposure = {}
        for sym, pos in positions.items():
            stock_data = day_data[day_data['symbol'] == sym]
            if len(stock_data) > 0:
                open_price = stock_data['open'].values[0]
                ind = pos['industry']
                industry_exposure[ind] = industry_exposure.get(ind, 0) + \
                    pos['shares'] * open_price / portfolio_value

        # ========== 买入逻辑 ==========
        slots = max_positions - len(positions)
        if slots > 0 and cash > 0:
            candidates = day_data[~day_data['symbol'].isin(positions.keys())]
            if len(candidates) > 0:
                candidates = candidates.sort_values('pred', ascending=False)
                top_candidates = candidates.head(int(len(candidates) * params['top_n']) + 10)

                for _, row in top_candidates.iterrows():
                    if len(positions) >= max_positions:
                        break

                    # 使用策略的买入判断
                    should_buy, reason = strategy.should_buy(
                        row, regime, industry_exposure,
                        portfolio_value, len(positions), cash
                    )

                    if not should_buy:
                        continue

                    sym = row['symbol']
                    # 使用当天开盘价买入
                    open_price = row['open']
                    high_price = row['high']
                    low_price = row['low']
                    pre_close = row['pre_close'] if 'pre_close' in row else open_price

                    # 一字涨停判断：开盘价>=涨停价 且 开盘价==最高价（无法买入）
                    涨停价 = pre_close * 1.1  # 10%涨停板
                    is_一字涨停 = (open_price >= 涨停价 * 0.999) and (abs(open_price - high_price) < 0.001)

                    if is_一字涨停:
                        continue  # 一字涨停无法买入

                    price = open_price
                    ind = stock_industries.get(sym, '其他')

                    # 计算买入股数
                    shares = strategy.calculate_position_size(
                        cash, slots, portfolio_value, price,
                        risk_config['max_position_per_stock']
                    )

                    if shares < 100:
                        continue

                    cost = shares * price * (1 + scenarios['normal']['buy_cost'])
                    if cost > cash:
                        continue

                    cash -= cost
                    buy_signal_detail = f"Rank {row['pred_rank']:.2%}, Score {row['pred']:.4f}, {regime}"

                    positions[sym] = {
                        'shares': shares,
                        'cost': price,
                        'entry_date': date,
                        'industry': ind,
                        'highest_price': price,
                        'highest_pnl': 0,
                        'buy_signal': f"Rank {row['pred_rank']:.2%}",
                        'buy_reason': buy_signal_detail,
                        'market_regime_at_entry': regime,
                    }

                    industry_exposure[ind] = industry_exposure.get(ind, 0) + \
                        shares * price / portfolio_value

        portfolio_values.append({
            'date': date,
            'portfolio_value': portfolio_value,
            'cash': cash,
            'positions': len(positions),
            'market_regime': regime,
        })

    # ========== 清仓 ==========
    if positions:
        final_date = dates[-1]
        final_data = test_df[test_df['date'] == final_date]

        for sym, pos in list(positions.items()):
            stock_data = final_data[final_data['symbol'] == sym]
            if len(stock_data) > 0:
                # 最后一天清仓根据配置选择开盘价或收盘价
                if sell_price_type == 'close':
                    close_price = stock_data['close'].values[0]
                    sell_price = close_price
                else:
                    open_price = stock_data['open'].values[0]
                    sell_price = open_price

                amount = pos['shares'] * sell_price * (1 - scenarios['normal']['sell_cost'])
                profit = amount - pos['shares'] * pos['cost']
                days = (final_date - pos['entry_date']).days
                pnl = (sell_price - pos['cost']) / pos['cost']

                trades.append({
                    '代码': sym,
                    '名称': stock_names.get(sym, sym),
                    '行业': pos['industry'],
                    '买入日期': pos['entry_date'].strftime('%Y%m%d'),
                    '买入价': round(pos['cost'], 2),
                    '卖出日期': final_date.strftime('%Y%m%d'),
                    '卖出价': round(sell_price, 2),
                    '股数': pos['shares'],
                    '盈亏金额': round(profit, 1),
                    '盈亏比例': f"{pnl * 100:.2f}%",
                    '持有天数': days,
                    '买入信号': pos.get('buy_signal', ''),
                    '买入原因': pos.get('buy_reason', ''),
                    '卖出信号': 'Close all',
                    '卖出原因': 'Close all',
                    '市场状态': 'END',
                    '股票池': pool_type,
                })
                cash += amount

    # ========== 计算结果 ==========
    final_value = cash
    total_return = (final_value - initial_cash) / initial_cash

    pf = pd.DataFrame(portfolio_values)
    pf['cum_return'] = (pf['portfolio_value'] / initial_cash) - 1
    pf['max_drawdown'] = pf['cum_return'] - pf['cum_return'].cummax()
    max_dd = pf['max_drawdown'].min()

    trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()

    if len(trades_df) > 0:
        win_rate = (trades_df['盈亏金额'].astype(float) > 0).mean()
        profits = trades_df[trades_df['盈亏金额'].astype(float) > 0]['盈亏金额'].astype(float)
        losses = trades_df[trades_df['盈亏金额'].astype(float) < 0]['盈亏金额'].astype(float)
        profit_factor = abs(profits.sum() / losses.sum()) if len(losses) > 0 and losses.sum() != 0 else float('inf')
        avg_holding = trades_df['持有天数'].mean()
    else:
        win_rate = 0
        profit_factor = 0
        avg_holding = 0

    logger.info(f"\n{'='*60}")
    logger.info(f" {pool_type.upper()} {strategy.name} 回测结果:")
    logger.info(f"  总收益率: {total_return:.2%}")
    logger.info(f"  最大回撤: {max_dd:.2%}")
    logger.info(f"  胜率: {win_rate:.2%}")
    logger.info(f"  盈亏比: {profit_factor:.2f}")
    logger.info(f"  交易次数: {len(trades)}")
    logger.info(f"{'='*60}")

    return {
        'pool': pool_type,
        'total_return': total_return,
        'max_drawdown': max_dd,
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'total_trades': len(trades),
        'avg_holding_days': avg_holding,
    }, trades_df, pf


def run_predict_strategy(strategy, price_df, stock_names, stock_industries, pool_type):
    """执行策略预测"""
    logger.info("\n生成选股预测...")

    # 加载模型
    strategy.load_models(pool_type)

    # 生成信号
    signals_df = strategy.generate_signals(price_df)

    # 获取最新日期
    latest_date = signals_df['date'].max()
    latest_df = signals_df[signals_df['date'] == latest_date].copy()
    latest_df = latest_df.sort_values('pred', ascending=False)

    # 展示结果
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

    return latest_df, latest_date


def main():
    """主函数"""
    args = parse_args()

    logger.info("="*70)
    logger.info(f" 量化策略工作流")
    logger.info(f" 策略: {args.strategy}, 股票池: {args.pool}, 模式: {args.mode}")
    logger.info(f" 时间: {args.start} 至 {args.end}")
    if args.mode == 'backtest':
        logger.info(f" 卖出价格: {args.sell_price}")
    logger.info("="*70)

    # 加载策略
    try:
        strategy = load_strategy(args.strategy)
        logger.info(f"成功加载策略: {strategy.name}")
    except Exception as e:
        logger.error(f"加载策略失败: {e}")
        return

    # 加载数据
    price_df, stock_names, stock_industries, _ = load_data(args)

    # 执行
    if args.mode == 'backtest':
        result, trades, pf = run_backtest_strategy(
            strategy, price_df, stock_names, stock_industries,
            args.pool, args.start, args.end, sell_price_type=args.sell_price
        )

        # 保存结果
        out_dir = Path(RESULTS_DIR) / f"{args.strategy}_{args.pool}"
        out_dir.mkdir(exist_ok=True, parents=True)
        trades.to_csv(out_dir / f"trades_{args.start[:4]}.csv",
                      index=False, encoding='utf-8-sig')
        pf.to_csv(out_dir / f"portfolio_{args.start[:4]}.csv", index=False)
        logger.info(f"\n结果已保存到: {out_dir}")

    elif args.mode == 'predict':
        latest_df, latest_date = run_predict_strategy(
            strategy, price_df, stock_names, stock_industries, args.pool
        )

        # 保存预测
        out_dir = Path(RESULTS_DIR)
        out_dir.mkdir(exist_ok=True, parents=True)
        latest_df[['symbol', 'pred']].to_csv(
            out_dir / f"predictions_{args.strategy}_{latest_date.strftime('%Y%m%d')}.csv",
            index=False
        )


if __name__ == "__main__":
    main()
