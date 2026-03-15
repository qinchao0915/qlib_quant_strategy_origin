# 量化策略架构设计方案

> 设计目标：支持多版本并行开发、避免垃圾文件、易于维护

---

## 推荐架构：分层 + 版本管理

```
qlib_quant_strategy_origin/
│
├── core/                          # 核心层（稳定，跨版本复用）
│   ├── __init__.py
│   ├── data/                      # 数据获取
│   │   ├── __init__.py
│   │   └── fetcher.py             # DataFetcher类
│   │
│   ├── features/                  # 特征工程
│   │   ├── __init__.py
│   │   └── engineering.py         # calculate_features等
│   │
│   ├── models/                    # 模型基础
│   │   ├── __init__.py
│   │   └── base.py                # 模型加载、预测基类
│   │
│   └── utils/                     # 工具函数（已创建）
│       ├── __init__.py
│       ├── logger.py
│       ├── math_utils.py
│       └── ...
│
├── strategies/                    # 策略层（版本化管理）
│   │
│   ├── v7_2025/                   # V7版本（当前生产版本）
│   │   ├── __init__.py
│   │   ├── config.py              # 版本专属配置
│   │   ├── model.py               # 模型定义（继承core.models）
│   │   ├── backtest.py            # 回测逻辑
│   │   ├── signals.py             # 信号生成
│   │   └── workflow.py            # 工作流编排
│   │
│   ├── v8_alpha/                  # V8版本（Alpha方向实验）
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── model.py               # LambdaRank等
│   │   ├── backtest.py
│   │   └── ...
│   │
│   └── v9_neutral/                # V9版本（中性化方向实验）
│       └── ...
│
├── experiments/                   # 实验层（临时、探索性）
│   ├── 20250315_test_lambdarank/  # 按日期命名实验
│   ├── 20250320_test_transformer/
│   └── archive/                   # 归档旧实验
│
├── tests/                         # 测试层
│   ├── unit/                      # 单元测试
│   ├── integration/               # 集成测试
│   └── test_data/                 # 测试数据
│
├── scripts/                       # 脚本层（一次性任务）
│   ├── download_data.py           # 数据下载
│   ├── evaluate_model.py          # 模型评估
│   └── generate_report.py         # 报告生成
│
├── notebooks/                     # 分析笔记本
│   ├── exploration/               # 探索性分析
│   └── reports/                   # 结果报告
│
├── data/                          # 数据目录
│   ├── raw/                       # 原始数据
│   ├── processed/                 # 处理后数据
│   └── cache/                     # 缓存
│
├── models/                        # 模型文件
│   ├── v7_2025/
│   ├── v8_alpha/
│   └── archive/
│
├── results/                       # 结果输出
│   ├── v7_2025/
│   ├── v8_alpha/
│   └── archive/
│
├── docs/                          # 文档
│   ├── architecture/              # 架构文档
│   ├── api/                       # API文档
│   └── experiments/               # 实验记录
│
├── config/                        # 全局配置（已创建）
│   └── settings.py
│
├── main.py                        # 入口文件（保留，调用最新稳定版）
├── main_v7.py                     # V7专用入口
├── main_v8.py                     # V8专用入口
├── requirements.txt
└── README.md
```

---

## 核心设计原则

### 1. 三层架构

| 层级 | 稳定性 | 复用性 | 示例 |
|------|--------|--------|------|
| **Core** | 高 | 跨版本 | DataFetcher, calculate_features |
| **Strategy** | 中 | 版本内 | V7的模型、回测逻辑 |
| **Experiment** | 低 | 一次性 | 临时测试、探索 |

### 2. 版本管理

```python
# 版本切换示例
from strategies.v7_2025 import workflow as v7_workflow
from strategies.v8_alpha import workflow as v8_workflow

# 运行V7
v7_workflow.run_backtest(start='2025-01-01', end='2025-12-31')

# 运行V8
v8_workflow.run_backtest(start='2025-01-01', end='2025-12-31')
```

### 3. 避免垃圾文件

| 规则 | 说明 |
|------|------|
| **实验必须归档** | experiments/下的文件夹超过30天自动移入archive/ |
| **结果按版本存放** | 不允许results/根目录堆积文件 |
| **模型版本化** | 每个版本有自己的models/子目录 |
| **脚本功能单一** | 一个脚本只做一件事，用完即走 |

### 4. 文件命名规范

```
✅ 正确:
  - v7_2025_backtest.py          # 版本_功能
  - 20250315_test_lambdarank/    # 日期_描述
  - evaluate_model.py            # 动词_名词

❌ 错误:
  - test.py                      # 太泛
  - temp.py                      # 临时文件
  - main_v2_v3_final.py          # 版本混乱
```

---

## 对比方案

### 方案A：Workflow文件夹（不推荐）
```
workflow/
  ├── step1_data.py
  ├── step2_features.py
  ├── step3_model.py
  └── step4_backtest.py
```
**问题**：
- 版本混乱（V7/V8/V9混在一起）
- 文件膨胀（不断添加step5, step6...）
- 难以回滚（改了一个文件影响所有版本）

### 方案B：分层+版本（推荐）
```
core/              # 稳定，不常变
strategies/
  ├── v7_2025/     # 独立版本
  ├── v8_alpha/    # 独立版本
  └── v9_neutral/  # 独立版本
```
**优点**：
- 版本隔离（互不影响）
- 清晰演进（V7稳定，V8实验）
- 易于回滚（直接切换版本）
- 团队协作（不同人负责不同版本）

---

## 实施建议

### 阶段1：整理现有代码（今天）
1. 创建 `core/` 目录，放入稳定代码
2. 创建 `strategies/v7_2025/`，放入当前生产代码
3. 保留 `main.py` 作为V7入口

### 阶段2：开发新版本（本周）
1. 创建 `strategies/v8_alpha/`
2. 继承 `core/` 的基础功能
3. 专注Alpha预测实验

### 阶段3：实验管理（持续）
1. 所有临时实验放入 `experiments/日期_描述/`
2. 定期归档旧实验
3. 成功的实验提升为 `strategies/vX_名称/`

---

## 你的选择？

| 选项 | 适用场景 |
|------|----------|
| **A. 快速整理** | 先按workflow整理，后续再重构 |
| **B. 完整重构** | 直接实施分层+版本架构 |
| **C. 混合方案** | 先创建core/，保留main.py，逐步迁移 |

**我的建议**：选 **C. 混合方案**
- 风险低（保留现有代码）
- 收益高（逐步建立好架构）
- 可持续（边用边改）

你觉得呢？
