# CNSTD/CNOCR 替代 RapidOCR 实验日志

> 日期: 2026-06-18
> 分支: `feat/cnocr-finetune`
> 目标: 用 CNSTD（检测）+ CNOCR（识别）替代 RapidOCR，提升书法字帖精度。
> **最终结论：22 页不够，RapidOCR 保持最优。**

---

## 一、换用不同模型（不做微调）

### 1.1 CNSTD 检测 + RapidOCR 识别

用 CNSTD 做检测定位，识别仍用 RapidOCR。

**CNSTD 官方模型**：直接用 breezedeus 发布的预训练检测模型。

**结果（page 24）：**

| 检测模型 | 检测框数 | 最终字符 | 得分 |
|---------|---------|---------|------|
| RapidOCR（基线） | ~140 | ~35 | **91.1** |
| CNSTD 官方模型 | 59→35 | 35 | **27.9** |

> 原因：官方 CNSTD 在印刷体上训练，书法字帖检测效果差；且 `pretrained_backbone` 被作者显式禁用（旧 torchvision 无 shufflenet_v2_x1_5 权重），骨干从随机初始化。

**修复**：注释掉 `cnstd/cli.py:98-99` 的禁用代码，重新训练（见第二章）。

### 1.2 RapidOCR 检测 + CNOCR 识别

用 RapidOCR 做检测，CNOCR 官方模型（印刷体预训练）做识别。

对 page 24 的 37 个裁剪单字测试：

```
准确率: 22/37 = 59.5%
```

典型错误：
- 形近字：峰→蜂、无→元、枉→神、谁→淮
- 非中文：一→T、石→a、可→m、红→2

**结论**：官方 CNOCR 对书法字帖泛化能力有限，远不如 RapidOCR 识别（93.7%）。

---

## 二、参数实验（以 RapidOCR 基线为基准）

此部分在 `docs/ocr_evaluation_log.md` 中有完整记录，这里是摘要。

### 2.1 CC refine 参数调优（5 轮实验）

| 实验 | search_margin_x | merge_radius | 得分 |
|------|----------------|-------------|------|
| Baseline | 40 | 100 | **91.57** |
| 跳过 CC refine | - | - | 61 |
| 行级等分外扩 | - | - | 73 |
| 等比外扩+抑制 | - | - | 72 |

**结论**：CC refine 是必需步骤，漏检从 39→1，边缘误差从 25px→2.1px。

### 2.2 文字纠错

`_is_valid_chinese` 过滤非中文字符，准确率 94.0%→94.1%（79→77 错误）。

---

## 三、微调模型

### 3.1 CNSTD 检测微调

**数据**：22 页 ~800 个字符框（ICDAR 多边形格式），80/20 分训练/验证。

**PL 2.6.1 兼容性修复（12 处）：**

| # | 文件 | 问题 |
|---|------|------|
| 1 | `dataset.py` | `train_transforms` 未保存到 self |
| 2 | `dataset.py` | `open()` 缺 `encoding='utf-8'` → GBK 崩溃 |
| 3 | `util.py` | 同上 |
| 4-6 | `trainer.py` | `gpus=` → `accelerator='cpu'`；`stochastic_weight_avg` 移除；`validation_epoch_end` 签名变更 |
| 7-8 | `cli.py:121`、`trainer.py:79` | `shape[1:]` 返回单元素列表 |
| 9-10 | `metrics.py:167,384` | 广播错误、空数组崩溃 |
| 11 | `cli.py:98-99` | shufflenet 预训练被显式禁用 |
| 12 | `trainer.py:217` | `resume_from_checkpoint` 移到 PL 2.x `fit()` |

**训练结果（50 epoch, CPU）：**

| 方案 | train_loss | val_loss | Page 24 得分 |
|------|-----------|---------|-------------|
| 无预训练骨干 | 8.8→1.92 | 6.9→1.91 | **27.9** |
| 有预训练骨干 | 9.6→1.68 | 7.4→1.91 | **68.3** |
| RapidOCR 基线 | - | - | **91.1** |

预训练骨干带来 +40.4 分提升，但 22 页数据仍不够。

### 3.2 CNOCR 识别微调

**数据**：1035 训练 + 279 验证（单字裁剪图），字表从训练数据提取。

**训练结果（50 epoch, CPU, ~3min）：**

| 模型 | 验证准确率 |
|------|-----------|
| 官方 CNOCR（印刷体，不微调） | **59.5%** |
| 微调 CNOCR（22页） | **42.7%** |
| RapidOCR 识别（基线） | **93.7%** |

**灾难性遗忘**：22 页书法数据让模型忘记印刷体知识，微调后反而更差。

### 3.3 Pipeline 集成

`--detection cnstd` 参数已加入 pipeline，可端到端跑通：

```bash
python pipeline.py 24 --detection cnstd --no-correct
```

识别仍用 RapidOCR。不推荐使用（得分 68.3 < 基线 91.1）。

---

## 四、关于 RapidOCR 微调

RapidOCR 底层是 PaddleOCR（PP-OCRv5）ONNX 模型。理论上可走 PaddlePaddle 训练流程再导出 ONNX。

**当前不推荐**：
- 需安装 PaddlePaddle GPU（~2GB），与项目 PyTorch 栈不兼容
- 数据量问题是根本——22 页不够任何检测/识别模型
- 优先：Review GUI 标注更多页面 → 数据量上来后再考虑训练

---

## 五、最终结论

| 方案 | 检测得分 | 识别准确率 |
|------|---------|-----------|
| **RapidOCR（基线）** | **91.1** | **93.7%** |
| CNSTD 官方（未经微调） | 27.9 | - |
| CNSTD 微调（有预训练） | **68.3** | - |
| CNSTD 微调（无预训练） | 27.9 | - |
| CNOCR 官方（不微调） | - | 59.5% |
| CNOCR 微调（22页） | - | 42.7% |

所有替代方案均无法超越 RapidOCR。关键瓶颈：**数据量**。

---

## 六、后续验证：27.9 分的真正原因（2026-06-19）

### 6.1 问题

CNSTD 官方模型得分 27.9 分异常偏低。作为成熟的中文文本检测模型，即使 backbone 随机初始化，也不应该如此之差。

### 6.2 排查过程

1. **`detector.py:156` 硬编码 `pretrained_backbone=False`** — CNSTD 的 Detector 类在初始化时禁用了预训练 backbone，导致即使网络下载成功，backbone 也是随机权重。`cli.py` 中虽已取消禁用（注释说明 torchvision 0.26+ 支持），但 `detector.py` 未同步修改。

2. **模型 checkpoint 可用** — `C:\Users\LMC\AppData\Roaming\cnstd\1.2\db_shufflenet_v2_small\` 下有 12MB 的 checkpoint 文件，检测模型权重本身已下载。

3. **实测 CNSTD 检测输出** — 在 page 24 上运行 CNSTD，输出 18 个区域框。可视化后发现：

   | 框类型 | 示例 | 说明 |
   |--------|------|------|
   | 整列框 | #2 (237×2698px), #3 (204×2664px) | 整列文字作为一个区域 |
   | 区域框 | #0 标题, #8 "青埂峰顽石偈" | 段落/标题级 |
   | 碎片框 | #4, #5, #9 等 | 注释文字片段 |

   **CNSTD 输出的是文本区域级框（列/段落），不是字符级框。**

### 6.3 根因

**粒度不匹配**：
- **CNSTD/CnOCR**：文本区域检测器 → 输出列级/行级框
- **RapidOCR（PP-OCRv5）**：字符级检测+识别 → 输出单字级框
- **Pipeline 需求**：字符级定位 → 与 RapidOCR 天然兼容

评估器用 Hungarian 匹配（中心距离 ≤ 60px），区域框的中心 ≠ 单字框的中心，导致大量匹配失败，分数崩塌。

### 6.4 CnOCR 调研

CnOCR V2.2+ 内部调用 CnSTD 做检测，同样输出区域级框。虽然 V2.3.1+ 集成了 PP-OCRv4/v5 识别模型，但检测端仍是区域级。**CnOCR 不支持字符级检测。**

### 6.5 结论

| 包 | 检测粒度 | 字符级框 | 与 Pipeline 兼容 |
|---|---------|---------|-----------------|
| **RapidOCR** | 字符级 | ✅ `return_word_box=True` | ✅ |
| **PaddleOCR** (原版) | 字符级 | ✅ PP-OCRv4/v5 | ⚠️ 需 PaddlePaddle 框架 |
| **CnOCR** | 区域级 | ❌ 依赖 CnSTD | ❌ |
| **CNSTD** | 区域级 | ❌ | ❌ |

**整个换检测器的实验方向有误** — 不该替换检测器，应在 RapidOCR 的字符级结果上做后处理优化。27.9 分不是模型差，是架构不兼容。

---

## 附录：文件归档

| 内容 | 路径 |
|------|------|
| 实验日志（本文） | `docs/experiment_log.md` |
| 评估汇总 | `docs/archive/cnocr_cnstd_finetune/results/evaluation_summary.md` |
| 训练配置 | `docs/archive/cnocr_cnstd_finetune/configs/` |
| 补丁脚本 | `docs/archive/cnocr_cnstd_finetune/scripts/patch_cnstd.py` |
| 训练产物（~1GB） | `docs/archive/cnocr_cnstd_finetune/training_artifacts/` |
