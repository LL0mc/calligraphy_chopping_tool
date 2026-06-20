# Project Notes

## Core Principles
- `write` tool is banned for existing files — always `read` then `edit`
- Pipeline v20: PP-OCRv5 detection + recognition, merge_radius=50, noise filter, last-page memory
- `detect_main_content_bbox` cropping before OCR improves recall on vertical text
- Dilate kernel: aids feibai stroke detection for localization only; final crop on original image
- Small-annotation characters merge into main column, never discarded
- Dedup IoU threshold 0.3, keep larger box

## Pipeline (v20)

### Flow
1. **Render** → grayscale 2496×3720 (A4-proportional)
2. **Content crop** → `detect_main_content_bbox` sliding window
3. **OCR raw detection** → `get_ocr_char_boxes` via RapidOCR (char-level, with original text + confidence)
4. **Punctuation filter** → exclude punctuation & empty boxes, record as `punctuation_boxes`
5. **Column clustering** → X-center clustering, sub-column split, small-char merge, column-width filter
6. **Missing char detection** → `detect_missing_chars_in_gaps`:
   - Gap merge distance: 80px (up from 40, fixes 枉 split)
   - Column-tail search limit: ≤ 2×avg_height
   - Ink-tail check: candidate < 25% avg_height from char above → skip
   - Overlap check: candidate overlaps >50% with char above → skip
7. **CC refinement** → `refine_char_bbox`:
   - Punctuation exclusion: component center inside punctuation_boxes & no OCR overlap → skip
   - `claimed_regions`: top-to-bottom per-column, prevents downstream char stealing components
   - Oversize fallback: area > 2×OCR area → exclude ROI-boundary-touching components
8. **OCR recognition** → `recognize_characters` prefers `original_text` (score≥0.6), re-OCR only when empty
9. **Dedup** → `remove_overlapping_boxes`: IoU 0.3, keep larger
10. **Post-process** → per-column outlier shrink: 3× median area threshold
11. **Noise filter** → remove empty-text low-confidence boxes (PP-OCRv5 full-column noise)

### Three Key Fixes (2026-05-23)
1. `ocr_recognizer.py`: prefer `original_text`/`original_score` over re-OCR
2. `char_segmenter.py`: gap merge distance 40→80
3. `char_segmenter.py`: column-tail triple guard — search ≤2×avg_h, ink-tail skip, overlap >50% skip

### PP-OCRv5 Adaptation
- merge_radius 100→50
- median_area ≥ 12000 列过滤
- 噪声过滤：空文字 conf<0.5
- overlap_ocr 限制已移除（经实验验证不影响效果，反而伤害识别）

### v4 vs v5 实验结论（29 页基线）

| 指标 | v4 基线 | v5 最终方案 | 变化 |
|------|--------|-----------|------|
| 平均分 | 90.15 | **94.27** | **+4.12** |
| 误检 | 474 | 23 | -451 |
| 漏检 | 7 | 7 | 0 |
| 文字错误 | 66 | 66 | 0 |
| 文字准确率 | 95.1% | 95.1% | 0 |

**关键发现：**
- PP-OCRv5 检测并不比 v4 更好——产生更多噪声框（3486 vs 3180），需要更多后处理
- overlap_ocr 距离限制是过度工程化，去掉后效果不变（claimed_regions 已足够防重复）
- 文字错误从 84 降回 66 是因为去掉了 overlap_ocr 限制，框不再被截断

## Compose Layout Engine (v20 added)
- **`src/compose_renderer.py`**: Pillow-based layout engine
  - Auto cell size = `max(max_char_w, max_char_h) × 1.15` — never overflows
  - Binary images loaded at original resolution, NEVER pre-scaled
  - RGBA chars pasted at original pixel size (no per-char scaling)
  - Vertical/horizontal, LTR/RTL directions
  - Newline → column break; space → blank cell
  - Punctuation: small overlay (45% of cell), bottom-right, font 70% of overlay
  - Background colors baked; gold_fleck and grass rendered as full-res Pillow patterns
  - Gold fleck: irregular polygons (5–10 sides, radius 5–18), density w×h/6000
  - Grass: 4-angle fibers, 50–200px, width 3–6, alpha 25–60
  - 5 text colors (black / white / ink_blue / gold / red)
  - Left margin = gap × 2

- **Web GUI** (`/compose` on port 5001):
  - Search sidebar: char-by-char variant selector with thumbnails
  - Param bar: cols, direction, char_size, gap, bg, text_color
  - Zoom slider (0.1–5.0, step 0.01), ZOOM_BASE=0.40
  - Click-to-select: maps textIdx→dataIdx via newline offset
  - Export PNG: client-side download from cached blob
  - Export PDF: server endpoint via fpdf2, full-resolution embed

## Digital Ink Frontend Redesign (v20)

全面升级三个前端页面（review_server、char_viewer、compose）的视觉风格：

- **CSS 变量系统** — `:root` 全局 tokens（`--bg-deep`、`--glass-*`、`--accent-*`、`--font-*`），统一维护
- **双主题切换** — 深色 `#0e1420`（蓝灰色调）/ 浅色 `#f2e8c8`（暖黄），localStorage 持久化，tab 栏一键切换
- **玻璃拟态** — 面板 `backdrop-filter: blur(12px)` 半透明毛玻璃效果 + 微光边框
- **蓝色强调** — `#4a7cf7` 聚焦辉光，按钮/输入框焦点发光反馈
- **无框设计** — 按钮和输入框去掉硬边框，纯半透明底色悬浮
- **排版升级** — Google Fonts（Noto Sans SC、ZCOOL QingKe HuangYou、JetBrains Mono）
- **集字排版** — 统一 `.btn-primary`（蓝辉光）/ `.btn-success`（绿辉光）按钮体系，变体缩略图 flex-wrap 左对齐排列
- **新增框保存 bug 修复** — `save_char()` 中 `and not c.get('added')` 导致重复 correction 记录，切换页面后位置/文字丢失

## Known Issues (unfixed)
- **巷** (p30, left boundary): left stroke 39px outside refine box — inter-char gap > merge_radius from OCR center
- **Feibai** (broken strokes): broken-stroke gaps connect to outer whitespace, excluding candidate components
- **Red-circle annotations**: mistaken as chars by OCR, affecting refine and layout
- **Punctuation-char adhesion**: small marks merge with strokes in binary image

## Fixed Issues
- **光** (p78): right na-stroke small component (6×14px), 115px from OCR center > merge_radius=50. Fix: merge_radius=50 distance check + claimed_regions 防重复
- **P24/P184/P210 tail ink false positives**: tail search ≤2×avg_height, P210 -7 false boxes
- **枉** (p24 split): gap merge distance 40→80, two halves (69.6px apart) merged
- **口述偏移** (p184 gap false): ink-tail + overlap check excludes 53×23 ink dot

## Filename Conventions
- Debug output images: English/underscore only (PowerShell encoding), e.g. `page_024_step3_raw_ocr.png`
- Sliced chars: `{seq:03d}_{char}.png`, e.g. `001_此.png` (reading order: RTL cols, top-down rows)

## Architecture
### Overview
```
pipeline.py → _ocr_results.json → review_server.py (GUI review)
                                         ↓ submit
                              /submit → sliced images + Obsidian char DB
                                              ↓
                              char_viewer.py (port 5001)
                                ├── / (char browser, Fabric.js)
                                └── /compose (layout engine, Pillow)
                                     └── export PNG / PDF
```

### Output Directory Structure

```
output/
├── pages/          ← page-level data (pipeline + review_server 读写)
└── cropped/        ← review_server submit 产出的裁剪字符图（仅供 char_viewer/compose 读）
```

#### `output/pages/` — 页面数据

| 文件 | 生成者 | 消费者 | 说明 |
|------|--------|--------|------|
| `page_{num}.png` | pipeline | review_server | PDF 渲染原图 |
| `page_{num}_processed.png` | pipeline | review_server | 预处理后（增强对比度+内容裁剪） |
| `page_{num}_ocr_results.json` | pipeline | review_server, evaluator | **生产文件** — 当前 OCR 结果 |
| `page_{num}_ocr_results_baseline.json` | 手动 copy | evaluator | **不可变快照** — GT 基线 |
| `page_{num}_corrected.json` | review_server | evaluator, load_data() | 人工修正（文字/增删框） |
| `page_{num}_reviewed.json` | review_server | evaluator | 提交标记 |
| `page_{num}_skipped.json` | review_server | review_server | 跳过标记 |

#### `output/cropped/` — 裁剪字符图

```
cropped/{calligrapher}/{source_text}/page_{num}/{seq:03d}_{char}.png
```
review_server `/submit` 产出，按阅读顺序编号+字符命名。4px padding。供 char_viewer 和 compose 使用。

### Experiment Workflow

**原则：实验不碰生产数据。**

- 使用 git 分支管理实验（`feat/xxx`）
- 实验产出写入 `output/exp/{实验名}/`，不写 `output/pages/`
- **`python pipeline.py N` 会覆盖 `output/pages/page_N_ocr_results.json`（生产数据）**。实验必须用 `python pipeline.py N --output-dir output/exp/{实验名}/`
- 评估器通过 `--det-dir` 参数指向实验目录
- baseline.json 和 corrected.json 只从 `output/pages/` 读取，不修改
- 如误覆盖生产数据，从 `_ocr_results_baseline.json` 恢复

### Obsidian Char DB
```
{obsidian_vault}/字库/{calligrapher}/{source_text}/{char}.md
```
One note per char. Frontmatter: char/calligrapher/source for Dataview. Table of all occurrences with image embed + confidence + context (3 chars before/after).

### Reading Order
- Columns: right→left (col descending)
- Rows: top→bottom (row ascending)
- Applies to: box indices, list sort, paragraph view, prev/next navigation

### GUI (review_server.py) — Port 5000
- Box colors: red (?/low conf), yellow (non-square shape), blue (normal), gray (empty), cyan (corrected), green (selected)
- Auto-save: on char switch, drag-end, Enter
- Paragraph view: full text (col-separated) in right panel
- Submit: slice + update Obsidian, then advance to next page

### Char Viewer (char_viewer.py) — Port 5001
- Tab bar: 字库浏览 / 集字排版
- Char browser: Fabric.js 5.3.0, 240×240 canvas, search, 4 modes (original/enhanced/bilateral/binary), invert, mizige/tianzi grid
- Compose layout: Pillow-based full-res engine, click-to-select variant, export PNG/PDF

## Commands
- Review GUI: `python review_server.py` → http://127.0.0.1:5000/?p=24
- Char viewer: `python char_viewer.py` → http://127.0.0.1:5001/
- Compose: http://127.0.0.1:5001/compose
- Pipeline single page: `python pipeline.py N --no-correct`
- Start scripts: `start_review.bat`, `start_char_viewer.bat`

## Extension: 横排 + 多书帖 (branch: feat/horizontal-layout)

### Status: 🚧 已实现，分支已推送

**横排支持** — `char_segmenter.py`:
- `classify_columns` 按 Y 中心聚为行
- `detect_missing_chars_in_gaps` 横排查 X 间隙
- `refine_char_bbox` 互换 search_margin
- `segment_characters` 内部按 X 排序

**多书帖** — `review_server.py`:
- `page_{num}_meta.json`：每页独立 calligrapher/source_text/layout_direction
- Toolbar 书帖下拉选择器（COPYBOOK_PROFILES + auto-discover）
- 阅读顺序自适应（竖排 RTL / 横排 LTR）
- `/api/copybooks` + `/api/meta` 端点

**待测试（未验证）：**
- 横排真实字帖的实际 Pipeline 效果
- 横排 missing char 检测的准确率
- 书帖切换后 page_meta 的流转
- 横排段落视图（updatePara）的正确性

### How to use
```bash
git checkout feat/horizontal-layout
# 在 config.py 中设置 LAYOUT_DIRECTION = "horizontal"
# 或通过 COPYBOOK_PROFILES 添加横排书帖
python pipeline.py N --no-correct
python review_server.py
```

## Refactoring & Testing

完整的分析与计划见 `docs/refactoring_plan.md`。

- **Phase 1:** `src/types.py` 引入 DataClass（CharBox / OcrResult / Column），消除魔数索引
- **Phase 2:** 第一梯队单元测试（纯逻辑函数：remove_overlapping_boxes / expand_box / classify_columns 等）
- **Phase 3:** 第二梯队单元测试（合成图像：detect_main_content_bbox / detect_missing_chars_in_gaps / refine_char_bbox）
- **Phase 4:** 集成测试（黄金输出回归）
