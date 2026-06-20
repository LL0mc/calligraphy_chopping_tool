# Pipeline 检测模块详解

## 概述

Pipeline（`pipeline.py`）是系统的检测入口，接收 PDF 页面编号，输出每个字符的边界框、识别文本和置信度。结果是 JSON 文件，供后续 GUI 人工校对使用。

调用命令：`python pipeline.py <页码> --no-correct`

> `--no-correct` 已弃用，保留仅为向后兼容。

可选参数：

| 参数 | 说明 |
|------|------|
| `--output-dir <path>` | 实验输出目录（默认写入 `output/pages/`） |

## 模块调用顺序

```
pdf_renderer.py → page_preprocessor.py → char_segmenter.py → ocr_recognizer.py → confidence_handler.py
```

---

## 步骤 1：PDF 渲染（pdf_renderer.py）

**入口函数：** `render_pdf_page(pdf_path, page_index, output_dir, dpi_scale=2)`

- 使用 `pypdfium2` 打开 PDF 文件。
- 渲染指定页面，默认 `dpi_scale=2`（约 200 DPI），输出 2496×3720 像素的灰度 PNG。
- 文件名：`page_{页码:03d}.png`，保存到 `output/pages/`。

**要点：** PDFium 是 Chromium 的 PDF 引擎，渲染质量比 PyMuPDF 更接近原版。`dpi_scale` 可调，越高字符边缘越清晰，但文件更大、处理更慢。

---

## 步骤 2：页面预处理（page_preprocessor.py）

**入口函数：** `preprocess_page(image_path, output_path, remove_lines=True)`

预处理结果仅用于调试查看，Pipeline 实际使用的是**原始灰度图**。步骤顺序：

### 2a. 加载图像（`load_image`）
- `cv2.imread(path, cv2.IMREAD_GRAYSCALE)` 加载为灰度图。

### 2b. 内容区域检测（`detect_content_bbox`）
- 阈值 50（灰度值 ≤ 50 视为"暗像素"，即墨水）。
- 水平投影：统计每行暗像素数。行暗像素占比 > 2% 即视为内容行。
- 垂直投影：同理，列暗像素占比 > 2% 即视为内容列。
- 取首个/末个内容行/列，外扩 5px，得 `(y_min, y_max, x_min, x_max)`。
- 若无任何内容行/列，返回全图范围 `(0, h, 0, w)`。

### 2c. 去除网格线（`remove_grid_lines`）
- 仅 `remove_lines=True` 时执行。
- 二值化（阈值 140，反色）。
- 形态学开运算：水平核 50×1 → 检测水平线，垂直核 1×50 → 检测垂直线。
- 二者 OR 为 `grid_mask`，从二值图中减去，再反转回白底黑字。

### 2d. 增强对比度（`enhance_contrast`）
- CLAHE（`clipLimit=2.0, tileGridSize=(8,8)`）。

---

## 步骤 3：字符切割（char_segmenter.py）

**入口函数：** `segment_characters(gray, config)` — 核心步骤，约 90% 的工程量。

### 3a. 主内容区域检测（`detect_main_content_bbox`）

- **不同于 step 2b**，这里是滑窗方式，专为裁剪 OCR 输入。
- 参数：`min_density_ratio=0.15`，`window=100`（步长 10）。
- 创建暗像素掩膜（`gray < 130`）。从每侧边缘向中心滑动窗口，找到第一个平均暗像素密度 > 阈值的窗口，再外扩 20px。
- 若某侧无检测结果，返回全图边界（与 step 2b 不同——step 2b 返回 (0,0,w,h)，这里也是）。

**为什么要做两次内容裁剪？** Step 2b 裁剪预处理后的图像（用于保存和调试）；Step 3a 裁剪原始灰度图（用于 OCR 检测）。垂直书帖页面边缘常有大片空白，裁剪后 OCR 在竖排上的检测稳定性显著提升。

### 3b. OCR 原始检测（`get_ocr_char_boxes`）

- 调用 `RapidOCR(PP-OCRv5, return_word_box=True)`，获取字级边界框。
- PP-OCRv5 检测模型比 PP-OCRv4 更宽（~220px vs ~141px），能捕获完整字符（包括笔画末端）。
- RapidOCR 返回 `word_results`，其中每个 WordResult 包含逐字符的 `(text, score, box)`。
- `box` 为四边形（4 个点），取其 x/y 的 min/max 转为矩形 `(x_min, x_max, y_min, y_max)`。
- 坐标从裁剪图空间转换回原图空间。

**为什么用 PP-OCRv5？** PP-OCRv5 检测框更宽，能捕获完整字符笔画，减少遗漏。配合 CC refinement 的 overlap_ocr 限制，框定位精度比 PP-OCRv4 提升 56%（8.8px→3.9px）。

### 3c. 标点过滤

- `punctuation_set` 包含常见中英文标点：`，。、；：？！,.;:?!""''（）()【】《》等。
- `text` 在标点集中或为空 → 排除。但其边界框记录到 `punctuation_boxes`，供精炼阶段（step 3g）排除标点连通分量。
- 未被标点过滤但置信度低的字符，保留到后续步骤。

### 3d. 分列（`classify_columns`）

- 计算每个字符的 X 中心坐标，按 X 升序排序。
- 从最小的 X 开始，若字符 X 中心与当前簇平均 X 之差 ≤ 100px，归入同一列；否则新建一列。
- 输出：`(col_idx, x_min, x_max, [chars...])`，按 X 排序。

### 3e. 子列拆分（`split_mixed_columns`）

- 参数 `size_threshold=120`：宽 ≥ 120 且高 ≥ 120 为"大字"。
- 若同一列中既有大字又有小字（注释/旁注）：
  - 检查小字 X 范围与大字重叠率 ≥ 50% → 小字为行内注释，合并回大字列。
  - 否则，小字成为独立的子列。
- 输出：重排后的列列表，大字在前（右侧），小字在后（左侧），符合竖排阅读顺序。

### 3f. 列过滤（`filter_calligraphy_columns`）

- 过滤条件：列宽 ≥ 130px、字符数 ≥ 2、**中位字符面积 ≥ 12000px²**。
- 130px 的依据：书法主列通常 140–240px，旁注列通常 60–110px，130px 是有效分隔值。
- 面积过滤：PP-OCRv5 检测的注释字符面积（~8000px²）远小于书法字符（~22000px²），12000px² 阈值可有效分离。
- 过滤后重新按 X 排序、赋索引。

### 3g. 遗漏字符检测（`detect_missing_chars_in_gaps`）

按列检测 OCR 漏检的飞白/淡墨字。两个阶段：

**阶段一：字间间隙**
- 遍历列内每对相邻字符（已按 Y 排序）。若垂直间距 > `gap_threshold=80`（从 40 上调以修复"枉"字分裂问题），提取间隙 ROI。
- 暗像素比率 > 15% 才有进一步分析价值。
- 连通域分析，筛选条件：面积 ≥ 300、X 范围在列宽内、宽高比 0.2–5.0、最小尺寸 50×50。
- 距离 < 80px 的相邻组件合并为一个候选框。

**阶段二：列尾搜索**
- 在列末字符下方搜索，范围限制 ≤ 2×avg_height（防止误吸远处墨迹）。
- 候选筛选：
  - 面积 ≥ 150（`min_area * 0.5`）。
  - **Ink-tail 检查**：候选与上一字符间距 < avg_height × 25% → 跳过（修复 P210 列尾 7 个假阳性）。
  - **重叠检查**：候选与上一字符重叠 > 50% 面积 → 跳过（修复 P184 墨点误检）。
- 取面积最大的候选框作为遗漏字符，标记为 `text='?'`，`score=0.0`。

### 3h. 连通域精炼（`refine_char_bbox`）

核心精炼步骤，对每个字符精确裁剪。按列从上到下逐字处理。

**输入：** OCR 初始框 + 搜索范围参数 + 每列 `claimed_regions`（已声明区域列表）。

**步骤：**
1. 定义搜索 ROI：OCR 框外扩 `search_margin_x=40`、`search_margin_y=100`。
2. ROI 二值化（阈值 140），8 连通域分析。
3. 对每个面积 ≥ 20 的连通分量：
   - **与 OCR 框重叠** → 无条件保留。
   - **标点排除**：分量中心在 `punctuation_boxes` 内、且不与 OCR 框重叠 → 跳过。
   - **距离检查**：与 OCR 中心距离 < `merge_radius=50` → 候选。
   - **重叠检查**：与 OCR 框重叠且距离 < `merge_radius/2` → 候选（防止宽检测框中的相邻字符被错误合并）。
   - **已声明区域检查**：分量中心在 `claimed_regions` 内 → 跳过（防止后字窃取前字笔画）。
4. 无候选 → 返回原 OCR 框。
5. 合并所有候选：取 min/max extents，外扩 `padding=5`，裁切到图像边界。
6. **过大回退**：若精炼框面积 > 2×OCR 框面积（且 OCR 面积 > 1000），排除接触 ROI 边界的组件，仅保留内部组件重新计算。

**注意：** `overlap_ocr` 分量仅在距离 < `merge_radius/2` 时保留（防止 PP-OCRv5 宽检测框中的相邻字符组件被错误合并）。

### 3i. 去重（`remove_overlapping_boxes`）

- 按面积降序排序（贪婪：保留最大框）。
- 遍历，IoU ≤ 0.3 者保留。
- 重新按 `(col_idx, row_idx)` 排序。

### 3j. 后处理：按列异常框缩小

- 按列计算面积中位数。若某框面积 > 中位数 × 3（且中位数 > 1000），缩小至 `sqrt(median_area)` 的正方形，保持中心位置。

### 3k. 拼接结果

所有列按阅读顺序（列 X 降序 → 行 Y 升序）拼为最终列表。

---

## 步骤 4：OCR 识别（ocr_recognizer.py）

**入口函数：** `recognize_characters(gray, characters, engine, expand_strategy, expand_padding)`

对每个字符：
1. 若 `original_text` 非空且 `original_score ≥ 0.6` → 直接使用原文，不重新 OCR。
2. 否则，用 `expand_box` 外扩裁剪区域（默认 `strategy="square"`，外扩 `padding=15`，使裁剪区域为正方形）。
3. 对裁剪图调用 RapidOCR 识别。若结果为空且 expand 策略非 `"none"`，回退到未扩张的原始裁剪重试。
4. 取结果第一个字符（处理多字符返回）。

**输出字段：** `x, y, w, h, col_idx, row_idx, original_text, original_score, ocr_text, ocr_score, expand_strategy`

**为什么优先用 original_text？** OCR 检测阶段的 RapidOCR 已在原图上定位识别一次，若置信度已足够高（≥ 0.6），再次裁剪识别可能因边框变化反而降低结果。优先使用原始结果更稳定。

---

## 步骤 5：置信度分类与导出（confidence_handler.py）

### 分类（`classify_by_confidence`）

| 类别 | 条件 |
|------|------|
| 高置信度（high） | `ocr_text` 非空且 score ≥ 0.8 |
| 中置信度（medium） | score ≥ 0.5 |
| 低置信度（low） | score < 0.5 |
| 未识别（unrecognized） | `ocr_text` 为空 |

### 导出（`export_results`）

输出 JSON 格式（`page_{num}_ocr_results.json`）：
```json
[
  {
    "col": 0,
    "row": 0,
    "text": "此",
    "confidence": 0.97,
    "x": 100, "y": 200, "w": 80, "h": 120,
    "expand_strategy": "square"
  },
  ...
]
```

---

## 关键配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `dpi_scale` | 2 | PDF 渲染倍率，2 = ~200 DPI |
| `binary_threshold` | 140 | 二值化阈值 |
| `gap_threshold` | 80 | 遗漏字符合并间距（从 40 上调） |
| `merge_radius` | 50 | 连通域合并半径 |
| `search_margin_x` | 40 | OCR 框 X 方向外扩搜索范围 |
| `search_margin_y` | 100 | OCR 框 Y 方向外扩搜索范围 |
| `min_chars_per_col` | 2 | 有效列最少字符数 |
| `size_threshold` | 120 | 大字/小字分类阈值 |

完整参数见 `config.py`。
