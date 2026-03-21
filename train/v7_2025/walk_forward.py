"""
v7_2025 Walk-Forward 训练与评估

目标:
- 训练窗 4 年，测试/交易窗 1 年
- 覆盖测试年份 2020-2025
- 输出每个窗口的年化收益、最大回撤、胜率、换手、IC

使用示例:
    python3 train/v7_2025/walk_forward.py --pool csi500
"""

import argparse
import importlib.util
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

try:
    from lightgbm import LGBMRegressor
except Exception:  # pragma: no cover - runtime fallback
    LGBMRegressor = None

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import CACHE_PATH, TUSHARE_TOKEN
from core.data.fetcher import DataFetcher
from core.features.engineering import FeatureEngineer
from core.utils.logger import logger
from strategies.v7_2025.strategy import V7Strategy
from workflow import run_backtest_strategy

SKLEARN_AVAILABLE = importlib.util.find_spec("sklearn") is not None


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="v7_2025 Walk-Forward 训练与评估")
    parser.add_argument("--pool", type=str, default="csi500",
                        choices=["csi300", "csi500", "csi1000"],
                        help="股票池")
    parser.add_argument("--test-start-year", type=int, default=2020,
                        help="滚动测试开始年份")
    parser.add_argument("--test-end-year", type=int, default=2025,
                        help="滚动测试结束年份")
    parser.add_argument("--train-years", type=int, default=4,
                        help="训练窗口长度（年）")
    parser.add_argument("--sell-price", type=str, default="open",
                        choices=["open", "close"],
                        help="卖出价格类型")
    parser.add_argument("--results-dir", type=str, default="results/walk_forward",
                        help="滚动评估结果目录")
    parser.add_argument("--models-dir", type=str, default="models/walk_forward",
                        help="滚动训练模型目录")
    return parser.parse_args()


def build_windows(test_start_year: int, test_end_year: int, train_years: int):
    """构建滚动窗口"""
    windows = []
    for test_year in range(test_start_year, test_end_year + 1):
        train_start_year = test_year - train_years
        train_end_year = test_year - 1
        windows.append({
            "test_year": test_year,
            "train_start": f"{train_start_year}-01-01",
            "train_end": f"{train_end_year}-12-31",
            "test_start": f"{test_year}-01-01",
            "test_end": f"{test_year}-12-31",
        })
    return windows


def date_mask(df: pd.DataFrame, start_date: str, end_date: str):
    """按日期区间过滤"""
    return (df["date"] >= pd.to_datetime(start_date)) & (df["date"] <= pd.to_datetime(end_date))


def calculate_daily_ic(df: pd.DataFrame, pred_col: str = "pred", label_col: str = "label"):
    """按交易日计算 Spearman IC"""
    ics = []
    for _, g in df.groupby("date"):
        if g[pred_col].nunique() < 2 or g[label_col].nunique() < 2:
            continue
        ic = g[pred_col].corr(g[label_col], method="spearman")
        if pd.notna(ic):
            ics.append(ic)
    return pd.Series(ics, dtype=float)


def split_train_val_by_time(df: pd.DataFrame):
    """按时间切分训练/验证集（80/20）"""
    dates = sorted(df["date"].unique())
    if len(dates) < 10:
        raise ValueError("可用交易日过少，无法切分训练/验证集")
    split_idx = max(1, int(len(dates) * 0.8))
    split_date = dates[split_idx - 1]
    train_df = df[df["date"] <= split_date].copy()
    val_df = df[df["date"] > split_date].copy()
    if val_df.empty:
        val_df = train_df.tail(min(len(train_df), 5000)).copy()
    return train_df, val_df


def train_models(train_df: pd.DataFrame, feature_cols):
    """训练三个子模型并根据验证 IC 计算权重"""
    train_part, val_part = split_train_val_by_time(train_df)
    x_train = train_part[feature_cols]
    y_train = train_part["label"]
    x_val = val_part[feature_cols]
    y_val = val_part["label"]

    models = {
        "lgbm_conservative": LGBMRegressor(
            n_estimators=500,
            learning_rate=0.03,
            num_leaves=31,
            max_depth=-1,
            subsample=0.9,
            colsample_bytree=0.9,
            reg_alpha=0.1,
            reg_lambda=1.0,
            min_child_samples=60,
            random_state=42,
            n_jobs=-1,
        ),
        "lgbm_bagging": LGBMRegressor(
            n_estimators=350,
            learning_rate=0.05,
            num_leaves=63,
            max_depth=-1,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.0,
            reg_lambda=0.3,
            min_child_samples=40,
            random_state=43,
            n_jobs=-1,
        ),
        "xgb": XGBRegressor(
            n_estimators=400,
            learning_rate=0.05,
            max_depth=6,
            subsample=0.85,
            colsample_bytree=0.85,
            objective="reg:squarederror",
            random_state=44,
            n_jobs=-1,
            tree_method="hist",
        ),
    }

    model_ic = {}
    for name, model in models.items():
        logger.info(f"训练子模型: {name}")
        model.fit(x_train, y_train)
        val_pred = model.predict(x_val)
        val_eval = val_part[["date", "label"]].copy()
        val_eval["pred"] = val_pred
        ic_series = calculate_daily_ic(val_eval, pred_col="pred", label_col="label")
        model_ic[name] = float(ic_series.mean()) if len(ic_series) > 0 else 0.0

    raw_weights = np.array([max(model_ic[k], 0.0) for k in models.keys()], dtype=float)
    if raw_weights.sum() <= 1e-12:
        raw_weights = np.ones(len(models), dtype=float)
    raw_weights = raw_weights / raw_weights.sum()
    weights = {k: float(w) for k, w in zip(models.keys(), raw_weights)}

    ensemble_pred = np.zeros(len(x_val))
    for name, model in models.items():
        ensemble_pred += weights[name] * model.predict(x_val)
    ensemble_eval = val_part[["date", "label"]].copy()
    ensemble_eval["pred"] = ensemble_pred
    ensemble_ic_series = calculate_daily_ic(ensemble_eval, pred_col="pred", label_col="label")
    ensemble_ic = float(ensemble_ic_series.mean()) if len(ensemble_ic_series) > 0 else 0.0

    return models, weights, model_ic, ensemble_ic


def predict_ensemble(models, weights, df: pd.DataFrame, feature_cols):
    """集成预测"""
    pred = np.zeros(len(df), dtype=float)
    for name, model in models.items():
        pred += weights[name] * model.predict(df[feature_cols])
    return pred


def calc_turnover(trades_df: pd.DataFrame, pf_df: pd.DataFrame):
    """估算换手率: 总成交额 / (2 * 平均资产)"""
    if trades_df.empty or pf_df.empty:
        return 0.0
    buy_amount = trades_df["买入价"].astype(float) * trades_df["股数"].astype(float)
    sell_amount = trades_df["卖出价"].astype(float) * trades_df["股数"].astype(float)
    avg_asset = float(pf_df["portfolio_value"].mean())
    if avg_asset <= 0:
        return 0.0
    return float((buy_amount.sum() + sell_amount.sum()) / (2.0 * avg_asset))


def calc_annualized_return(total_return: float, n_days: int):
    """按交易日数折算年化收益"""
    if n_days <= 0:
        return 0.0
    return float((1.0 + total_return) ** (252.0 / n_days) - 1.0)


def main():
    """主函数"""
    args = parse_args()
    windows = build_windows(args.test_start_year, args.test_end_year, args.train_years)
    if not windows:
        raise ValueError("窗口为空，请检查年份参数")

    earliest_start = windows[0]["train_start"]
    latest_end = windows[-1]["test_end"]

    logger.info("=" * 70)
    logger.info("Walk-Forward 训练评估开始")
    logger.info(f"股票池: {args.pool}")
    logger.info(f"窗口: {args.train_years}年训练 + 1年测试")
    logger.info(f"测试年份: {args.test_start_year}-{args.test_end_year}")
    logger.info("=" * 70)

    fetcher = DataFetcher(TUSHARE_TOKEN, str(CACHE_PATH))
    feature_engineer = FeatureEngineer()

    logger.info(f"加载全量数据: {earliest_start} 到 {latest_end}")
    price_df, stock_names, stock_industries, _ = fetcher.load_data_extended(
        earliest_start, latest_end, args.pool
    )
    price_df["date"] = pd.to_datetime(price_df["date"])

    logger.info("计算全量特征（仅一次）...")
    feature_df = feature_engineer.calculate_features(price_df)
    feature_cols = feature_engineer.get_feature_cols()
    feature_df = feature_df.dropna(subset=feature_cols + ["label"]).copy()
    feature_df["date"] = pd.to_datetime(feature_df["date"])

    models_dir = Path(args.models_dir) / args.pool
    results_dir = Path(args.results_dir) / args.pool
    models_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    all_rows = []
    for window in windows:
        test_year = window["test_year"]
        logger.info("-" * 70)
        logger.info(
            f"窗口 {test_year}: 训练 {window['train_start']}~{window['train_end']} | "
            f"测试 {window['test_start']}~{window['test_end']}"
        )

        train_mask = date_mask(feature_df, window["train_start"], window["train_end"])
        train_df = feature_df[train_mask].copy()
        if train_df.empty:
            logger.warning(f"窗口 {test_year} 训练数据为空，跳过")
            continue

        models, weights, model_ic, ensemble_ic_val = train_models(train_df, feature_cols)
        model_data = {
            "models": models,
            "weights": weights,
            "features": feature_cols,
            "ensemble_ic": ensemble_ic_val,
            "train_date": pd.Timestamp.now().strftime("%Y-%m-%d"),
            "train_start": window["train_start"],
            "train_end": window["train_end"],
            "test_start": window["test_start"],
            "test_end": window["test_end"],
            "model_ic": model_ic,
        }

        model_path = models_dir / f"model_{args.pool}_{test_year}.pkl"
        with open(model_path, "wb") as f:
            pickle.dump(model_data, f)

        test_mask = date_mask(feature_df, window["test_start"], window["test_end"])
        test_df = feature_df[test_mask].copy()
        if test_df.empty:
            logger.warning(f"窗口 {test_year} 测试数据为空，跳过")
            continue

        test_df["pred"] = predict_ensemble(models, weights, test_df, feature_cols)
        ic_series = calculate_daily_ic(test_df[["date", "pred", "label"]], pred_col="pred", label_col="label")
        test_ic = float(ic_series.mean()) if len(ic_series) > 0 else 0.0

        strategy = V7Strategy()
        strategy.models = models
        strategy.weights = weights
        strategy.feature_cols = feature_cols
        strategy._models_loaded = True

        test_start_dt = pd.to_datetime(window["test_start"])
        test_end_dt = pd.to_datetime(window["test_end"])
        slice_start = (test_start_dt - pd.Timedelta(days=200)).strftime("%Y-%m-%d")
        slice_end = (test_end_dt + pd.Timedelta(days=10)).strftime("%Y-%m-%d")
        price_slice = price_df[(price_df["date"] >= pd.to_datetime(slice_start)) &
                               (price_df["date"] <= pd.to_datetime(slice_end))].copy()

        result, trades_df, pf_df = run_backtest_strategy(
            strategy=strategy,
            price_df=price_slice,
            stock_names=stock_names,
            stock_industries=stock_industries,
            pool_type=args.pool,
            start_date=window["test_start"],
            end_date=window["test_end"],
            sell_price_type=args.sell_price,
            skip_model_load=True,  # walk-forward 模式，跳过模型加载
        )

        turnover = calc_turnover(trades_df, pf_df)
        ann_return = calc_annualized_return(result["total_return"], len(pf_df))

        year_dir = results_dir / str(test_year)
        year_dir.mkdir(parents=True, exist_ok=True)
        if not trades_df.empty:
            trades_df.to_csv(year_dir / "trades.csv", index=False, encoding="utf-8-sig")
        if not pf_df.empty:
            pf_df.to_csv(year_dir / "portfolio.csv", index=False)

        row = {
            "test_year": test_year,
            "train_start": window["train_start"],
            "train_end": window["train_end"],
            "annual_return": ann_return,
            "total_return": result["total_return"],
            "max_drawdown": result["max_drawdown"],
            "win_rate": result["win_rate"],
            "turnover": turnover,
            "test_ic": test_ic,
            "val_ic": ensemble_ic_val,
            "total_trades": result["total_trades"],
            "avg_holding_days": result["avg_holding_days"],
            "model_file": str(model_path),
        }
        all_rows.append(row)

        logger.info(
            f"窗口 {test_year} 完成 | 年化 {ann_return:.2%} | 回撤 {result['max_drawdown']:.2%} | "
            f"胜率 {result['win_rate']:.2%} | 换手 {turnover:.2f} | IC {test_ic:.4f}"
        )

    summary_df = pd.DataFrame(all_rows).sort_values("test_year")
    summary_path = results_dir / f"walk_forward_summary_{args.test_start_year}_{args.test_end_year}.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")

    if not summary_df.empty:
        logger.info("=" * 70)
        logger.info("Walk-Forward 汇总结果")
        logger.info("=" * 70)
        logger.info(
            summary_df[
                ["test_year", "annual_return", "max_drawdown", "win_rate", "turnover", "test_ic", "total_trades"]
            ].to_string(index=False)
        )
    logger.info(f"汇总文件已保存: {summary_path}")


if __name__ == "__main__":
    main()
