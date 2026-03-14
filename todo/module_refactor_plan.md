# Main.py 模块拆分方案

## 当前代码结构分析

main.py 共 760 行，包含以下核心组件：

```
├── 全局配置 (CONFIG, RISK_CONFIG, PARAMS)
├── DataFetcher 类 (数据获取)
├── load_v7_model (模型加载)
├── calculate_features (特征工程)
├── predict_ensemble (预测)
├── detect_market_regime (市场环境检测)
├── run_backtest (回测逻辑)
└── main (主函数)
```

## 目标架构

```
project/
├── config/
│   └── settings.py          # 全局配置
├── data/
│   └── 01_data_prepare.py   # 数据准备
├── features/
│   └── 02_feature_engineering.py  # 特征工程
├── models/
│   └── 03_model_train.py    # 模型加载与预测
├── backtest/
│   └── 04_backtest.py       # 回测引擎
├── strategy/
│   └── 05_select_stocks.py  # 选股生成
└── workflow/
    └── 06_daily_workflow.py # 每日自动流程
```

## 模块详细设计

### 1. config/settings.py
**职责**：集中管理所有配置参数

**内容**：
```python
# API 配置
TUSHARE_TOKEN = "..."

# 路径配置
CACHE_PATH = './data/cache'
MODEL_DIR = './models'
RESULTS_DIR = './results'

# 风控配置
RISK_CONFIG = {...}

# 市场状态参数
PARAMS = {...}

# 交易参数
HARD_STOP_LOSS = -0.08
SCENARIOS = {...}
```

**被依赖**：所有其他模块

---

### 2. data/01_data_prepare.py
**职责**：数据获取和缓存管理

**内容**：
```python
class DataFetcher:
    """Tushare数据获取器"""
    def __init__(self, token, cache_path): ...
    def get_stock_list(self, market): ...
    def get_daily_price(self, ts_code, start, end): ...
    def get_daily_prices_batch(self, stocks, start, end): ...
    def load_data_extended(self, start, end, market): ...
```

**输入**：API Token, 日期范围, 股票池类型
**输出**：price_df, stock_names, stock_industries, stock_tscodes

**被依赖**：backtest.py, select_stocks.py, daily_workflow.py

---

### 3. features/02_feature_engineering.py
**职责**：计算 53 个特征

**内容**：
```python
def calculate_features(price_df):
    """计算v7增强版特征 (53个特征)"""
    # 价格动量因子
    # 波动率因子
    # 均线因子
    # 布林带
    # RSI
    # MACD
    # 成交量因子
    # ...
    return df

def get_feature_cols():
    """获取v7特征列列表"""
    return [...]
```

**输入**：price_df (原始价格数据)
**输出**：feature_df (带特征的数据)

**被依赖**：backtest.py, select_stocks.py
**依赖**：无 (纯计算模块)

---

### 4. models/03_model_train.py
**职责**：模型加载和预测

**内容**：
```python
def load_v7_model(pool_type='csi500'):
    """加载v7模型"""
    ...
    return models, weights, feature_cols

def predict_ensemble(models, weights, df, feature_cols):
    """集成预测"""
    ...
    return ensemble_pred, predictions
```

**输入**：股票池类型
**输出**：模型对象、权重、特征列

**被依赖**：backtest.py, select_stocks.py
**依赖**：settings.py

---

### 5. backtest/04_backtest.py
**职责**：回测引擎核心逻辑

**内容**：
```python
def detect_market_regime(price_df, date):
    """检测市场环境"""
    ...

def run_backtest(price_df, models, weights, feature_cols,
                 stock_names, stock_industries, pool_type,
                 start_date, end_date):
    """运行回测"""
    # 1. 计算特征
    # 2. 预测
    # 3. 每日循环：
    #    - 检测市场状态
    #    - 卖出逻辑 (Hard Stop / Trailing Stop / Rank Exit)
    #    - 买入逻辑
    #    - 记录持仓
    # 4. 清仓
    # 5. 计算收益指标
    return result, trades_df, pf
```

**输入**：价格数据、模型、日期范围
**输出**：回测结果、交易记录、每日持仓

**依赖**：
- settings.py (配置参数)
- data_prepare.py (DataFetcher - 如果需要重新加载数据)
- feature_engineering.py (calculate_features)
- model_train.py (predict_ensemble)

---

### 6. strategy/05_select_stocks.py
**职责**：基于预测生成选股列表

**内容**：
```python
def generate_stock_selection(price_df, models, weights, feature_cols,
                             stock_names, stock_industries, top_n=20):
    """生成选股推荐"""
    # 1. 计算特征
    # 2. 预测
    # 3. 排序取 Top N
    # 4. 格式化输出
    return selected_stocks

def display_selection(selected_stocks):
    """展示选股结果"""
    ...

def save_selection(selected_stocks, output_path):
    """保存选股结果"""
    ...
```

**输入**：价格数据、模型
**输出**：Top N 股票列表

**依赖**：
- settings.py
- feature_engineering.py
- model_train.py

---

### 7. workflow/06_daily_workflow.py
**职责**：主入口，协调各模块完成每日任务

**内容**：
```python
def parse_args():
    """解析命令行参数"""
    ...

def main():
    """主函数"""
    # 1. 解析参数
    args = parse_args()

    # 2. 初始化
    fetcher = DataFetcher(...)
    models, weights, feature_cols = load_v7_model(args.pool)

    # 3. 加载数据
    price_df, stock_names, stock_industries, _ = fetcher.load_data_extended(...)

    # 4. 根据模式执行
    if args.mode == 'backtest':
        result, trades, pf = run_backtest(...)
        save_results(...)
    elif args.mode == 'predict':
        selected = generate_stock_selection(...)
        display_selection(selected)
        save_selection(selected)

if __name__ == "__main__":
    main()
```

**依赖**：所有其他模块

---

## 新增模块：交易执行模块 (execution/04_trade_execution.py)

**职责**：封装所有交易相关操作，包括买入、卖出、风控检查、仓位管理

**为什么独立**：
1. **复用性**：回测和实盘共用同一套交易逻辑
2. **可测试性**：可以单独测试交易规则
3. **清晰度**：将交易细节从回测循环中剥离

**核心类设计**：

```python
class TradeExecutor:
    """交易执行器"""

    def __init__(self, risk_config, scenarios):
        """
        初始化交易执行器

        Args:
            risk_config: 风控配置
            scenarios: 交易成本配置
        """
        self.risk_config = risk_config
        self.scenarios = scenarios

    def calculate_position_size(self, cash, slots, portfolio_value, price, max_per_stock):
        """
        计算买入股数

        Args:
            cash: 可用现金
            slots: 剩余持仓槽位
            portfolio_value: 当前组合价值
            price: 当前股价
            max_per_stock: 单只股票最大仓位比例

        Returns:
            shares: 可买入股数（已取整到100的倍数）
        """
        max_position_value = portfolio_value * max_per_stock
        planned = min(cash * 0.95 / max(slots, 1), max_position_value)
        shares = int(planned / price / 100) * 100
        return shares

    def execute_buy(self, symbol, price, date, cash, positions, industry_exposure,
                    pred_rank, pred_score, regime, stock_industries, cfg):
        """
        执行买入操作

        Args:
            symbol: 股票代码
            price: 买入价格
            date: 买入日期
            cash: 可用现金
            positions: 当前持仓字典
            industry_exposure: 行业敞口字典
            pred_rank: 预测排名
            pred_score: 预测得分
            regime: 当前市场状态
            stock_industries: 股票行业映射
            cfg: 当前市场状态下的配置参数

        Returns:
            success: 是否成功买入
            cost: 实际花费（含手续费）
            position_info: 新持仓信息
            updated_cash: 更新后的现金
            updated_industry_exposure: 更新后的行业敞口
        """
        # 1. 风控检查 - 日涨幅限制
        if row.get('return_1d', 0) > cfg['max_daily_return']:
            return False, 0, None, cash, industry_exposure

        # 2. 风控检查 - 均线偏离
        if row.get('deviation_from_ma5', 0) > cfg['max_ma5_deviation']:
            return False, 0, None, cash, industry_exposure

        # 3. 风控检查 - 行业集中度
        ind = stock_industries.get(symbol, '其他')
        current_ind = industry_exposure.get(ind, 0)
        if current_ind >= self.risk_config['max_position_per_industry']:
            return False, 0, None, cash, industry_exposure

        # 4. 计算买入股数
        portfolio_value = sum(pos['shares'] * price for pos in positions.values()) + cash
        shares = self.calculate_position_size(
            cash,
            self.risk_config['max_positions'] - len(positions),
            portfolio_value,
            price,
            self.risk_config['max_position_per_stock']
        )

        if shares < 100:
            return False, 0, None, cash, industry_exposure

        # 5. 计算成本（含手续费）
        cost = shares * price * (1 + self.scenarios['normal']['buy_cost'])

        if cost > cash:
            return False, 0, None, cash, industry_exposure

        # 6. 创建持仓记录
        buy_signal_detail = f"Rank {pred_rank:.2%}, Score {pred_score:.4f}, {regime}"
        position_info = {
            'shares': shares,
            'cost': price,
            'entry_date': date,
            'industry': ind,
            'highest_price': price,
            'highest_pnl': 0,
            'buy_signal': f"Rank {pred_rank:.2%}",
            'buy_reason': buy_signal_detail,
            'market_regime_at_entry': regime,
        }

        # 7. 更新现金和行业敞口
        updated_cash = cash - cost
        updated_industry_exposure = industry_exposure.copy()
        updated_industry_exposure[ind] = current_ind + shares * price / portfolio_value

        return True, cost, position_info, updated_cash, updated_industry_exposure

    def check_exit_conditions(self, pos, current_price, days, regime, cfg, day_data):
        """
        检查卖出条件

        Args:
            pos: 持仓信息
            current_price: 当前价格
            days: 持有天数
            regime: 当前市场状态
            cfg: 当前市场状态下的配置参数
            day_data: 当日数据（用于获取排名）

        Returns:
            should_sell: 是否应该卖出
            reason: 卖出原因
            pnl: 当前盈亏比例
        """
        # 计算当前盈亏
        pnl = (current_price - pos['cost']) / pos['cost']

        # 更新最高价格和最高盈亏
        highest_price = max(pos.get('highest_price', pos['cost']), current_price)
        highest_pnl = max(pos.get('highest_pnl', 0), pnl)

        # 1. Hard Stop - 硬性止损
        if pnl <= -0.08:  # HARD_STOP_LOSS
            return True, f"{regime} Hard stop ({pnl:.1%})", pnl

        # 2. Trailing Stop - 移动止损
        if current_price < highest_price * (1 - cfg['trailing_stop']):
            pullback = (highest_price - current_price) / highest_price
            return True, f"{regime} trailing stop ({pullback * 100:.1f}%)", pnl

        # 3. Rank Exit - 排名退出
        if days >= cfg['min_holding_days'] and highest_pnl <= 0.20:
            current_rank = day_data[day_data['symbol'] == pos['symbol']]['pred_rank'].values
            if len(current_rank) > 0 and current_rank[0] > cfg['rank_exit_threshold']:
                return True, f"{regime} rank exit ({current_rank[0] * 100:.1f}%)", pnl

        return False, None, pnl

    def execute_sell(self, pos, current_price, date, cash, regime, reason):
        """
        执行卖出操作

        Args:
            pos: 持仓信息
            current_price: 卖出价格
            date: 卖出日期
            cash: 当前现金
            regime: 市场状态
            reason: 卖出原因

        Returns:
            trade_record: 交易记录字典
            updated_cash: 更新后的现金
            profit: 盈亏金额
        """
        # 计算卖出金额（扣除手续费）
        amount = pos['shares'] * current_price * (1 - self.scenarios['normal']['sell_cost'])

        # 计算盈亏
        profit = amount - pos['shares'] * pos['cost']

        # 计算持有天数
        days = (date - pos['entry_date']).days

        # 计算盈亏比例
        pnl = (current_price - pos['cost']) / pos['cost']

        # 生成交易记录
        trade_record = {
            '代码': pos['symbol'],
            '名称': pos.get('name', pos['symbol']),
            '行业': pos['industry'],
            '买入日期': pos['entry_date'].strftime('%Y%m%d'),
            '买入价': round(pos['cost'], 2),
            '卖出日期': date.strftime('%Y%m%d'),
            '卖出价': round(current_price, 2),
            '股数': pos['shares'],
            '盈亏金额': round(profit, 1),
            '盈亏比例': f"{pnl * 100:.2f}%",
            '持有天数': days,
            '买入信号': pos.get('buy_signal', 'Top Rank'),
            '买入原因': pos.get('buy_reason', 'Top Rank'),
            '卖出信号': reason,
            '卖出原因': reason,
            '市场状态': regime,
        }

        updated_cash = cash + amount

        return trade_record, updated_cash, profit

    def close_all_positions(self, positions, final_date, final_data, cash, stock_names):
        """
        清仓所有持仓（回测结束或强制清仓）

        Args:
            positions: 当前所有持仓
            final_date: 清仓日期
            final_data: 当日价格数据
            cash: 当前现金
            stock_names: 股票名称映射

        Returns:
            trades: 交易记录列表
            updated_cash: 清仓后的现金
        """
        trades = []

        for symbol, pos in list(positions.items()):
            price = final_data[final_data['symbol'] == symbol]['close'].values
            if len(price) > 0:
                trade_record, updated_cash, _ = self.execute_sell(
                    {**pos, 'symbol': symbol, 'name': stock_names.get(symbol, symbol)},
                    price[0],
                    final_date,
                    cash,
                    'END',
                    'Close all'
                )
                trades.append(trade_record)
                cash = updated_cash

        return trades, cash


class PortfolioTracker:
    """投资组合跟踪器"""

    def __init__(self, initial_cash):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions = {}
        self.industry_exposure = {}
        self.portfolio_values = []

    def update_portfolio_value(self, date, day_data, regime):
        """更新组合净值"""
        portfolio_value = self.cash
        for sym, pos in self.positions.items():
            price = day_data[day_data['symbol'] == sym]['close'].values
            if len(price) > 0:
                portfolio_value += pos['shares'] * price[0]

        self.portfolio_values.append({
            'date': date,
            'portfolio_value': portfolio_value,
            'cash': self.cash,
            'positions': len(self.positions),
            'market_regime': regime,
        })

        return portfolio_value

    def calculate_performance(self):
        """计算回测绩效指标"""
        df = pd.DataFrame(self.portfolio_values)
        df['cum_return'] = (df['portfolio_value'] / self.initial_cash) - 1
        df['max_drawdown'] = df['cum_return'] - df['cum_return'].cummax()

        total_return = df['cum_return'].iloc[-1]
        max_dd = df['max_drawdown'].min()

        return {
            'total_return': total_return,
            'max_drawdown': max_dd,
            'portfolio_df': df
        }
```

**依赖**：
- settings.py（风控参数）

**被依赖**：
- 04_backtest.py
- 06_daily_workflow.py（未来实盘交易）

**使用示例**：

```python
# 在回测中使用
executor = TradeExecutor(RISK_CONFIG, SCENARIOS)
portfolio = PortfolioTracker(initial_cash=200000)

for date in dates:
    day_data = test_df[test_df['date'] == date]

    # 1. 检查卖出
    for sym, pos in list(positions.items()):
        should_sell, reason, pnl = executor.check_exit_conditions(
            pos, current_price, days, regime, cfg, day_data
        )
        if should_sell:
            trade, cash, _ = executor.execute_sell(pos, current_price, date, cash, regime, reason)
            trades.append(trade)
            del positions[sym]

    # 2. 检查买入
    for _, row in top_candidates.iterrows():
        success, cost, pos_info, cash, industry_exp = executor.execute_buy(
            row['symbol'], row['close'], date, cash, positions,
            industry_exposure, row['pred_rank'], row['pred'],
            regime, stock_industries, cfg
        )
        if success:
            positions[row['symbol']] = pos_info

    # 3. 更新净值
    portfolio.update_portfolio_value(date, day_data, regime)
```

---

## 更新后的模块架构

```
project/
├── config/
│   └── settings.py              # 全局配置
├── data/
│   └── 01_data_prepare.py       # 数据准备
├── features/
│   └── 02_feature_engineering.py # 特征工程
├── models/
│   └── 03_model_train.py        # 模型加载与预测
├── execution/                   # 交易执行（新增）
│   └── 04_trade_execution.py    # 买入/卖出/风控
├── backtest/
│   └── 05_backtest.py           # 回测引擎（调用交易模块）
├── strategy/
│   └── 06_select_stocks.py      # 选股生成
└── workflow/
    └── 07_daily_workflow.py     # 每日自动流程
```

**关键变更**：
- 原 `04_backtest.py` 改为 `05_backtest.py`
- 新增 `04_trade_execution.py` 专门处理交易逻辑
- 回测模块只负责调度（每日循环），具体买卖逻辑交给交易模块

---

## 数据流图

```
┌─────────────────────────────────────────────────────────────┐
│  06_daily_workflow.py (主入口)                               │
└──────────────────┬──────────────────────────────────────────┘
                   │
    ┌──────────────┼──────────────┐
    │              │              │
    ▼              ▼              ▼
┌─────────┐ ┌─────────────┐ ┌─────────────┐
│01_data  │ │03_model     │ │02_features  │
│prepare  │ │train        │ │engineering  │
└────┬────┘ └──────┬──────┘ └──────┬──────┘
     │             │               │
     │    ┌────────┴────────┐      │
     │    │                 │      │
     └───►│ 04_backtest.py  │◄─────┘
          │                 │
          │  - run_backtest │
          └────────┬────────┘
                   │
                   ▼
          ┌─────────────────┐
          │ 05_select_stocks │
          └─────────────────┘
```

## 关键依赖关系

| 模块 | 依赖模块 | 被依赖模块 |
|------|----------|------------|
| config/settings | 无 | 所有模块 |
| 01_data_prepare | settings | 04, 05, 06 |
| 02_feature_eng | 无 | 04, 05, 06 |
| 03_model_train | settings | 04, 05, 06 |
| 04_backtest | settings, 01, 02, 03 | 06 |
| 05_select_stocks | settings, 02, 03 | 06 |
| 06_daily_workflow | 所有 | 无 |

## 拆分步骤

### Step 1: 创建目录结构
```bash
mkdir -p config data features models backtest strategy workflow
```

### Step 2: 提取 config/settings.py
- 从 main.py 提取 CONFIG、RISK_CONFIG、PARAMS
- 提取 load_env_file 函数

### Step 3: 提取 data/01_data_prepare.py
- 提取 DataFetcher 类
- 保持所有方法不变

### Step 4: 提取 features/02_feature_engineering.py
- 提取 calculate_features 函数
- 提取 get_feature_cols 函数

### Step 5: 提取 models/03_model_train.py
- 提取 load_v7_model 函数
- 提取 predict_ensemble 函数

### Step 6: 提取 backtest/04_backtest.py
- 提取 detect_market_regime 函数
- 提取 run_backtest 函数
- 注意：需要导入 settings 的配置参数

### Step 7: 提取 strategy/05_select_stocks.py
- 从 main 的 predict 模式提取逻辑
- 封装为 generate_stock_selection 函数

### Step 8: 重构 workflow/06_daily_workflow.py
- 保留 main 函数框架
- 使用 import 引用其他模块
- 保持 CLI 接口不变

## 接口设计

### 模块间共享数据结构

```python
# 数据传递格式
price_df = pd.DataFrame({
    'date': [...],
    'symbol': [...],
    'open': [...],
    'high': [...],
    'low': [...],
    'close': [...],
    'volume': [...],
    'amount': [...]
})

# 回测结果
backtest_result = {
    'pool': str,
    'total_return': float,
    'max_drawdown': float,
    'win_rate': float,
    'profit_factor': float,
    'total_trades': int,
    'avg_holding_days': float
}

# 交易记录
trades_df = pd.DataFrame({
    '代码': [...],
    '名称': [...],
    '买入日期': [...],
    '卖出日期': [...],
    '盈亏金额': [...],
    ...
})
```

## 命令行接口保持不变

```bash
# 回测模式
python3 -m workflow.06_daily_workflow --start 2025-01-01 --end 2025-12-31 --pool csi500 --mode backtest

# 预测模式
python3 -m workflow.06_daily_workflow --pool csi500 --mode predict
```

或者使用简化入口：

```bash
# 创建 run.py 作为快捷入口
python3 run.py --start 2025-01-01 --end 2025-12-31 --pool csi500 --mode backtest
```

## 注意事项

1. **循环依赖**：避免模块间循环引用
2. **配置传递**：通过 config/settings.py 共享配置
3. **日志处理**：保持统一的 logger 配置
4. **异常处理**：各模块保持原有的错误处理逻辑
5. **性能考虑**：避免重复计算（如特征计算应在各模块间缓存）

## 后续优化

拆分后可进行的优化：
1. 为每个模块添加单元测试
2. 使用 __init__.py 简化导入
3. 添加类型注解
4. 实现特征缓存机制
5. 添加并行计算支持
