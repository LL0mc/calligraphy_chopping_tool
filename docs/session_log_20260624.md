# 2026-06-24 工作记录

## 重构评估系统

### 问题
- 旧评估器从 `baseline.json + corrected.json` 拼接 GT，`orig_idx` 引用的是旧版 ocr_results 的索引
- pipeline 重跑后 ocr_results 变化，`orig_idx` 错位，GT 构建出错
- AGENTS.md 中的基线数据（94.27）基于旧页面集（29 页），与当前（31 页）不一致

### 改动
1. **`src/evaluator.py`** — 直接加载 `page_N_gt.json` 快照，移除 `build_ground_truth()`；平均分改为按 GT 字数加权平均
2. **`review_server.py`** — submit 时自动生成 `gt.json`（从 corrected 数据构建）
3. **`src/migrate_gt.py`**（新建）— 从 baseline+corrected 一次性迁移生成 GT 快照
4. **`docs/experiment_workflow.md`**（新建）— 完整实验流程文档
5. **`AGENTS.md`** — 更新架构图、文件表、评估器说明
6. **清理** — 删除 `data/`（无引用）、`src/utils_deprecated.py`（无引用）、`output/pages/` 中的 baseline 和调试 PNG

### 新评估数据流
```
review_server submit → gt.json（不可变真值快照）
pipeline 输出 → ocr_results.json（可变）
evaluator → gt.json vs ocr_results.json → 评分
baseline → output/exp/{实验名}/ocr_results.json（旧方法检测结果）
```

## 评估对比

### 同页面集（29 页）对比
| | v4_baseline | 当前 pipeline |
|---|---|---|
| 加权平均分 | 89.48 | 89.35 |
| 误检 | 485 | 24 |
| 文字错误 | 74 | 92 |
| 文字准确率 | 94.5% | 93.2% |

**结论**：分数几乎一样（差 0.13），错误构成不同。v4 误检多但文字准，当前误检少但文字错更多。成本模型下两者打平。

### 当前 pipeline 基线（31 页，GT 快照）
- 加权平均分：**89.33**
- 文字准确率：**93.2%**（87 个文字错误 / 1418 匹配）
- 漏检：22，误检：25

## 文字错误分析（87 个错误）

| 类型 | 数量 | 示例 |
|------|------|------|
| 繁简差异 | 7 | 满→滿(x6), 内→內(x1) |
| 形近字 | ~25 | 日→月(x3), 相→桐(x2), 士→生 |
| 非中文误匹配 | ~15 | Z→如, 1→人, Y→尘 |
| 空识别 (conf=0) | 12 | 枉→"", 荒→"" |
| 其他 | ~28 | 爱→贾, 罢→黑 |

**最高频错误**：满→滿（繁体），出现 6 次。

## 模型组合测试

测试了 4 种 Det/Rec 模型组合（PP-OCRv4/v5 × PP-OCRv4/v5），通过完整 pipeline 后评估结果**完全一致**。

原因：`recognize_characters` 在 confidence ≥ 0.6 时跳过 re-OCR，直接用检测阶段的文字。rec 模型对大部分字符不生效。

### 原始 OCR 输出对比（未经 pipeline 过滤）
| 组合 | CharAcc | EdgeErr | 备注 |
|------|---------|---------|------|
| v4_v4 | 92.0% | 88.6px | |
| v4_v5 | 93.7% | 92.0px | |
| v5_v4 | 90.2% | 127.9px | |
| v5_v5 | 92.2% | 131.3px | |

PP-OCRv4 识别对 87 个错误中的 **29 个**能给出正确答案（33%），PP-OCRv5 能修 **20 个**（23%）。

### 检测模型对比（原始输出）
- PP-OCRv5 检测召回率更高（8 页有漏检 vs v4 的 15 页）
- PP-OCRv4 检测噪声框更少
- pipeline 后处理后差异被抹平

## 结论

1. **当前 pipeline 的瓶颈是文字识别准确率**（93.2%），而非检测
2. **模型微调不可行** — 数据量不足（31 页 / 1439 字），且 ONNX 模型无法直接微调
3. **繁简映射收益低** — 只能修 7 个错误（8%），ROI 不高
4. **最有效的改进方向**：扩大 GT 数据集（标注更多页面），为后续优化打基础
5. **评估体系已重建** — GT 快照 + 加权评分，pipeline 可随意重跑不影响评估

## 文件产出
- `output/exp/current_pipeline/` — 当前 pipeline 的 31 页检测结果
- `output/exp/text_errors.json` — 87 个文字错误详情
- `output/exp/error_analysis.json` — 错误分类统计
- `output/exp/model_test/` — 4 种模型组合的测试结果
- `test_model_combos.py` — 模型组合测试脚本
