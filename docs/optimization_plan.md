# v7_2025 策略优化实施计划

**基于**: [量化策略诊断模型v7.md](量化策略诊断模型v7.md)
**目标**: 实现年化 Alpha > 20% 且最大回撤 < 15%
**制定日期**: 2026-03-15

---

## 📋 执行路线图

```
阶段1: 清洗回测环境 (Week 1-2)
    ├─ 滚动窗口训练框架
    └─ 撮合引擎重构

阶段2: 因子中性化 (Week 3-4)
    ├─ 行业中性化
    └─ 风格因子正交化

阶段3: 模型异构集成 (Week 5-6)
    ├─ 子模型A (趋势跟随)
    ├─ 子模型B (反转与价值)
    └─ 集成权重优化

阶段4: 架构解耦 (Week 7-8)
    ├─ DataFetcher 独立
    ├─ FeatureEngine 独立
    ├─ ModelInference 独立
    └─ BacktestEngine 独立
```

---

## 🚨 阶段1: 清洗回测环境（优先级：极高）

### 1.1 滚动窗口训练框架

**目标**: 废除全局静态模型，消除前瞻偏差

**具体任务**:
- [ ] 修改 `train/v7_2025/train.py` 支持滚动窗口
- [ ] 实现 Walk-Forward 训练逻辑
  ```python
  # 训练窗口配置
  TRAIN_WINDOWS = [
      ("2016-01-01", "2019-12-31", "2020-01-01", "2020-12-31"),
      ("2017-01-01", "2020-12-31", "2021-01-01", "2021-12-31"),
      ("2018-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
      ("2019-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
      ("2020-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
  ]
  ```
- [ ] 每个窗口独立训练模型并保存
- [ ] 实现模型切换逻辑（按日期自动选择对应模型）

**验收标准**:
- 能够按年份滚动训练5个独立模型
- 回测时自动加载对应时间段的模型
- 无数据泄露（训练集日期严格早于测试集）

**预估工时**: 3-4天

---

### 1.2 撮合引擎重构

**目标**: 使用次日开盘价成交，加入涨跌停过滤

**具体任务**:
- [ ] 修改 `workflow.py` 中的 `run_backtest_strategy` 函数
- [ ] 买入价改为次日开盘价 (`next_open`)
  ```python
  # 当前问题代码
  current_price = price_data[0]  # 使用当日close

  # 修改后
  next_day_data = get_next_day_data(sym, date)
  if next_day_data is None or next_day_data['volume'] == 0:
      continue  # 无法成交
  fill_price = next_day_data['open']
  ```
- [ ] 添加涨跌停判断
  ```python
  def can_trade(stock_data):
      """判断是否可以成交"""
      if stock_data['volume'] == 0:
          return False  # 无量跌停/涨停
      if abs(stock_data['pct_change']) > 0.095:  # 接近涨跌停
          return False
      return True
  ```
- [ ] 更新成本计算（滑点从 0.03%/0.13% 调整为 0.2%/0.2%）

**验收标准**:
- 所有买入操作使用次日开盘价
- 涨跌停股票无法成交
- 滑点成本调整后的回测收益率下降不超过30%

**预估工时**: 2-3天

---

## 🔬 阶段2: 因子中性化与 Alpha 纯化（优先级：极高）

### 2.1 行业中性化

**目标**: 消除行业集中风险，实现行业均匀分散

**具体任务**:
- [ ] 在 `core/features/engineering.py` 中添加中性化函数
  ```python
  def neutralize_factor(self, df, factor_col, group_col='industry'):
      """
      行业中性化处理
      Factor_neutral = (Factor - Mean(Industry)) / Std(Industry)
      """
      def _zscore_within_group(x):
          return (x - x.mean()) / (x.std() + 1e-8)

      df[f'{factor_col}_neutral'] = df.groupby(group_col)[factor_col].transform(_zscore_within_group)
      return df
  ```
- [ ] 对 53 个因子全部进行行业中性化处理
- [ ] 修改选股逻辑，使用中性化后的因子
- [ ] 添加行业集中度检查（确保 Top 30 均匀分布于各行业）

**验收标准**:
- 回测结果中行业集中度 < 15%
- 单一行业持仓不超过 3 只股票
- 最大回撤降低 20% 以上

**预估工时**: 3-4天

---

### 2.2 风格因子正交化

**目标**: 剥离市值、波动率等风格暴露

**具体任务**:
- [ ] 实现风格因子回归剥离
  ```python
  def orthogonalize_factor(self, df, factor_col, style_factors=['market_cap', 'volatility_20d', 'beta']):
      """
      对目标因子进行风格正交化
      去除市值、波动率、Beta等风格暴露
      """
      from sklearn.linear_model import LinearRegression

      df_clean = df.dropna(subset=[factor_col] + style_factors)

      X = df_clean[style_factors]
      y = df_clean[factor_col]

      model = LinearRegression().fit(X, y)
      residuals = y - model.predict(X)

      df_clean[f'{factor_col}_pure'] = residuals
      return df_clean
  ```
- [ ] 针对 Size Factor（市值）进行重点剥离
- [ ] 验证 Alpha 的纯粹性（跨股票池表现一致性）

**验收标准**:
- CSI300 与 CSI500 收益率差异缩小至 20% 以内
- 策略 Beta 值降低至 0.8 以下

**预估工时**: 2-3天

---

## 🧠 阶段3: 拯救模型组合（优先级：高）

### 3.1 子模型A - 趋势跟随模型

**目标**: 专门捕捉动量趋势

**具体任务**:
- [ ] 定义趋势跟随特征集
  ```python
  TREND_FEATURES = [
      # 动量类
      'momentum_5d', 'momentum_10d', 'momentum_20d', 'momentum_60d',
      # 均线类
      'ma5', 'ma10', 'ma20', 'ma60',
      'deviation_from_ma5', 'deviation_from_ma20', 'deviation_from_ma60',
      # MACD
      'macd', 'macd_signal', 'macd_hist',
      # 趋势强度
      'adx', 'plus_di', 'minus_di',
  ]
  ```
- [ ] 使用趋势特征子集训练 LightGBM 模型
- [ ] 使用趋势特征子集训练 XGBoost 模型
- [ ] 模型参数调优（更保守的学习率）

**预估工时**: 2-3天

---

### 3.2 子模型B - 反转与价值模型

**目标**: 专门捕捉均值回归和价值机会

**具体任务**:
- [ ] 定义反转价值特征集
  ```python
  REVERSION_FEATURES = [
      # 反转类
      'rsi_6', 'rsi_14', 'rsi_24',
      'cci_20', 'williams_r',
      # 波动率类
      'volatility_5d', 'volatility_20d', 'volatility_60d',
      'atr_14', 'atr_24',
      # 布林带
      'bb_position', 'bb_width',
      'bb_upper_dist', 'bb_lower_dist',
      # 量价背离
      'volume_price_divergence',
      # 换手率
      'turnover_5d', 'turnover_20d',
  ]
  ```
- [ ] 使用反转特征子集训练 LightGBM 模型
- [ ] 使用反转特征子集训练 XGBoost 模型
- [ ] 模型参数调优（更深的树深度捕捉非线性）

**预估工时**: 2-3天

---

### 3.3 异构集成与权重优化

**目标**: 强制子模型共存，防止单一模型垄断

**具体任务**:
- [ ] 实现静态权重集成（禁止动态IC权重）
  ```python
  # 强制异构集成权重
  ENSEMBLE_WEIGHTS = {
      'trend_lgbm': 0.30,
      'trend_xgb': 0.30,
      'reversion_lgbm': 0.20,
      'reversion_xgb': 0.20,
  }
  ```
- [ ] 或实现逻辑回归集成层
  ```python
  from sklearn.linear_model import LogisticRegression

  def train_meta_learner(self, predictions_dict, y_true):
      """训练元学习器进行集成"""
      X_meta = np.column_stack([
          predictions_dict['trend_lgbm'],
          predictions_dict['trend_xgb'],
          predictions_dict['reversion_lgbm'],
          predictions_dict['reversion_xgb'],
      ])

      meta_model = LogisticRegression()
      meta_model.fit(X_meta, y_true)
      return meta_model
  ```
- [ ] 验证集成多样性（子模型预测相关性 < 0.7）

**验收标准**:
- 4个子模型都有非零贡献
- 预测相关性矩阵显示低相关性
- 集成IC > 单一模型IC

**预估工时**: 2-3天

---

## 🏗️ 阶段4: 工程架构解耦（优先级：中）

### 4.1 DataFetcher 独立模块

**目标**: 数据获取层完全独立

**具体任务**:
- [ ] 创建 `core/data/data_fetcher.py` Class
  ```python
  class DataFetcher:
      """独立的数据获取模块"""

      def __init__(self, token, cache_path):
          self.token = token
          self.cache = CacheManager(cache_path)
          self.pro = ts.pro_api(token)

      def fetch_stock_list(self, pool_type):
          """获取股票列表"""
          pass

      def fetch_price_data(self, symbol, start_date, end_date):
          """获取价格数据"""
          pass

      def fetch_industry_data(self, symbols):
          """获取行业分类"""
          pass
  ```
- [ ] 所有数据访问统一通过 DataFetcher
- [ ] 实现数据缓存管理

**预估工时**: 2天

---

### 4.2 FeatureEngine 独立模块

**目标**: 因子计算层完全独立

**具体任务**:
- [ ] 创建 `core/features/feature_engine.py` Class
  ```python
  class FeatureEngine:
      """独立的因子计算模块"""

      def __init__(self, config=None):
          self.config = config or DEFAULT_FEATURE_CONFIG
          self.neutralizer = FactorNeutralizer()

      def calculate_features(self, price_df):
          """计算所有特征"""
          pass

      def neutralize_features(self, df, method='industry'):
          """因子中性化"""
          pass

      def get_feature_matrix(self, df):
          """获取特征矩阵用于模型输入"""
          pass
  ```
- [ ] 支持配置化特征选择
- [ ] 支持特征缓存

**预估工时**: 2天

---

### 4.3 ModelInference 独立模块

**目标**: 模型推理层完全独立

**具体任务**:
- [ ] 创建 `core/models/model_inference.py` Class
  ```python
  class ModelInference:
      """独立的模型推理模块"""

      def __init__(self, model_path, ensemble_config):
          self.models = self._load_models(model_path)
          self.ensemble_weights = ensemble_config

      def predict(self, feature_matrix):
          """执行预测"""
          predictions = {}
          for name, model in self.models.items():
              predictions[name] = model.predict(feature_matrix)

          # 集成预测
          ensemble_pred = self._ensemble_predictions(predictions)
          return ensemble_pred, predictions

      def _ensemble_predictions(self, predictions):
          """多模型集成"""
          pass
  ```
- [ ] 支持动态模型切换
- [ ] 支持批量预测和实时预测

**预估工时**: 2天

---

### 4.4 BacktestEngine 独立模块

**目标**: 回测执行层完全独立

**具体任务**:
- [ ] 创建 `core/backtest/backtest_engine.py` Class
  ```python
  class BacktestEngine:
      """独立的回测引擎"""

      def __init__(self, config):
          self.config = config
          self.position_manager = PositionManager()
          self.risk_manager = RiskManager()
          self.execution_engine = ExecutionEngine()

      def run_backtest(self, signals_df, start_date, end_date):
          """执行回测"""
          pass

      def get_trades(self):
          """获取交易记录"""
          pass

      def get_portfolio_values(self):
          """获取净值曲线"""
          pass

      def get_metrics(self):
          """获取绩效指标"""
          pass
  ```
- [ ] 支持多种撮合模式（开盘价/收盘价/VWAP）
- [ ] 支持多种风控规则

**预估工时**: 3天

---

## 📅 总体时间规划

| 阶段 | 任务 | 预估工时 | 开始日期 | 结束日期 |
|------|------|----------|----------|----------|
| **阶段1** | 清洗回测环境 | **5-7天** | 2026-03-17 | 2026-03-23 |
| | 1.1 滚动窗口训练 | 3-4天 | | |
| | 1.2 撮合引擎重构 | 2-3天 | | |
| **阶段2** | 因子中性化 | **5-7天** | 2026-03-24 | 2026-03-30 |
| | 2.1 行业中性化 | 3-4天 | | |
| | 2.2 风格正交化 | 2-3天 | | |
| **阶段3** | 异构集成 | **6-9天** | 2026-03-31 | 2026-04-08 |
| | 3.1 趋势模型 | 2-3天 | | |
| | 3.2 反转模型 | 2-3天 | | |
| | 3.3 集成优化 | 2-3天 | | |
| **阶段4** | 架构解耦 | **9天** | 2026-04-09 | 2026-04-17 |
| | 4.1 DataFetcher | 2天 | | |
| | 4.2 FeatureEngine | 2天 | | |
| | 4.3 ModelInference | 2天 | | |
| | 4.4 BacktestEngine | 3天 | | |

**总计**: 约 **25-32 个工作日**（6-7周）

---

## ✅ 里程碑检查点

### Checkpoint 1 (Week 2): 回测环境清洗完成
- [ ] 滚动窗口训练可正常运行
- [ ] 撮合引擎使用次日开盘价
- [ ] 涨跌停过滤生效

### Checkpoint 2 (Week 4): 因子中性化完成
- [ ] 所有因子行业中性化
- [ ] 风格因子正交化
- [ ] 行业集中度 < 15%

### Checkpoint 3 (Week 6): 异构集成完成
- [ ] 4个子模型训练完成
- [ ] 集成权重非零
- [ ] CSI300/CSI500 收益差异 < 20%

### Checkpoint 4 (Week 8): 架构解耦完成
- [ ] 4个独立模块可用
- [ ] 单元测试覆盖率 > 80%
- [ ] 实盘API对接就绪

---

## 🎯 预期效果

完成全部优化后，策略应达到以下指标：

| 指标 | 优化前 | 优化后目标 | 改进幅度 |
|------|--------|-----------|----------|
| 年化 Alpha | ~15% | > 20% | +33% |
| 最大回撤 | -15% ~ -20% | < -15% | 风险降低 |
| 夏普比率 | ~0.8 | > 1.5 | +87% |
| 跨股票池一致性 | 差异大 | 差异 < 20% | 更稳健 |
| 滑点敏感度 | 高 | 低 | 更真实 |

---

## 📝 相关文档

- [量化策略诊断模型v7.md](量化策略诊断模型v7.md)
- [回测报告 2026 Q1](../model_docs/backtest_report_2026q1.md)
- [架构提案](../architecture_docs/architecture_proposal.md)

---

*计划制定: 2026-03-15*
*版本: v1.0*
*负责人: [待填写]*
