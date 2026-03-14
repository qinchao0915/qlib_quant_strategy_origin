# 待办事项

## 下一步任务

### 1. 扩展股票池覆盖范围
- **任务**: 将回测股票池从 CSI500 扩展到 CSI300 和 CSI1000
- **状态**: ✅ 已完成
- **结果**:
  - CSI300 2025: -3.77% (跑输大盘)
  - CSI500 2025: +84.97%
  - CSI1000 2025: +50.33%
- **分析**: 策略在中小盘表现更好，大盘蓝筹股表现较差

### 预期执行命令
```bash
# CSI300 回测
python3 main.py --start 2025-01-01 --end 2025-12-31 --pool csi300 --mode backtest
python3 main.py --start 2026-01-01 --end 2026-03-14 --pool csi300 --mode backtest

# CSI1000 回测
python3 main.py --start 2025-01-01 --end 2025-12-31 --pool csi1000 --mode backtest
python3 main.py --start 2026-01-01 --end 2026-03-14 --pool csi1000 --mode backtest
```

### 对比维度
- 收益率差异
- 最大回撤
- 胜率、盈亏比
- 交易次数
- 不同市场状态下的表现

---

## 数据优化任务

### 2. 新增买入原因字段
- **任务**: 在回测结果 `trades` 数据中新增 `买入原因` 字段
- **状态**: ✅ 已完成
- **实现**:
  - 新增 `买入原因` 列，格式：`Rank 2.87%, Score 0.0324, BULL`
  - 包含预测排名、得分、市场状态

### 3. 优化 Hard Stop 卖出原因
- **任务**: Hard Stop 卖出原因需包含市场状态信息
- **状态**: ✅ 已完成
- **实现**:
  - 修改前：`Hard stop (-8.0%)`
  - 修改后：`BEAR Hard stop (-8.0%)` 或 `BULL Hard stop (-8.0%)`

---

## 代码重构任务

### 4. 拆分 main 函数为独立模块
- **任务**: 将 monolithic 的 `main()` 函数拆分为多个职责单一的函数
- **状态**: 待完成
- **当前问题**: `main()` 函数包含参数解析、模型加载、数据获取、回测执行、结果保存、预测输出等多个职责
- **拆分方案**:

```python
# 重构后的结构

def parse_args():
    """任务1: 解析命令行参数"""
    parser = argparse.ArgumentParser(...)
    # ... 参数定义
    return parser.parse_args()

def initialize_components(args):
    """任务2: 初始化模型和数据获取器"""
    models, weights, feature_cols = load_v7_model(args.pool)
    fetcher = DataFetcher(CONFIG['tushare_token'], CONFIG['cache_path'])
    return models, weights, feature_cols, fetcher

def load_market_data(fetcher, args):
    """任务3: 加载市场数据"""
    logger.info("\n加载市场数据...")
    price_df, stock_names, stock_industries, stock_tscodes = fetcher.load_data_extended(
        args.start, args.end, args.pool
    )
    return price_df, stock_names, stock_industries, stock_tscodes

def execute_backtest(price_df, models, weights, feature_cols, stock_names,
                     stock_industries, args):
    """任务4: 执行回测"""
    result, trades, pf = run_backtest(
        price_df, models, weights, feature_cols, stock_names, stock_industries,
        args.pool, args.start, args.end
    )
    return result, trades, pf

def save_backtest_results(trades, pf, args):
    """任务5: 保存回测结果"""
    out_dir = Path(CONFIG['results_dir']) / f"v7_{args.pool}"
    out_dir.mkdir(exist_ok=True, parents=True)
    trades.to_csv(out_dir / f"trades_{args.start[:4]}.csv", ...)
    pf.to_csv(out_dir / f"portfolio_{args.start[:4]}.csv", ...)
    logger.info(f"\n结果已保存到: {out_dir}")

def generate_predictions(price_df, models, weights, feature_cols, stock_names, args):
    """任务6: 生成选股预测"""
    df = calculate_features(price_df)
    df = df.dropna(subset=feature_cols)
    df['pred'], _ = predict_ensemble(models, weights, df, feature_cols)

    latest_date = df['date'].max()
    latest_df = df[df['date'] == latest_date].copy()
    latest_df = latest_df.sort_values('pred', ascending=False)
    return latest_df, latest_date

def display_predictions(latest_df, latest_date, stock_names, stock_industries):
    """任务7: 展示预测结果"""
    logger.info(f"\n{'='*60}")
    logger.info(f" {latest_date.strftime('%Y-%m-%d')} 选股推荐 (Top 20)")
    # ... 展示逻辑

def save_predictions(latest_df, latest_date):
    """任务8: 保存预测结果"""
    out_dir = Path(CONFIG['results_dir'])
    out_dir.mkdir(exist_ok=True, parents=True)
    latest_df[['symbol', 'pred']].to_csv(
        out_dir / f"predictions_{latest_date.strftime('%Y%m%d')}.csv", index=False
    )

def main():
    """主函数：协调各模块"""
    args = parse_args()

    # 初始化
    models, weights, feature_cols, fetcher = initialize_components(args)
    price_df, stock_names, stock_industries, _ = load_market_data(fetcher, args)

    # 根据模式执行
    if args.mode == 'backtest':
        result, trades, pf = execute_backtest(
            price_df, models, weights, feature_cols, stock_names, stock_industries, args
        )
        save_backtest_results(trades, pf, args)
    elif args.mode == 'predict':
        latest_df, latest_date = generate_predictions(
            price_df, models, weights, feature_cols, stock_names, args
        )
        display_predictions(latest_df, latest_date, stock_names, stock_industries)
        save_predictions(latest_df, latest_date)
```

- **重构收益**:
  1. **单一职责**: 每个函数只做一件事，便于单元测试
  2. **可复用**: 各模块可独立调用，如只执行数据加载或只保存结果
  3. **可扩展**: 新增模式（如优化参数、批量回测）更容易
  4. **易调试**: 问题定位到具体函数，不用在200+行的 main 中找 bug

---

## 当前待办汇总

| 序号 | 任务 | 优先级 | 状态 |
|------|------|--------|------|
| 1 | 扩展股票池至 CSI300/CSI1000 | 高 | ⏳ |
| 2 | 新增买入原因字段 | 中 | ⏳ |
| 3 | 优化 Hard Stop 卖出原因 | 低 | ⏳ |
| 4 | 拆分 main 函数 | 中 | ⏳ |

---

## Gemini 诊断优化建议

### 5. 优化选股池，注入"低位高弹"基因
- **任务**: 改进特征工程和过滤机制，寻找更具爆发力且下行空间有限的标的
- **状态**: 待评估
- **建议措施**:
  1. **增加底部放量因子**：引入特定的量价配合特征，例如寻找过去 60 天内价格处于较低分位数，但近 5 日成交量突破 60 日均量两倍以上的标的（资金建仓信号）
  2. **低价股权重倾斜**：在市值和价格因子中，给予绝对价格较低的股票更高的得分权重（低价股上行弹性通常大于高价白马股）
  3. **严格剔除近期涨停股**：增加对过去 3-5 个交易日内触及过涨停板（日收益率 ≥ 9.8%）个股的硬性过滤，防范追高风险

### 6. 修复回测引擎的"自欺欺人"
- **任务**: 重构撮合逻辑，更真实模拟实盘交易
- **状态**: 待评估
- **问题**: 当前回测可能过于乐观，未充分考虑开盘跳空和滑点
- **建议措施**:
  1. **加入开盘价判断**：如果次日开盘价直接低于 `cost * (1 - HARD_STOP_LOSS)`，强制以开盘价（或跌停价无法成交递延至下一日）计算亏损
  2. **增加滑点冲击成本**：在成本中加入至少 2‰ 的滑点冲击成本

### 7. 强制隔离特征，拯救集成学习
- **任务**: 解决 XGBoost 权重 100%、集成学习失效的问题
- **状态**: 待评估
- **建议措施**:
  - **模型 A（XGBoost）**：专注于动量类和成交量类因子，负责进攻，寻找高弹性标的
  - **模型 B（LightGBM）**：专注于波动率类、布林带及市值偏离因子，负责防守和均值回归
  - **强制组合公式**：`Score = 0.7 * Score_A + 0.3 * Score_B`，哪怕回测分数降低，实盘的鲁棒性也会大幅提升

### 8. 引入行业中性化（迫在眉睫）
- **任务**: 解决行业集中风险，避免过度暴露于单一板块
- **状态**: 待评估
- **建议措施**:
  1. 对预测出的 `pred` 得分进行行业内的 Z-Score 标准化
  2. 确保选出的 Top 30 股票均匀分布在 5-8 个表现最强势的行业中
  3. 避免全部扎堆在某一个短期过热的板块

---

## 优化建议优先级评估

| 建议 | 实施难度 | 预期效果 | 优先级 |
|------|---------|---------|--------|
| 行业中性化 | 中 | 大幅降低回撤 | 🔴 高 |
| 修复回测引擎 | 中 | 更真实评估策略 | 🔴 高 |
| 特征隔离 | 高 | 提升模型鲁棒性 | 🟠 中 |
| 低位高弹基因 | 中 | 提升收益弹性 | 🟡 中 |
