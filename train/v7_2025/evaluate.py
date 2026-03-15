"""
v7_2025 模型评估脚本

评估已训练模型的性能
"""
import sys
import argparse
import pickle
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.utils.logger import logger
from config.settings import MODEL_DIR


def parse_args():
    """解析参数"""
    parser = argparse.ArgumentParser(description='v7_2025 模型评估')
    parser.add_argument('--pool', type=str, default='csi500',
                        choices=['csi300', 'csi500', 'csi1000'])
    parser.add_argument('--model', type=str, default=None,
                        help='模型文件路径')
    return parser.parse_args()


def load_model(model_path, pool_type):
    """加载模型"""
    if model_path is None:
        model_path = Path(MODEL_DIR) / f"model_enhanced_v7_{pool_type}.pkl"
    else:
        model_path = Path(model_path)

    if not model_path.exists():
        raise FileNotFoundError(f"模型文件不存在: {model_path}")

    with open(model_path, 'rb') as f:
        data = pickle.load(f)

    return data


def evaluate_model(model_data):
    """评估模型"""
    logger.info("="*60)
    logger.info("模型评估结果")
    logger.info("="*60)

    logger.info(f"特征数: {len(model_data['features'])}")
    logger.info(f"模型权重: {model_data['weights']}")
    logger.info(f"集成IC: {model_data.get('ensemble_ic', 0):.4f}")
    logger.info(f"训练日期: {model_data.get('train_date', 'N/A')}")

    # TODO: 添加更多评估指标
    # - IC均值
    # - ICIR
    # - 分组收益
    # - 回测表现


def main():
    """主函数"""
    args = parse_args()

    # 加载模型
    model_data = load_model(args.model, args.pool)

    # 评估模型
    evaluate_model(model_data)


if __name__ == "__main__":
    main()
