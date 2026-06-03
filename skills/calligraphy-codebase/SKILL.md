---
name: calligraphy-codebase
description: Knowledge base for the 书法练习助手 (calligraphy practice assistant) project. Use this whenever the user asks about project architecture, module structure, config parameters, code conventions, file paths, reading order rules, output directory layout, or any technical question about the OCR pipeline, review GUI, char viewer, compose layout engine, or Obsidian integration. This skill replaces reading AGENTS.md and docs/ files — use it for any project-related technical question to save time and avoid context waste.
---

# Skill: Calligraphy Codebase Knowledge

## Overview

将竖排/横排书法字帖逐字切割、OCR 识别、人工校对、浏览检索、集字排版，建立可检索的 Obsidian 字库。

**项目定位：** 书法练习助手（非纯字帖校对系统）
**Repository:** `D:\notebooks\handwriting`
**主分支:** `main` | 横排支持分支: `feat/horizontal-layout`

## Architecture

```
pipeline.py → _ocr_results.json → review_server.py (GUI校对)
                                        ↓ submit
                              /submit → sliced images + Obsidian char DB
                                              ↓
                              char_viewer.py (port 5001)
                                ├── / (char browser, Fabric.js)
                                └── /compose (Pillow layout engine)
                                     └── export PNG / PDF
```

## Modules

### `pipeline.py` — 全流程入口
- `python pipeline.py N --no-correct` 处理单页
- 内部调用链：`pdf_renderer` → `page_preprocessor` → `char_segmenter` → `ocr_recognizer` → `confidence_handler`
- `process_page` 接收 `layout_direction` 参数（默认读 config）

### `src/pdf_renderer.py` — PDF→PNG
- 使用 pypdfium2（Chromium PDFium 引擎），质量优于 PyMuPDF
- 默认 `dpi_scale=2`，输出 ~200 DPI，2496×3720 像素
- 文件名：`page_{N:03d}.png`，保存到 `output/pages/`

### `src/page_preprocessor.py` — 页面预处理
- 预处理结果仅用于调试，Pipeline 实际用原始灰度图
- 步骤：加载 → 内容裁剪 (`detect_content_bbox`, 阈值50) → 去网格线 → CLAHE 增强

### `src/char_segmenter.py` — 字符切割（核心）
- `segment_characters(gray, config)` 调用全部子函数
- 子函数链：`detect_main_content_bbox` → `get_ocr_char_boxes` → 标点过滤 → `classify_columns` → `split_mixed_columns` → `filter_calligraphy_columns` → `detect_missing_chars_in_gaps` → `refine_char_bbox` → `remove_overlapping_boxes` → 后处理
- 接受 `layout_direction` 参数适配竖排/横排
- OCR 模块用 RapidOCR（`return_word_box=True`），字级边界框

### `src/ocr_recognizer.py` — OCR 识别
- `original_score >= 0.6` 时复用原文，否则重新 OCR
- 裁剪为正方形后识别，失败时回退到未扩展裁剪

### `src/confidence_handler.py` — 置信度分类 + JSON 导出
- 分类：high (≥0.8), medium (≥0.5), low (≥0.3), unrecognized (空文本)

### `review_server.py` — 校对 GUI (Port 5000)
- Flask 单文件应用，前端 HTML/CSS/JS 内嵌
- 数据源：`_ocr_results.json` + `_corrected.json`（按 `orig_idx` 合并）
- 提交：裁剪 4px → 切片 PNG → 更新 Obsidian 字库 → 标记 reviewed
- 状态：unprocessed / ready / submitted / pending / skipped
- 多书帖支持：`?cb=profile_name` 查询参数
- 页面级元数据：`page_{N:03d}_meta.json`
- 阅读顺序：竖排 RTL (`-col, row`) / 横排 LTR (`col, row`)
- 段落视图根据 layout_direction 自适应

### `char_viewer.py` — 字符查看器 + 集字排版 (Port 5001)
- 索引自动重建（每次 API 调用扫描文件系统）
- 四种图像模式：original / enhanced / bilateral / binary
- 墨心居中、反色、米字格/田字格

### `src/compose_renderer.py` — 排版引擎
- `render_composition(chars, variants, params)` 返回 Pillow Image
- **关键规则：** 二进制字图绝不缩放、格子 = max_char_dim × 1.15
- 背景：beige / white / black / red / gold_fleck / grass
- 标点：格子 45% 覆盖层，右下角定位
- 导出 PNG（客户端）/ PDF（fpdf2 服务端）

## Config (`config.py`)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `DPI_SCALE` | 2 | PDF 渲染倍率 |
| `LAYOUT_DIRECTION` | `"vertical"` | 书帖排向 (`vertical`/`horizontal`) |
| `BINARY_THRESHOLD` | 140 | 二值化阈值 |
| `CALLIGRAPHER` | `"吴玉生"` | 默认书家 |
| `SOURCE_TEXT` | `"红楼梦"` | 默认字帖 |
| `PDF_PATH` | | PDF 文件路径 |
| `OBSIDIAN_VAULT` | | Obsidian 仓库根路径 |
| `COPYBOOK_PROFILES` | `{"default": {...}}` | 多书帖配置 |

### `char_segmenter.py` 关键参数（通过 config dict 传入）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `gap_threshold` | 80 | 遗漏字符合并间距 |
| `merge_radius` | 100 | 连通域合并半径 |
| `search_margin_x` | 40 | OCR 框 X 搜索范围 |
| `search_margin_y` | 100 | OCR 框 Y 搜索范围 |
| `size_threshold` | 120 | 大字/小字分类阈值 |
| `min_col_width` | 130 | 有效列最小宽度 |
| `min_chars_per_col` | 3 | 有效列最少字符数 |

## 阅读顺序

| layout_direction | 排序 | 含义 |
|---|---|---|
| `vertical` | `(-col, row)` | 列右→左，行上→下 |
| `horizontal` | `(col, row)` | 行上→下，列左→右 |

## Output 目录结构

```
output/
  pages/                        # Pipeline 输出（git ignored）
    page_NNN_ocr_results.json   # OCR 检测结果
    page_NNN_corrected.json     # 手动修正叠加（orig_idx 关联）
    page_NNN_reviewed.json      # 提交标记
    page_NNN_skipped.json       # 跳过标记
    page_NNN_meta.json          # 页面级元数据（calligrapher/source/layout）
    page_NNN.png                # PDF 渲染图
    page_NNN_processed.png      # 预处理后图（调试用）
  characters/                   # Pipeline 切割单字（按列/行编号）
  cropped/{calligrapher}/{source_text}/
    page_NNN/                   # GUI 提交裁剪（阅读顺序编号）
      001_此.png
      002_书.png
      ...
```

## Commands

```bash
# Pipeline 单页
python pipeline.py 24 --no-correct

# 校对 GUI
python review_server.py  → http://127.0.0.1:5000

# 字符查看器 + 集字排版
python char_viewer.py  → http://127.0.0.1:5001

# 快捷启动
start_review.bat
start_char_viewer.bat
```

## Conventions

- **文件命名：** 调试图用英文/下划线（PowerShell 编码），切片用 `{seq:03d}_{char}.png`
- **Canvas 坐标：** `cssX = b.x / gs()`，`gs() = img.naturalWidth / img.offsetWidth`
- **cv2 中文路径：** 用 `cv2.imdecode(np.fromfile(path, ...), ...)` 处理 Unicode 文件名
- **Fabric.js 注意：** v5.3.0 无 `sendObjectToBack`，网格需要在添加图像前绘制
- **aggressive cleaning：** 提交前 `shutil.rmtree` 旧裁剪目录，再重建
- **优先 original_text：** OCR 识别优先用检测阶段的原文（score≥0.6），避免二次识别损失精度
