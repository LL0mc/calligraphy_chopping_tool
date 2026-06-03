# Project Notes

## Core Principles
- `write` tool is banned for existing files — always `read` then `edit`
- Pipeline v19: OCR + connectivity-domain refinement for broken strokes (feibai)
- `detect_main_content_bbox` cropping before OCR improves recall on vertical text
- Dilate kernel (config param): aids feibai stroke detection for localization only; final crop on original image
- Small-annotation characters merge into main column, never discarded
- Dedup IoU threshold 0.3, keep larger box

## Pipeline (v19)

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

### Three Key Fixes (2026-05-23)
1. `ocr_recognizer.py`: prefer `original_text`/`original_score` over re-OCR
2. `char_segmenter.py`: gap merge distance 40→80
3. `char_segmenter.py`: column-tail triple guard — search ≤2×avg_h, ink-tail skip, overlap >50% skip

## Compose Layout Engine (v19 added)
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

## Known Issues (unfixed)
- **巷** (p30, left boundary): left stroke 39px outside refine box — inter-char gap > merge_radius from OCR center
- **Feibai** (broken strokes): broken-stroke gaps connect to outer whitespace, excluding candidate components
- **Red-circle annotations**: mistaken as chars by OCR, affecting refine and layout
- **Punctuation-char adhesion**: small marks merge with strokes in binary image

## Fixed Issues
- **光** (p78): right na-stroke small component (6×14px), 115px from OCR center > merge_radius=100. Fix: `overlap_ocr` components always kept regardless of distance
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

### Sliced Storage
```
output/cropped/{calligrapher}/{source_text}/page_{page:03d}/{seq:03d}_{char}.png
```
4px padding. calligrapher & source_text from config.py.

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
