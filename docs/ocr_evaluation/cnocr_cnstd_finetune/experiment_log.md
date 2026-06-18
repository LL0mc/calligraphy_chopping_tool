# CNSTD/CNOCR 微调实验日志

> ⚠️ 已归档。训练产物（checkpoints、logs）见 `docs/archive/cnocr_cnstd_finetune/training_artifacts/`
> 配置文件见 `docs/archive/cnocr_cnstd_finetune/configs/`
> 完整评估汇总见 `docs/archive/cnocr_cnstd_finetune/results/evaluation_summary.md`
> 最终结论：数据量太小，RapidOCR 保持最优。

> Branch: `feat/cnocr-finetune`
> 时间: 2026-06-18
> 目标: 用已标注的 22 页数据微调 CNSTD（检测）+ CNOCR（识别）模型，替代 RapidOCR，提升书法字帖 OCR 精度。

---

## 术语

| 缩写 | 全称 | 功能 | 类比 RapidOCR 阶段 | 模型架构 |
|------|------|------|---------------------|----------|
| CNSTD | Chinese Text Detection | 文字检测（定位 bbox） | 检测阶段 | `db_shufflenet_v2_small` |
| CNOCR | Chinese OCR | 字符识别（识别具体字） | 识别阶段 | `densenet_lite_136-gru` |

两者均来自 [breezedeus/CnOCR](https://github.com/breezedeus/CnOCR) 开源工具包。

---

## 一、准备工作

### 1.1 导出训练数据

**脚本**: `export_training_data.py`

从已审核的 OCR 结果 + 渲染图导出 CNSTD 和 CNOCR 需要的训练格式。

**发现的 bug 及修复**:

1. **TSV 行首多余空格** — `writer.writerow([''] + row)` 导致 TSV 每行以 tab 开头
   - Fix: 改为 `writer.writerow(row)`
2. **CNOCR 图像路径错误** — 拼接路径时 `os.path.join(rec_img_dir, ...)` 未结合 `img_folder` 配置
   - Fix: 改为相对 `img_folder` 路径

### 1.2 CNSTD 训练数据格式

```
output/training_data/detection/
├── train/
│   ├── gt.txt           # 每行: img_path\tx1,y1,x2,y2,...,text
│   └── imgs/
├── val/
│   ├── gt.txt
│   └── imgs/
└── config_detection.json
```

- 22 页渲染图（2496×3720），按 80/20 分训练/验证
- 每张图 ~40 个字符级多边形框（ICDAR 格式）
- 总计: ~800 框

### 1.3 CNOCR 训练数据格式

```
output/training_data/recognition/
├── train.tsv        # 每行: img_path\tlabel
├── val.tsv
├── imgs/            # 裁剪的单字图
│   ├── page_024_000_一.png
│   ├── page_024_001_上.png
│   └── ...
├── train_config.json
└── label_cn_custom.txt   # 自定义字表（去重后所有出现汉字）
```

- 裁剪图: 1035 训练 + 279 验证
- 统一添加 4px padding
- 字表从训练数据自动提取

---

## 二、CNSTD 检测微调

### 2.1 PL 2.6.1 兼容性问题

当前环境 PL 2.6.1，而 cnstd（v1.2）写于 PL 1.x/2.0 时代。**共发现并修复 10 个 bug**：

| # | 文件 | 行号 | 问题 | 修复 |
|---|------|------|------|------|
| 1 | `cnstd/dataset.py` | - | `train_transforms`/`val_transforms` 未保存到 `self` | 加 `self.train_transforms = train_transforms` |
| 2 | `cnstd/dataset.py` | - | `open(gt, 'r')` 缺 encoding，Windows 默认 GBK 崩溃 | 加 `encoding='utf-8'` |
| 3 | `cnstd/util.py` | - | 同上 | 加 `encoding='utf-8'` |
| 4 | `cnstd/trainer.py` | - | `gpus=0` → PL 2.x 已废弃 | `accelerator='cpu'` |
| 5 | `cnstd/trainer.py` | - | `stochastic_weight_avg=True` → PL 2.x 已移除 | 删除 |
| 6 | `cnstd/trainer.py` | - | `validation_epoch_end` 接收 `losses_list` 参数但父类签名不匹配 | 改为 `on_validation_epoch_end` + 移除 `losses_list` |
| 7 | `cnstd/cli.py` | 121 | `resized_shape=expected_img_shape[1:]` → 单元素列表 | 改为完整 `expected_img_shape` |
| 8 | `cnstd/trainer.py` | 79 | 同款 bug（mask_shape） | 同修 |
| 9 | `cnstd/metrics.py` | 167-168 | `np.zeros(num_gts)` → 广播错误 | `np.zeros((num_gts, 1))` |
| 10 | `cnstd/metrics.py` | 384 | 空 `sorted_idxs` 导致 index error | 跳过 + 初始化 `cur_prec=0.0` |
| 11 | `cnstd/cli.py` | 98-99 | shufflenet 显式禁用 `pretrained_backbone`（遗留代码，旧 torchvision 无 x1_5 权重） | 注释掉两行；torchvision 0.26 已有 x1_5 预训练权重 |

**补丁脚本**: `C:\Users\LMC\AppConfig\Local\Temp\opencode\patch_cnstd.py`

### 2.2 训练命令

```powershell
$env:WANDB_MODE='disabled'; $env:PYTHONIOENCODING='utf-8'
cd D:\notebooks\handwriting\output\training_data\detection
python -m cnstd.cli train -c config_detection.json --epochs 50
```

### 2.3 训练过程

| Epoch | train_loss | val_loss |
|-------|-----------|----------|
| 0     | 8.800     | 6.944    |
| 10    | 5.288     | 5.534    |
| 20    | 3.619     | 3.613    |
| 30    | 2.857     | 2.654    |
| 40    | 2.200     | 2.058    |
| 49    | 1.918     | 1.909    |

Loss 持续下降，未过拟合。

### 2.4 模型文件

- 原始 PL 模型: `lightning_logs/version_7/checkpoints/cnstd-v1.2-db_shufflenet_v2_small-fpn-epoch=049-val_loss_epoch=1.9091.ckpt`
- 重导出（去除 PL wrapper）: `lightning_logs/version_7/checkpoints/cnstd-v1.2-db_shufflenet_v2_small-fpn-epoch=049-val_loss_epoch=1.9091-model.ckpt`
- 最终复制: `output/training_data/detection/cnstd_finetuned.pt`

### 2.5 模型加载验证

```python
from cnstd import CnStd
std = CnStd(model_name='db_shufflenet_v2_small', model_fp=r'output/training_data/detection/cnstd_finetuned.pt')
```

验证结果: 成功加载，page 24 检测到 59 个框（基线 RapidOCR ~140 个）。

### 2.6 Pipeline 集成

**修改文件**:

| 文件 | 修改内容 |
|------|----------|
| `src/ocr_recognizer.py:get_ocr_char_boxes()` | 新增 `cnstd_model` 参数；`cnstd_backend` 分支调用 cnstd 推理 |
| `src/char_segmenter.py:segment_characters()` | 透传 `cnstd_model` |
| `src/pipeline.py:process_page()` | 新增 `--detection {rapidocr,cnstd}`；加载 cnstd 模型并传入下游 |

### 2.7 评估结果

**工具**: `eval_ocr.py`
**页面**: Page 24（799 字）
**指标**: 所有字符读作空格计分

| 检测后端 | 得分 | 漏检 | 多余框 |
|----------|------|------|--------|
| RapidOCR（基线） | **91.1** | 低 | 低 |
| CNSTD 微调 | **27.9** | 大量 | 大量 |

**退化原因分析**:
1. **⚡ 核心原因: `pretrained_backbone` 被显式禁用** — `cli.py:98-99` 中 cnstd 作者对所有 shufflenet 变体设置了 `pretrained_backbone = False`。写代码时旧版 torchvision 还没有 shufflenet_v2_x1_5 的预训练权重，但现在 torchvision 0.26 已经有了（13.6MB ImageNet 权重）。**导致微调实际从随机初始化开始。**
2. 训练数据仅 22 页 ~800 个标注框 — 检测模型需要 1000+ 样本
3. 59 个检测框中包含大量冗余/不完整框，与标注格式差异大

### 2.8 2026-06-18 修复

#### 2.8.1 预训练骨干修复

**发现**: `cli.py:98-99` 对 shufflenet 禁用 `pretrained_backbone`。
**验证**: `shufflenet_v2_x1_5(pretrained=True)` 在 torchvision 0.26 可成功下载 ImageNet 权重（13.6MB）。
**修复**: 注释掉 `pretrained_backbone = False` 两行。

#### 2.8.2 PL 2.x `resume_from_checkpoint` 修复

**发现**: `trainer.py:217` 在 PL 2.x 中 `Trainer.__init__()` 不再接受 `resume_from_checkpoint` 参数。
**修复**: 移除 `self.pl_trainer = pl.Trainer(resume_from_checkpoint=...)`，改为将 `ckpt_path` 传给 `self.pl_trainer.fit()`。

在 PL 兼容性表中新增第 11、12 项：

| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 11 | `cnstd/cli.py` | 98-99 | shufflenet 显式禁用 `pretrained_backbone` | 注释掉两行 |
| 12 | `cnstd/trainer.py` | 217 | `Trainer(resume_from_checkpoint=...)` → PL 2.x 废弃 | 移到 `fit(ckpt_path=...)` |

### 2.9 重新训练结果（带 pretrained_backbone）

| 指标 | 无预训练（之前） | 有预训练（现在） | RapidOCR（基线） |
|------|-----------------|-----------------|-----------------|
| **Page 24 得分** | **27.9** | **68.3** | **91.1** |
| 原始检测框数 | 59 | 36 | ~140 |
| 最终字符数 | 35 | 35 | ~35 |
| val_loss (best) | 1.909 | 1.912 | - |

**改进幅度**: +40.4 分（145% 提升）。
**与基线差距**: 22.8 分，主要瓶颈仍是训练数据量（仅 22 页）。

---

## 三、CNOCR 识别微调

### 3.1 PL 2.6.1 兼容性问题

| # | 文件 | 问题 | 修复 |
|---|------|------|------|
| 1 | `cnocr/utils.py:250` | `open(fp)` 缺 `encoding='utf-8'` → GBK 崩溃 | `open(fp, encoding='utf-8')` |
| 2 | `cnocr/dataset.py:74` | `super().__init__(data_source)` → PL 2.x BucketSampler API 变化 | `super().__init__()` |
| 3 | `cnocr/trainer.py` | 配置缺 `lr_scheduler` 字段 | `train_config.json` 中添加 |

### 3.2 训练配置

`output/training_data/recognition/train_config.json`:
```json
{
  "train_data_fp": "train.tsv",
  "val_data_fp": "val.tsv",
  "img_folder": "imgs",
  "label_custom_fp": "label_cn_custom.txt",
  "epochs": 50,
  "batch_size": 16,
  "num_workers": 0,
  "log_every_n_steps": 10,
  "lr_scheduler": {"name": "cosine", "warmup_epochs": 3},
  "pl_checkpoint_monitor": "complete_match",
  "pl_checkpoint_mode": "max",
  "accelerator": "cpu",
  "devices": 1,
  "pretrained_model_fp": null
}
```

### 3.3 训练命令

```powershell
$env:WANDB_MODE='disabled'; $env:NO_ALBUMENTATIONS_UPDATE=1; $env:PYTHONIOENCODING='utf-8'
cd D:\notebooks\handwriting\output\training_data\recognition
python -m cnocr.train -c train_config.json
```

### 3.4 附加依赖安装

cnocr 训练需要额外包:
```powershell
pip install datasets
pip install "albumentations<2"    # cnocr pin 在 v1.x
pip install multiprocess
```

### 3.5 训练过程

| Epoch | train_loss | val_loss | train_acc | val_acc |
|-------|-----------|----------|-----------|---------|
| 0     | 9.368     | 9.527    | 0.039     | 0.058   |
| 5     | 6.343     | 9.195    | 0.260     | 0.162   |
| 10    | 4.863     | 8.610    | 0.442     | 0.193   |
| 20    | 3.151     | 7.244    | 0.621     | 0.267   |
| 30    | 2.496     | 6.415    | 0.699     | 0.313   |
| 40    | 1.926     | 6.156    | 0.748     | 0.374   |
| 48    | **1.725** | **6.087**| **0.752** | **0.427** |
| 49    | 1.716     | 6.103    | 0.754     | 0.401   |

最佳 epoch 48: val_acc = 42.65%

### 3.6 模型文件

- 最佳 PL 模型: `runs/CnOCR-Rec/1r2ycf67/checkpoints/cnocr-v2.3-densenet_lite_136-gru-epoch=048-val-complete_match-epoch=0.4265.ckpt`
- 重导出: `.../-model.ckpt`
- 最终复制: `output/training_data/recognition/cnocr_finetuned.pt`

### 3.7 官方 cnocr 模型基准测试（2026-06-18）

用官方预训练 cnocr（`densenet_lite_136-gru`，印刷体数据训练）直接在 page 24 的 37 个裁剪单字上做识别，**不做任何微调**。

```python
from cnocr import CnOcr
ocr = CnOcr(name='densenet_lite_136-gru')
result = ocr.ocr_for_single_line('001_第.png')
# 返回 {'text': '第', 'score': 0.753}
```

**结果**: 22/37 = **59.5%** 准确率

**典型错误**:
- 形近字：峰→蜂、无→元、枉→神、谁→淮
- 非中文乱码：一→T、石→a、可→m、红→2
- 得分不一定可信：无→元 score=0.830 但错了

**结论**: 官方印刷体模型对书法字帖泛化能力有限。

### 3.8 微调 vs 官方模型对比

| 指标 | 官方 cnocr | 微调 cnocr（22页） |
|------|-----------|-------------------|
| 准确率 | **59.5%** | 42.7% |
| 对印刷体记忆 | ✅ 完整保留 | ❌ 灾难性遗忘 |
| 对书法适应性 | ❌ 差 | ⚠️ 略有提升但不足 |

22 页数据不足以让模型忘记印刷体先验并学到书法特征，微调反而退步。

### 3.9 当前状态

✅ 训练完成，模型已保存
❌ 官方和微调模型均远低于 RapidOCR 基线 ~93.8%

---

## 四、关键教训

1. **数据量是第一瓶颈**。22 页对检测模型远远不够（~800 框 vs 所需数千），对识别模型也不够（42.7% vs 基线 93.8%）。
2. **预训练骨干至关重要**（+40.4 分）。`cli.py:98-99` 禁用 shufflenet 预训练是个坑。
3. **微调识别存在灾难性遗忘**。22 页数据让 cnocr 忘记印刷体知识（59.5% → 42.7%）。
4. **PL 版本兼容性是最大时间消耗**。CNSTD 12 个 bug + CNOCR 3 个，全部是 PL 2.x API 变化导致。

### 最终结论（2026-06-18）

| 方案 | 检测得分 | 识别准确率 | 结论 |
|------|---------|-----------|------|
| RapidOCR（基线） | **91.1** | **93.7%** | ✅ 保持最优 |
| CNSTD + pretrained | 68.3 | - | ❌ 数据不足 |
| CNOCR 官方模型 | - | 59.5% | ❌ 书法字帖不兼容 |
| CNOCR 微调 | - | 42.7% | ❌ 灾难性遗忘 |

**所有替代方案均无法超越 RapidOCR**。已归档。

## 五、关于 RapidOCR 微调

RapidOCR 底层是 PaddleOCR（PP-OCRv5）的 ONNX 模型。微调是可行的：

1. **获取 PaddleOCR 训练代码和权重**（非 ONNX 格式）
2. **转换训练数据**到 PaddleOCR 标注格式（PPOCR 格式与当前格式不同）
3. **用 PaddlePaddle 框架训练**（需安装 PaddlePaddle GPU 版，~2GB）
4. **导出回 ONNX** 供推理使用

**当前不推荐**，原因：
- 需要引入 PaddlePaddle 全套生态，与项目已有 PyTorch 栈不兼容
- 数据量问题同样存在——22 页对任何检测/识别模型都不够
- 优先策略：Review GUI 标注更多页面 → 数据量上来后再考虑训练方案

## 六、附录：命令速查

### 恢复基线
```powershell
# config.py 中检查 RAPID_OCR_BACKEND = "rapidocr"
Copy-Item output/cropped/文征明/千字文/page_024/ocr_results_baseline.json output/cropped/文征明/千字文/page_024/ocr_results.json
python pipeline.py 24 --no-correct
python eval_ocr.py 24
```

### CNSTD 微调
```powershell
python export_training_data.py
# patch cnstd (apply_patches.bat)
$env:WANDB_MODE='disabled'; $env:PYTHONIOENCODING='utf-8'
python -m cnstd.cli train -c output/training_data/detection/config_detection.json --epochs 50
```

### CNOCR 微调
```powershell
# 确保依赖已安装: pip install datasets "albumentations<2" multiprocess
$env:WANDB_MODE='disabled'; $env:NO_ALBUMENTATIONS_UPDATE=1; $env:PYTHONIOENCODING='utf-8'
python -m cnocr.train -c output/training_data/recognition/train_config.json
```

### Pipeline 使用 CNSTD 检测
```powershell
python pipeline.py 24 --detection cnstd --no-correct
```

### 模型推理验证
```python
from cnstd import CnStd
std = CnStd(model_name='db_shufflenet_v2_small', model_fp=r'output/training_data/detection/cnstd_finetuned.pt')
```
