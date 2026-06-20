# Pipeline Detection Module

## Overview

The Pipeline (`pipeline.py`) is the detection entry point: given a PDF page number, it outputs each character's bounding box, recognized text, and confidence score. Results are saved as JSON for manual proofreading in the GUI.

Command: `python pipeline.py <page_num> --no-correct`

> `--no-correct` is deprecated, kept for backward compatibility.

Optional parameters:

| Parameter | Description |
|-----------|-------------|
| `--output-dir <path>` | Experiment output directory (default: `output/pages/`) |

## Module Call Order

```
pdf_renderer.py → page_preprocessor.py → char_segmenter.py → ocr_recognizer.py → confidence_handler.py
```

---

## Step 1: PDF Rendering (pdf_renderer.py)

**Entry:** `render_pdf_page(pdf_path, page_index, output_dir, dpi_scale=2)`

- Opens PDF via `pypdfium2`.
- Renders the page at `dpi_scale=2` (~200 DPI), outputting a 2496×3720 grayscale PNG.
- Filename: `page_{num:03d}.png`, saved to `output/pages/`.

**Note:** PDFium is Chromium's PDF engine — rendering quality closer to the original than PyMuPDF. Higher `dpi_scale` gives sharper strokes but larger files and slower processing.

---

## Step 2: Page Preprocessing (page_preprocessor.py)

**Entry:** `preprocess_page(image_path, output_path, remove_lines=True)`

Preprocessed output is for debug viewing only — the Pipeline actually uses the **original grayscale image**. Steps in order:

### 2a. Load Image (`load_image`)
- `cv2.imread(path, cv2.IMREAD_GRAYSCALE)`.

### 2b. Content BBox Detection (`detect_content_bbox`)
- Threshold 50 (pixel ≤ 50 is "dark" / ink).
- Horizontal projection: count dark pixels per row. Rows with > 2% dark pixels are content rows.
- Vertical projection: same, columns > 2% dark pixels are content columns.
- Take first/last content row/column, pad 5px → `(y_min, y_max, x_min, x_max)`.
- If no content rows/columns, return full image `(0, h, 0, w)`.

### 2c. Remove Grid Lines (`remove_grid_lines`)
- Only runs when `remove_lines=True`.
- Binarize (threshold 140, invert).
- Morphological open: horizontal kernel 50×1 → detect horizontal lines, vertical kernel 1×50 → detect vertical lines.
- OR both into `grid_mask`, subtract from binary image, invert back.

### 2d. Enhance Contrast (`enhance_contrast`)
- CLAHE (`clipLimit=2.0, tileGridSize=(8,8)`).

---

## Step 3: Character Segmentation (char_segmenter.py)

**Entry:** `segment_characters(gray, config)` — core step, ~90% of the engineering work.

### 3a. Main Content BBox Detection (`detect_main_content_bbox`)

- **Different from step 2b**: this uses a sliding window approach specifically for cropping OCR input.
- Params: `min_density_ratio=0.15`, `window=100` (stride 10).
- Create dark-pixel mask (`gray < 130`). Slide window inward from each edge; find the first window where average dark-pixel density exceeds the threshold, then pad 20px outward.
- If a side has no detection, return full image boundary.

**Why two content crops?** Step 2b crops the preprocessed image (for save/debug); Step 3a crops the raw grayscale (for OCR input). Vertical copybook pages often have large margins — cropping significantly improves OCR stability on vertical text.

### 3b. OCR Raw Detection (`get_ocr_char_boxes`)

- Calls `RapidOCR(return_word_box=True)` for character-level bounding boxes.
- RapidOCR returns `word_results`, where each WordResult contains per-character `(text, score, box)`.
- `box` is a quadrilateral (4 points) — convert to rect `(x_min, x_max, y_min, y_max)` via min/max of x/y.
- Coordinates transformed from crop space back to original image space.

**Why RapidOCR over pure CV?** Running-script (行书) has broken strokes (飞白), ligatures, and light ink that easily break or merge in projection/connected-component methods. RapidOCR has a built-in character segmentation model that locates OCR-recognizable character boundaries and outputs confidence for filtering.

### 3c. Punctuation Filter

- `punctuation_set` covers common Chinese/English punctuation: `，。、；：？！,.;:?!""''（）()【】《》` etc.
- If `text` is in the set or empty → excluded. Its bounding box is recorded in `punctuation_boxes` for the refinement stage (step 3g) to exclude punctuation components.
- Low-confidence chars that pass punctuation filter are kept for subsequent steps.

### 3d. Column Classification (`classify_columns`)

- Compute X-center for each char, sort by X ascending.
- Start from smallest X: if a char's X-center differs from current cluster's average X by ≤ 100px, assign to same column; otherwise start a new column.
- Output: `(col_idx, x_min, x_max, [chars...])`, X-sorted.

### 3e. Sub-column Split (`split_mixed_columns`)

- `size_threshold=120`: chars with both w ≥ 120 and h ≥ 120 are "big chars".
- If a column has both big and small (annotation/旁注) chars:
  - Check if small char's X-range overlaps big char's X-range by ≥ 50% → it's an inline annotation, merge back.
  - Otherwise, it becomes an independent sub-column.
- Output: reordered column list — big columns first (right side), small columns after (left side), matching vertical reading order.

### 3f. Column Filter (`filter_calligraphy_columns`)

- Filter: column width ≥ 130px and char count ≥ 2.
- Rationale for 130px: main calligraphy columns are typically 140–240px, annotation columns 60–110px — 130px is a good separator.
- Re-sort by X and reassign indices after filtering.

### 3g. Missing Character Detection (`detect_missing_chars_in_gaps`)

Detects OCR-missed feibai/light-ink chars per column. Two phases:

**Phase 1: Inter-char gaps**
- For each adjacent pair in a column (Y-sorted). If vertical gap > `gap_threshold=80` (raised from 40 to fix 枉 splitting), extract gap ROI.
- Dark-pixel ratio > 15% required for further analysis.
- Connected-component analysis: area ≥ 300, X-range within column, aspect ratio 0.2–5.0, min size 50×50.
- Adjacent components within 80px merged into one candidate box.

**Phase 2: Column-tail search**
- Search below the last char of the column, limited to ≤ 2× avg_height (prevents distant ink false positives).
- Candidate filter:
  - Area ≥ 150 (`min_area * 0.5`).
  - **Ink-tail check**: candidate distance from char above < 25% of avg_height → skip (fixes P210's 7 tail false positives).
  - **Overlap check**: candidate overlaps > 50% area with char above → skip (fixes P184 ink dot false positive).
- Take the largest candidate as the missing char, mark `text='?'`, `score=0.0`.

### 3h. CC Refinement (`refine_char_bbox`)

Core refinement step — precisely crops each character. Processed top-to-bottom per column.

**Input:** OCR initial box + search range params + per-column `claimed_regions` (list of already-claimed areas).

**Procedure:**
1. Define search ROI: OCR box padded by `search_margin_x=40`, `search_margin_y=100`.
2. Binarize ROI (threshold 140), 8-connected component analysis.
3. For each component with area ≥ 20:
   - **Overlaps OCR box** → unconditionally kept.
   - **Punctuation exclusion**: component center inside `punctuation_boxes` AND no OCR overlap → skip.
   - **Distance check**: distance from OCR center < `merge_radius=50` → candidate.
   - **Claimed-regions check**: component center inside `claimed_regions` → skip (prevents downstream chars from stealing upstream strokes).
4. No candidates → return original OCR box.
5. Merge all candidates: min/max extents, `padding=5`, clamp to image bounds.
6. **Oversize fallback**: if refined area > 2× OCR area (and OCR area > 1000), exclude components touching the ROI boundary, recompute from internal components only.

> Note: Earlier versions used an overlap_ocr distance restriction (extra distance limit when component overlaps OCR box). This was proven to be over-engineering — removing it improved results. The effective mechanisms are merge_radius=50 distance check + claimed_regions prevention.

### 3i. Deduplication (`remove_overlapping_boxes`)

- Sort by area descending (greedy: keep largest box).
- Iterate, keep if IoU ≤ 0.3.
- Re-sort by `(col_idx, row_idx)`.

### 3j. Post-processing: per-column outlier shrink

- Per column: compute median area. If a box area > median × 3 (and median > 1000), shrink to `sqrt(median_area)` square, keep center position.

### 3k. Noise filter

- Empty text + confidence < 0.5 → filter out (PP-OCRv5 full-column noise boxes, area up to 100K+ pixels).

### 3l. Assemble Results

All columns concatenated in reading order (col X descending → row Y ascending).

---

## Step 4: OCR Recognition (ocr_recognizer.py)

**Entry:** `recognize_characters(gray, characters, engine, expand_strategy, expand_padding)`

For each character:
1. If `original_text` is non-empty and `original_score ≥ 0.6` → use original, no re-OCR.
2. Otherwise, expand crop region via `expand_box` (default `strategy="square"`, `padding=15`).
3. Re-OCR the crop via RapidOCR. If result is empty and expand strategy is not `"none"`, fall back to unexpanded crop.
4. Take first character of result (handles multi-char returns).

**Output fields:** `x, y, w, h, col_idx, row_idx, original_text, original_score, ocr_text, ocr_score, expand_strategy`

**Why prefer original_text?** RapidOCR already localized and recognized the character on the full image during the detection stage. If the confidence is already high (≥ 0.6), re-cropping may actually degrade quality due to different borders. Using the original is more stable.

---

## Step 5: Confidence Classification & Export (confidence_handler.py)

### Classification (`classify_by_confidence`)

| Class | Condition |
|-------|-----------|
| High | `ocr_text` non-empty and score ≥ 0.8 |
| Medium | score ≥ 0.5 |
| Low | score < 0.5 |
| Unrecognized | `ocr_text` empty |

### Export (`export_results`)

Output JSON format (`page_{num}_ocr_results.json`):
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

## Key Config Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `dpi_scale` | 2 | PDF render scale, 2 = ~200 DPI |
| `binary_threshold` | 140 | Binarization threshold |
| `gap_threshold` | 80 | Missing char merge distance (raised from 40) |
| `merge_radius` | 50 | CC merge radius |
| `search_margin_x` | 40 | OCR box X-direction search margin |
| `search_margin_y` | 100 | OCR box Y-direction search margin |
| `min_chars_per_col` | 2 | Minimum chars for a valid column |
| `size_threshold` | 120 | Big/small char classification threshold |

Full parameters in `config.py`.
