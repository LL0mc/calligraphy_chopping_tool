# Web Application Module Details

## Overview

After Pipeline finishes character detection, three web applications handle manual proofreading, browsing/search, and composition layout:

- **Review Server** (Port 5000): `review_server.py` — manual proofreading of OCR results
- **Char Viewer** (Port 5001): `char_viewer.py` — browse and search submitted characters
- **Compose Layout** (Port 5001 /compose): `char_viewer.py` + `compose_renderer.py` — assemble calligraphy compositions

---

## 1. Review Server (review_server.py)

### 1.1 Data Model

Each page's data consists of three parts:

| File | Format | Description |
|------|--------|-------------|
| `page_{num}_ocr_results.json` | JSON array | Raw Pipeline detection results |
| `page_{num}_corrected.json` | JSON array | User correction overlay |
| `page_{num}_reviewed.json` | `{}` (empty JSON) | Submit marker — presence means submitted |

Each entry in **corrected.json** links to the OCR results array via `orig_idx`:

```json
[
  {"orig_idx": 5, "corrected_text": "此", "x": 100, "y": 200, "w": 80, "h": 120, "manual_corrected": true},
  {"orig_idx": 99, "deleted": true},
  {"orig_idx": 100, "added": true, "col": 0, "row": 5, "corrected_text": "？"}
]
```

### 1.2 Page Load Flow (`load_data` → `load_clean`)

1. Read `_ocr_results.json`, assign `orig_idx` to each entry (array index).
2. If `_corrected.json` exists, merge by `orig_idx`:
   - `deleted=true` → mark deleted.
   - `added=true` → append new entry.
   - Otherwise → overlay fields onto original OCR result (x, y, w, h, text, confidence, etc.).
3. `load_clean` caches result (keyed by page_num). Any write (save/del/add/submit) calls `drop_cache` to invalidate.

### 1.3 Save Flow

**Text edit:** User modifies text in input field → Enter or Ctrl+Enter triggers `/sv` POST → find or create corrected.json entry → write file → drop cache.

**Drag adjust:** Drag any of the 8 control points → `mouseup` fires `/sv` POST → same as above.

**Auto-save:** On char switch, `saveBg` compares current text input value with saved value; if changed, calls `/sv`.

### 1.4 Submit Flow (`/submit`)

1. Load clean data and full-resolution original image.
2. Sort by reading order: column X descending (RTL), row Y ascending (top to bottom).
3. Assign `seq` numbers after sort (starting at 1).
4. For each character:
   - Crop from original image with 4px padding.
   - Save as `{CROPPED_DIR}/{calligrapher}/{source_text}/page_{num}/{seq:03d}_{char}.png`.
   - **Clear** the page's old cropped directory before saving (`shutil.rmtree` + recreate).
5. Group by character, build `char_entries` list — each group contains all occurrences (seq, char, position, confidence, image path, 3-char context).
6. **Update Obsidian char DB:** For each unique character, write/update `{CHAR_DB_DIR}/{calligrapher}/{source_text}/{char}.md`:
   - Frontmatter: `char`, `calligrapher`, `source`
   - Body table: `![[image.png]]` + confidence + context
7. Write `page_{num}_reviewed.json` (empty JSON as marker).
8. If a skipped marker file exists, delete it.
9. Drop cache; frontend auto-navigates to next page.

**Note:** The old cropped directory is cleared before re-saving. Submitting is "overwrite" not "append" — re-submitting a corrected page replaces old slices.

### 1.5 Page Status

Accessed via `/status` endpoint, frontend auto-polls/refreshes:

| Status | Condition |
|--------|-----------|
| **unprocessed** | `_ocr_results.json` does not exist |
| **ready** | `_ocr_results.json` exists, `_reviewed.json` does not |
| **submitted** | `_reviewed.json` exists, `_corrected.json` mtime ≤ `_reviewed.json` mtime + 1s |
| **pending** | `_reviewed.json` exists, but `_corrected.json` is newer (mtime diff > 1s) |
| **skipped** | `_skipped.json` exists |

Frontend uses different CSS classes: `st1` (unprocessed/red), `st2` (ready/green), `st3` (submitted/yellow), `st4` (pending/orange), `st5` (skipped/gray).

**Pending auto-refresh:** `checkStatus(PAGE)` called after every `/sv`, `/del`, `/add` success — status updates without page reload.

### 1.6 Add/Delete Characters

- **Delete** (`/del`): append `{orig_idx, deleted: true}` entry to corrected.json.
- **Add** (`/add`): append `{orig_idx: max+1, added: true, x, y, w, h, corrected_text: "?"}` entry to corrected.json. Column/row position inferred from the selected char.

### 1.7 Auto-invoke Pipeline

Visiting an unprocessed page triggers frontend `/run_page` → server runs `python pipeline.py {page} --no-correct` via `subprocess` → auto-refresh on completion.

---

## 2. Char Viewer (char_viewer.py)

### 2.1 Index Building (`build_index`)

Scans `output/cropped/{calligrapher}/{source_text}/` directory:

```
page_024/
  001_此.png
  002_书.png
  ...
page_027/
  ...
```

Reads all files matching `(\d+)_(.+?)\.png`, builds a global dictionary:

```python
{
  "此": [{"page": 24, "seq": 1, "filename": "001_此.png", "page_dir": "page_024"}, ...],
  "书": [...],
  ...
}
```

**Auto-refresh:** All API endpoints (search, char, compose/search, etc.) rebuild the index on each call (filesystem scan < 100ms for ~260 pages) — newly submitted chars appear immediately without server restart.

### 2.2 Search Logic (`/api/search`)

- `?q=` parameter performs substring match (`q in char`).
- Empty q returns all chars with occurrence counts.
- Results sorted by Unicode code point.

### 2.3 Image Processing Modes

`/api/image/<path>` supports four processing modes and invert:

| Mode | Operation |
|------|-----------|
| `original` | Raw cropped image |
| `enhanced` | CLAHE + sharpen kernel (`[[0,-1,0],[-1,5,-1],[0,-1,0]]`) |
| `bilateral` | Bilateral filter (d=9, sigmaColor=75, sigmaSpace=75) |
| `binary` | Otsu adaptive binarization |

**Adaptive background sampling:** Compute image brightness histogram, find peak (background color), sample ±30 around it for the average. Auto-adapts to black-on-white or white-on-black copybooks. Background flips with invert.

**Ink-center alignment (`ink_center_crop`):** Compute character centroid (moment), crop 200×200 region centered on it.

### 2.4 Fabric.js Frontend

- 240×240 canvas, 200×200 effective display area.
- Mizige/tianzi grid lines via `drawGrid()` (note: Fabric.js 5.3.0 has no `sendObjectToBack` — image must be added before grid).
- Load debounce: `loadSeq` counter in `fromURL` callback prevents stale callbacks from overwriting newer loads.
- Keyboard shortcuts: ←/→ prev/next char, R reset zoom, I invert.

---

## 3. Compose Layout (compose_renderer.py + char_viewer.py /compose)

### 3.1 Overall Flow

1. User enters text in compose frontend → POST `/api/compose/search` → backend queries variant list per char.
2. User selects variant for each position in sidebar → click "Render" → POST `/api/compose/render`.
3. Backend calls `render_composition(chars, variants, params)` → Pillow engine renders → returns PNG.
4. PDF export: same pipeline → fpdf2 embeds PNG → download.

### 3.2 Layout Engine Design (compose_renderer.py)

**Core function:** `render_composition(chars, variants, params)`

#### Phase 1: Parse Input

`chars` is a string; parsed into items per character:

| Type | Source |
|------|--------|
| `char` | Normal Chinese character |
| `punct` | Chinese/English punctuation (in set) |
| `space` | Space character |
| `nl` | Newline `\n` (triggers column break) |

#### Phase 2: Load Character Images

- For each `char`-type item, find image path via `variants` dict.
- Use `cv2.imdecode` for Unicode paths (avoids Chinese filename issues).
- Otsu binarize → invert so 255 = white background, 0 = black ink.
- **Never scale**: binary images kept at original resolution.
- Track `max_char_w` and `max_char_h` across all loaded images.

#### Phase 3: Cell Size

```
cell_size = max(max_char_w, max_char_h) × 1.15
```

- The 1.15 multiplier ensures the largest character never overflows.
- If no images loaded (all punct/space/fallback), fall back to `params['char_size']` (default 100).

#### Phase 4: Layout Calculation

**Wrapping & auto-wrap:**
- `\n` forces a column break (vertical) or line break (horizontal).
- `params['cols']` controls max rows per column (vertical) or max columns per line (horizontal).
- `has_nl` guard removed — auto-wrap always active.

**First pass (layout simulation):** compute rows per column and total columns.
- Vertical (v_rtl/v_ltr): row count limited by `cols`. New row overflow → new column.
- Horizontal (h_ltr/h_rtl): column count limited by `cols`. Column overflow → new line.
- RTL modes reverse column order during positioning (right to left).

**Canvas dimensions:**
- Left margin = `gap × 2`
- Vertical: `w = left_margin + n_cols × (cell + gap) + gap`, `h = gap + max_rows × (cell + gap) + gap`
- Horizontal: `w = left_margin + cols × (cell + gap) + gap`, `h = gap + n_rows × (cell + gap) + gap`

#### Phase 5: Background Rendering

| Background | Implementation |
|------------|----------------|
| `beige` | Solid (252, 249, 240, 255) |
| `white` | Solid white (255,255,255,255) |
| `black` | Solid black (0,0,0,255) |
| `red` | Solid red (200,40,30,255) |
| `gold_fleck` | Beige base + irregular gold polygons (`_render_gold_fleck_bg`) |
| `grass` | Yellow-brown base + fiber texture (`_render_grass_bg`) |

**Gold fleck (`_render_gold_fleck_bg`):**
- Fixed seed (`np.random.RandomState(42)`) for reproducible renders.
- Density: `w × h / 6000` polygons (min 8).
- 5–10 sides per polygon, radius 5–18px, random angle ±0.3 rad.
- Color: R=200–255, G=165–205, B=20–44, alpha=100–220.
- 35% chance of a brighter inner polygon (0.5× radius).

**Grass paper (`_render_grass_bg`):**
- Density: `w × h / 3000` fibers (min 40).
- 4 angles: 75°, 165°, 30°, 120°.
- Length 50–200px, width 3–6px, alpha 25–60.
- Color: R=100–150, G=60–100, B=30–55.

#### Phase 6: Second Pass (Actual Rendering)

Renders all items in position order:

- **Space** → empty cell.
- **Newline** → advance to next column/line.
- **Normal char** → compute cell position, center-paste RGBA char image in cell.
  - No image found → `_make_fallback_char` (font render at 60% cell size).
- **Punctuation** → `_make_punctuation_overlay`:
  - Overlay size = cell × 45%.
  - Font size = overlay × 70% (shrunk to avoid collision).
  - Position: cell bottom-right, 12% padding.

#### Binary to RGBA (`_binary_to_rgba`)

- Determine ink direction: count dark vs light pixels, the minority is ink.
- Ink pixels set to `text_color`, other pixels fully transparent `(0,0,0,0)`.
- Supports 5 text colors: `black`, `white`, `ink_blue`, `gold`, `red`.

### 3.3 Export

| Format | Method |
|--------|--------|
| PNG | Client download: server returns PNG → frontend caches as blob → `saveAs` |
| PDF | POST `/api/compose/export_pdf` → server renders PNG → fpdf2 creates PDF (page size = image pixel dims, 1pt=1px) → returns PDF file |

### 3.4 Frontend Interaction

**Click-to-locate:** Click any character in preview → compute click coordinates to (col, row) via `X-Cell-Size` and `X-Total-Cols` response headers → map to `textIdx` → find `dataIdx` via newline offset → sidebar auto-scrolls to corresponding variant.

**Zoom:** `ZOOM_BASE=0.40`, slider 0.1–5.0. Actual scale = `previewWidth × 0.40 × sliderValue`. `margin: 0 auto` for horizontal centering.

**Param response:** Number fields use `input` event + 200ms debounce for jank-free live preview.

---

## 4. Obsidian Character Database

### 4.1 Directory Structure

```
{CHAR_DB_DIR}/{calligrapher}/{source_text}/
  ├── 此.md
  ├── 书.md
  ├── 梦.md
  └── ...
```

### 4.2 File Format

```markdown
---
char: 梦
calligrapher: 吴玉生
source: 红楼梦
---

| # | Char | Image | Confidence | Context |
|---|------|-------|------------|---------|
| 1 | 梦 | ![[page_024/001_梦.png]] | 0.99 | 红楼~ |
| 2 | 梦 | ![[page_027/013_梦.png]] | 0.97 | 入~境 |
```

- All occurrences of the same character are accumulated into one file.
- Context = 3 characters before and after (respecting reading order).
- Images use Obsidian embeds (`![[...]]`).
- Dataview plugin can use frontmatter for advanced filtering.
