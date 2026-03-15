# v7_2025 模型训练说明

## 目录结构

```
train/v7_2025/
├── README.md       # 本文件
├── train.py        # 训练脚本
├── evaluate.py     # 评估脚本
└── notebooks/      # (可选) Jupyter notebooks
```

## 使用方法

### 1. 训练模型

```bash
# 训练 CSI500 模型
python train/v7_2025/train.py --pool csi500 --start 2020-01-01 --end 2024-12-31

# 训练 CSI300 模型
python train/v7_2025/train.py --pool csi300 --start 2020-01-01 --end 2024-12-31

# 训练 CSI1000 模型
python train/v7_2025/train.py --pool csi1000 --start 2020-01-01 --end 2024-12-31

# 指定输出路径
python train/v7_2025/train.py --pool csi500 --output models/my_model_v7.pkl
```

### 2. 评估模型

```bash
# 评估 CSI500 模型
python train/v7_2025/evaluate.py --pool csi500

# 评估指定模型
python train/v7_2025/evaluate.py --model models/model_enhanced_v7_csi500.pkl
```

## 模型输出

训练完成后，模型文件将保存在 `models/` 目录：
- `model_enhanced_v7_csi300.pkl`
- `model_enhanced_v7_csi500.pkl`
- `model_enhanced_v7_csi1000.pkl`

## 注意事项

1. **训练数据**：建议使用2020-2024年数据训练
2. **验证数据**：建议使用2025年数据进行参数调优
3. **测试数据**：建议使用2026年数据进行策略验证
4. **避免前瞻泄露**：训练时不要使用未来数据

## 自定义训练

编辑 `train.py` 中的 `train_model()` 函数，实现你的模型训练逻辑。
