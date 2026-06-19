# 2026-06-19 实验记录

## 评估方法

### 成本评估器（本次新设计）

基于人工审阅成本的评分模型，反映实际工作量：

| 操作 | 成本 | 说明 |
|------|------|------|
| 新增框（漏检） | 8 | 需要精确画新框 |
| 删除框（误检） | 1 | 一次点击 |
| 调整框（边缘误差） | 0.1 × edge_sum | 按像素累加 |
| 修改文字 | 2 | 只需打字 |

```
edge_sum = |dl| + |dt| + |dr| + |db|   （四边绝对误差之和）
total_cost = Σ(match_costs) + 8 × n_missed + 1 × n_extra
score = max(0, 100 × (1 - total_cost / max_cost))
max_cost = n_gt × 10
```

### 旧评估器（问题）

旧评估器使用乘法公式：`score = 100 × 文字准确率 × 边缘因子 × 检测F1`

问题：
- 三项相乘导致分数过度偏低（每项 0.95 → 总分 85.7）
- 漏检和误检等价对待（实际漏检成本远高于误检）
- 无法反映真实的审阅工作量

## 实验过程

### 实验 1：过滤噪声框

**方法**：移除 ocr_text 为空且 ocr_score < 0.3 的框。

| 指标 | 基线 | 实验 1 | 变化 |
|------|------|--------|------|
| 得分 | 90.43 | 90.15 | -0.28 |
| 漏检 | 1 | **10** | +9 ❌ |
| 误检 | 10 | 5 | -5 ✓ |

**结论**：过滤器太激进，把 9 个有效低置信度字符也删了。漏检成本（8/个）远大于误检节省（1/个）。失败。

### 实验 2：右侧边框加宽

**方法**：每个框的 w 增加 15px，补偿右侧系统性偏窄（平均 22.7px）。

| 指标 | 基线 | 实验 2 | 变化 |
|------|------|--------|------|
| 得分 | 90.43 | **75.47** | -14.96 ❌ |
| 边缘误差 | 8.8px | **23.4px** | +14.6 ❌ |

**结论**：固定加宽太粗暴，对右侧已经正确的框引入新误差。失败。

### 实验 3：增大 expand_padding

**方法**：expand_padding 从 15 增加到 25，让 OCR 看到更多上下文。

| 指标 | 基线 (p=15) | 实验 3 (p=25) | 变化 |
|------|------------|--------------|------|
| 得分 | 90.43 | 90.40 | -0.03 |
| 文字错误 | 79 | 77 | -2 ✓ |

**结论**：OCR 识别对上下文边距不敏感，无显著改进。

### 实验 4：PP-OCRv5 全链路适配（最终成功）

**方法**：
1. 检测模型：PP-OCRv4 → PP-OCRv5
2. 识别模型：PP-OCRv4 → PP-OCRv5
3. CC refinement：`overlap_ocr` 限制在 `merge_radius * 0.5` 距离内
4. 列过滤：增加中位字符面积 >= 12000px 检查
5. merge_radius：100 → 50

| 指标 | PP-OCRv4 基线 | PP-OCRv5 适配 | 变化 |
|------|--------------|--------------|------|
| **得分** | 90.43 | **95.08** | **+4.65** ✓ |
| **边缘误差** | 8.8px | **3.9px** | **-56%** ✓ |
| **文字错误** | 79 | **58** | **-27%** ✓ |
| **文字准确率** | 94.0% | **95.6%** | +1.6% ✓ |
| 漏检 | 1 | 3 | +2 |
| 误检 | 10 | 21 | +11 |

**成功关键**：`overlap_ocr` 不再无条件包含重叠组件，限制在 `merge_radius * 0.5` 距离内。

## PP-OCRv5 适配过程中的尝试

| 尝试 | 方法 | 结果 | 原因 |
|------|------|------|------|
| 1 | 直接使用 v5 检测 | 73.01 ❌ | 检测框太宽，CC refinement 搜到相邻字符 |
| 2 | median_area 列过滤 | 77.45 ❌ | 注释列面积与书法列接近 |
| 3 | 增大 expand_padding | 90.40 ⚪ | OCR 识别对边距不敏感 |
| 4 | CC drift check | 75.05 ❌ | 丢弃正确 refined box |
| 5 | 搜索区域裁剪到检测框 | 57.3 ❌ | 裁剪太激进 |
| **6** | **overlap_ocr 限制 + 面积过滤** | **95.08 ✓** | **最终方案** |

## 最终配置

```python
# pipeline.py
config = {
    "min_chars_per_col": 2,
    "min_char_width": 100,
    "min_char_height": 100,
    "size_threshold": 120,
    "binary_threshold": 140,
    "bbox_padding": 5,
    "merge_radius": 50,
}

# char_segmenter.py - get_ocr_char_boxes
ocr = RapidOCR(params={
    'Det.ocr_version': OCRVersion.PPOCRV5,
    'Rec.ocr_version': OCRVersion.PPOCRV5,
})

# char_segmenter.py - refine_char_bbox
if dist < merge_radius or (overlap_ocr and dist < merge_radius * 0.5):

# char_segmenter.py - filter_calligraphy_columns
median_area = sorted(areas)[len(areas)//2]
if median_area < 12000: continue
```

## v4/v5 兼容性验证

在当前改动下（overlap_ocr 限制、median_area 过滤、merge_radius=50），v4 和 v5 得分完全一致（95.08）。原因：

1. **overlap_ocr 限制对 v4 无害**：v4 框窄（~141px），不会触发 overlap 兜底
2. **median_area 过滤对 v4 无影响**：v4 检测的注释字符面积已足够小
3. **merge_radius=50 对 v4 兼容**：v4 搜索区域内组件更少，50px 足够
4. **文字错误一致（58）**：pipeline 的 `original_text` 优先逻辑（score≥0.6 直接用检测文本）决定了识别质量，v4/v5 的检测文本相同

**结论**：改动向后兼容，v4 和 v5 均可使用。

## 对比图

- `output/exp/v5adapt3/viz/page_024_gt.png` — GT（白色框）
- `output/exp/v5adapt3/viz/page_024_v4_baseline.png` — PP-OCRv4 基线（橙色框）
- `output/exp/v5adapt3/viz/page_024_v5_adapted.png` — PP-OCRv5 适配（绿/橙/红按置信度）
