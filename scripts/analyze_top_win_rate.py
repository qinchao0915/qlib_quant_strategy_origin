#!/usr/bin/env python3
"""
分析模型在不同Top比例下的胜率表现
"""
import pandas as pd
import re
from pathlib import Path

def extract_rank(buy_signal):
    """从买入信号中提取排名百分比"""
    if pd.isna(buy_signal):
        return 1.0
    match = re.search(r'Rank\s+([\d.]+)%', str(buy_signal))
    if match:
        return float(match.group(1)) / 100
    return 1.0

def analyze_top_win_rate(df, pool_name, year):
    """分析不同Top比例的胜率"""
    # 提取排名
    df['rank_pct'] = df['买入信号'].apply(extract_rank)

    # 判断盈亏
    df['is_win'] = df['盈亏金额'] > 0

    results = []

    # 定义Top比例
    top_thresholds = [0.01, 0.03, 0.05, 0.10]
    top_labels = ['Top 1%', 'Top 3%', 'Top 5%', 'Top 10%']

    for threshold, label in zip(top_thresholds, top_labels):
        # 筛选该区间内的交易
        if threshold == 0.01:
            mask = df['rank_pct'] <= 0.01
        elif threshold == 0.03:
            mask = (df['rank_pct'] > 0.01) & (df['rank_pct'] <= 0.03)
        elif threshold == 0.05:
            mask = (df['rank_pct'] > 0.03) & (df['rank_pct'] <= 0.05)
        else:  # 0.10
            mask = (df['rank_pct'] > 0.05) & (df['rank_pct'] <= 0.10)

        subset = df[mask]

        if len(subset) > 0:
            win_rate = subset['is_win'].mean()
            avg_return = subset['盈亏比例'].str.replace('%', '').astype(float).mean()
            total_trades = len(subset)
            win_trades = subset['is_win'].sum()
        else:
            win_rate = 0
            avg_return = 0
            total_trades = 0
            win_trades = 0

        results.append({
            '股票池': pool_name,
            '年份': year,
            '分组': label,
            '交易次数': total_trades,
            '盈利次数': win_trades,
            '胜率': f"{win_rate:.2%}",
            '平均收益率': f"{avg_return:.2f}%"
        })

    return results

def main():
    """主函数"""
    base_path = Path('/Users/qin/Documents/qlib_quant_origin/results')

    pools = ['csi300', 'csi500', 'csi1000']
    years = ['2025', '2026']

    all_results = []

    print("=" * 80)
    print("v7_2025 模型不同Top比例胜率分析")
    print("=" * 80)

    for pool in pools:
        for year in years:
            file_path = base_path / f'v7_2025_{pool}' / f'trades_{year}.csv'

            if not file_path.exists():
                print(f"文件不存在: {file_path}")
                continue

            try:
                df = pd.read_csv(file_path)
                if len(df) == 0:
                    continue

                results = analyze_top_win_rate(df, pool.upper(), year)
                all_results.extend(results)

            except Exception as e:
                print(f"处理 {file_path} 时出错: {e}")
                continue

    # 输出结果
    results_df = pd.DataFrame(all_results)

    # 按股票池和年份分组显示
    for pool in ['CSI300', 'CSI500', 'CSI1000']:
        print(f"\n{'='*80}")
        print(f"【{pool}】")
        print('='*80)

        pool_data = results_df[results_df['股票池'] == pool]

        for year in ['2025', '2026']:
            year_data = pool_data[pool_data['年份'] == year]
            if len(year_data) == 0:
                continue

            print(f"\n{year}年数据:")
            print("-" * 80)
            print(f"{'分组':<12} {'交易次数':>10} {'盈利次数':>10} {'胜率':>12} {'平均收益率':>12}")
            print("-" * 80)

            for _, row in year_data.iterrows():
                print(f"{row['分组']:<12} {row['交易次数']:>10} {row['盈利次数']:>10} {row['胜率']:>12} {row['平均收益率']:>12}")

    # 保存结果
    output_path = base_path / 'top_win_rate_analysis.csv'
    results_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"\n\n详细结果已保存至: {output_path}")

if __name__ == '__main__':
    main()
