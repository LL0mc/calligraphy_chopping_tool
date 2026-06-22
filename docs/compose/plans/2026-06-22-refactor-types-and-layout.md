# Refactor: DataClass Types + Multi-Book Config + Module Split

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace magic tuples with typed dataclasses, add multi-book profile config, split monolithic files, and support horizontal/vertical layout — while producing byte-identical JSON output.

**Architecture:** 
- Introduce `CharBox`, `OcrResult`, `Column` dataclasses in `src/types.py`
- Replace all 10-element tuples across char_segmenter → ocr_recognizer pipeline
- Add `CopybookProfile` for multi-book/author/layout support
- Split `char_segmenter.py` (704 lines) into detection / segmentation / refinement modules
- Split `review_server.py` (1487 lines) into routes / data / obsidian modules
- Keep dead code (debug/test functions) — just move them to `src/utils_deprecated.py`

**Tech Stack:** Python 3.11, dataclasses, cv2, numpy, RapidOCR, Flask

---

## File Structure

```
src/
├── __init__.py              (existing, empty)
├── types.py                 (NEW) CharBox, OcrResult, Column dataclasses
├── copybook_config.py       (NEW) CopybookProfile + profile registry
├── detection.py             (NEW) OCR detection + content cropping (from char_segmenter)
├── segmentation.py          (NEW) Column classification + filtering + gap detection (from char_segmenter)
├── refinement.py            (NEW) CC refinement + dedup + noise filter (from char_segmenter)
├── pipeline.py              (NEW) char_segmenter main flow → calls detection/segmentation/refinement
├── ocr_recognizer.py        (MODIFY) use OcrResult, remove draw_ocr_results dead code
├── confidence_handler.py    (KEEP as-is)
├── page_preprocessor.py     (KEEP as-is)
├── pdf_renderer.py          (KEEP as-is)
├── evaluator.py             (KEEP as-is)
├── compose_renderer.py      (KEEP as-is)
├── data.py                  (NEW) data loading functions from review_server
├── obsidian.py              (NEW) Obsidian sync functions from review_server
├── utils_deprecated.py      (NEW) dead code preserved: save_characters, draw_character_boxes, etc.
pipeline.py                  (MODIFY) use new imports from src.pipeline
review_server.py             (MODIFY) import from src/data, src/obsidian, slim to routes only
config.py                    (MODIFY) remove dead constants, add COPYBOOK_PROFILES
```

---

## Phase 1: Golden Baseline + DataClass

### Task 1: Capture golden baseline JSON

**Files:**
- Create: `output/exp/refactor_baseline/` directory

- [ ] **Step 1: Run pipeline on all reviewed pages to capture current JSON**

```bash
# List reviewed pages
ls output/pages/*_reviewed.json | sed 's/.*page_\([0-9]*\)_.*/\1/' | sort
```

- [ ] **Step 2: Copy current production JSON to baseline**

```bash
mkdir -p output/exp/refactor_baseline
# Copy all current _ocr_results.json files as golden baseline
for f in output/pages/page_*_ocr_results.json; do
    cp "$f" "output/exp/refactor_baseline/$(basename $f)"
done
```

- [ ] **Step 3: Verify baseline files exist**

```bash
ls output/exp/refactor_baseline/page_*_ocr_results.json | wc -l
# Expected: ~29 files (one per reviewed page)
```

- [ ] **Step 4: Commit baseline**

```bash
git add output/exp/refactor_baseline/
git commit -m "chore: capture golden baseline JSON before refactoring"
```

### Task 2: Create `src/types.py` with dataclasses

**Files:**
- Create: `src/types.py`

- [ ] **Step 1: Create types.py with three dataclasses**

```python
"""Core data types for the pipeline."""
from dataclasses import dataclass, field
import numpy as np


@dataclass
class CharBox:
    """A detected character box with position, image, and metadata."""
    x: int
    y: int
    w: int
    h: int
    img: np.ndarray = field(default=None, repr=False)
    area: int = 0
    col_idx: int = 0
    row_idx: int = 0
    text: str = ""
    score: float = 0.0

    def to_dict(self) -> dict:
        return {
            'x': self.x, 'y': self.y, 'w': self.w, 'h': self.h,
            'col': self.col_idx + 1, 'row': self.row_idx + 1,
            'text': self.text, 'confidence': self.score,
        }


@dataclass
class OcrResult:
    """OCR recognition result for a single character."""
    x: int
    y: int
    w: int
    h: int
    col_idx: int
    row_idx: int
    original_text: str
    original_score: float
    ocr_text: str = ""
    ocr_score: float = 0.0
    expand_strategy: str = "none"

    def to_dict(self) -> dict:
        return {
            'x': self.x, 'y': self.y, 'w': self.w, 'h': self.h,
            'col': self.col_idx + 1, 'row': self.row_idx + 1,
            'text': self.ocr_text, 'confidence': self.ocr_score,
            'original_text': self.original_text,
            'original_score': self.original_score,
            'expand_strategy': self.expand_strategy,
        }


@dataclass
class Column:
    """A vertical (or horizontal) column of characters."""
    col_idx: int
    x_min: int
    x_max: int
    chars: list[CharBox] = field(default_factory=list)
```

- [ ] **Step 2: Commit**

```bash
git add src/types.py
git commit -m "feat: add CharBox/OcrResult/Column dataclasses in src/types.py"
```

### Task 3: Migrate `char_segmenter.py` to use CharBox

**Files:**
- Modify: `src/char_segmenter.py` (all functions)
- Test: run `python pipeline.py 24 --no-correct` and diff against baseline

- [ ] **Step 1: Import CharBox at top of char_segmenter.py**

Replace the module docstring and add import:
```python
"""单字切割模块 v12：OCR定位 + 连通域精确裁剪"""
import os
import cv2
import numpy as np
from src.types import CharBox
```

- [ ] **Step 2: Migrate `get_ocr_char_boxes` to return list[CharBox]**

Change the return type of `get_ocr_char_boxes`. Currently returns tuples:
```python
all_chars.append((x_min, x_max, y_min, y_max, char_text, char_score, line_idx, char_idx))
```

Change to:
```python
all_chars.append(CharBox(
    x=x_min, y=0, w=x_max - x_min, h=y_max - y_min,
    text=char_text, score=char_score,
    col_idx=line_idx, row_idx=char_idx
))
```

**NOTE:** The current tuple format is `(x_min, x_max, y_min, y_max, ...)` — this is NOT `(x, y, w, h)`. The migration must preserve the same coordinate semantics. Every downstream function that unpacks these tuples must be updated accordingly.

- [ ] **Step 3: Update all functions in char_segmenter.py that consume CharBox**

Functions to update: `classify_columns`, `split_mixed_columns`, `filter_calligraphy_columns`, `detect_missing_chars_in_gaps`, `segment_characters`. Each currently indexes tuples like `c[0]`, `c[1]`, `c[2]`, `c[3]`. Change to `c.x_min`, etc.

**CRITICAL: Maintain the SAME coordinate format.** The current code uses `c[0]=x_min, c[1]=x_max, c[2]=y_min, c[3]=y_max` for intermediate columns. The final CharBox output uses `x, y, w, h`. Keep the intermediate format working, only change the final output.

- [ ] **Step 4: Update `segment_characters` to return list[CharBox]**

```python
all_characters.append(CharBox(
    x=new_x, y=new_y, w=new_w, h=new_h,
    img=gray[new_y:new_y+new_h, new_x:new_x+new_w],
    area=new_w * new_h,
    col_idx=new_col_idx, row_idx=row_idx,
    text=text, score=score,
))
```

- [ ] **Step 5: Update `remove_overlapping_boxes` and `compute_iou` to use CharBox**

```python
def compute_iou(box1: CharBox, box2: CharBox) -> float:
    x2_1, y2_1 = box1.x + box1.w, box1.y + box1.h
    x2_2, y2_2 = box2.x + box2.w, box2.y + box2.h
    inter_x1 = max(box1.x, box2.x)
    inter_y1 = max(box1.y, box2.y)
    inter_x2 = min(x2_1, x2_2)
    inter_y2 = min(y2_1, y2_2)
    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    union_area = box1.area + box2.area - inter_area
    return inter_area / union_area if union_area > 0 else 0
```

- [ ] **Step 6: Move dead code to `src/utils_deprecated.py`**

Move these functions from char_segmenter.py:
- `save_characters`
- `draw_character_boxes`

- [ ] **Step 7: Run pipeline and diff against golden baseline**

```bash
python pipeline.py 24 --no-correct --output-dir output/exp/refactor_test/
# Compare output JSON
python -c "
import json
with open('output/exp/refactor_baseline/page_024_ocr_results.json') as f: old = json.load(f)
with open('output/exp/refactor_test/page_024_ocr_results.json') as f: new = json.load(f)
for i, (o, n) in enumerate(zip(old, new)):
    for k in ['x','y','w','h','col','row','text','confidence']:
        if o.get(k) != n.get(k):
            print(f'DIFF at [{i}] {k}: {o.get(k)} != {n.get(k)}')
print(f'OLD: {len(old)} items, NEW: {len(new)} items')
"
```

Expected: "OLD: N items, NEW: N items" with no DIFF lines.

- [ ] **Step 8: Commit**

```bash
git add src/char_segmenter.py src/utils_deprecated.py
git commit -m "refactor: migrate char_segmenter.py to CharBox dataclass"
```

### Task 4: Migrate `ocr_recognizer.py` to use OcrResult

**Files:**
- Modify: `src/ocr_recognizer.py`
- Modify: `pipeline.py` (import path if needed)

- [ ] **Step 1: Import OcrResult**

```python
from src.types import OcrResult, CharBox
```

- [ ] **Step 2: Change `recognize_characters` to return list[OcrResult]**

Currently returns dicts. Change to:
```python
results.append(OcrResult(
    x=x, y=y, w=w, h=h,
    col_idx=char.col_idx, row_idx=char.row_idx,
    original_text=char.text, original_score=char.score,
    ocr_text=text, ocr_score=score,
    expand_strategy=expand_strategy,
))
```

- [ ] **Step 3: Update `confidence_handler.export_results` to accept OcrResult**

In `export_results`, change `r['col_idx']` to `r.col_idx` etc.

- [ ] **Step 4: Move `draw_ocr_results` to `src/utils_deprecated.py`**

- [ ] **Step 5: Run full regression on page 24**

```bash
python pipeline.py 24 --no-correct --output-dir output/exp/refactor_test/
# Diff against baseline
python -c "
import json
with open('output/exp/refactor_baseline/page_024_ocr_results.json') as f: old = json.load(f)
with open('output/exp/refactor_test/page_024_ocr_results.json') as f: new = json.load(f)
for i, (o, n) in enumerate(zip(old, new)):
    for k in ['x','y','w','h','col','row','text','confidence']:
        if o.get(k) != n.get(k):
            print(f'DIFF [{i}] {k}: {o.get(k)} != {n.get(k)}')
print(f'OLD: {len(old)} NEW: {len(new)}')
"
```

Expected: no DIFF lines.

- [ ] **Step 6: Commit**

```bash
git add src/ocr_recognizer.py src/utils_deprecated.py src/confidence_handler.py
git commit -m "refactor: migrate ocr_recognizer to OcrResult dataclass"
```

---

## Phase 2: Copybook Profiles

### Task 5: Create `src/copybook_config.py`

**Files:**
- Create: `src/copybook_config.py`
- Modify: `config.py` (remove hardcoded CALLIGRAPHER, SOURCE_TEXT, PDF_PATH)

- [ ] **Step 1: Create copybook_config.py**

```python
"""Multi-book profile configuration."""
from dataclasses import dataclass
import os
from config import BASE_DIR, OUTPUT_DIR


@dataclass
class CopybookProfile:
    """Configuration for a single calligraphy copybook."""
    name: str                          # identifier, e.g. "wys_hongloumeng"
    pdf_path: str                      # absolute path to PDF
    calligrapher: str                  # e.g. "吴玉生"
    source_text: str                   # e.g. "红楼梦"
    layout_direction: str = "vertical" # "vertical" | "horizontal"
    pages_dir: str = ""                # defaults to output/pages
    cropped_dir: str = ""              # defaults to output/cropped
    obsidian_vault: str = r"D:\notebooks\Lmc\brew"

    def __post_init__(self):
        if not self.pages_dir:
            self.pages_dir = os.path.join(OUTPUT_DIR, "pages")
        if not self.cropped_dir:
            self.cropped_dir = os.path.join(OUTPUT_DIR, "cropped")


# Registry of known copybooks
COPYBOOK_PROFILES: dict[str, CopybookProfile] = {}


def register_profile(profile: CopybookProfile):
    COPYBOOK_PROFILES[profile.name] = profile


def get_profile(name: str) -> CopybookProfile:
    if name not in COPYBOOK_PROFILES:
        raise ValueError(f"Unknown copybook profile: {name}")
    return COPYBOOK_PROFILES[name]


def list_profiles() -> list[str]:
    return list(COPYBOOK_PROFILES.keys())


# Register default profile (backward compatible)
from config import PDF_PATH, CALLIGRAPHER, SOURCE_TEXT
register_profile(CopybookProfile(
    name="wys_hongloumeng",
    pdf_path=PDF_PATH,
    calligrapher=CALLIGRAPHER,
    source_text=SOURCE_TEXT,
))
```

- [ ] **Step 2: Commit**

```bash
git add src/copybook_config.py
git commit -m "feat: add CopybookProfile for multi-book support"
```

### Task 6: Wire CopybookProfile through pipeline.py

**Files:**
- Modify: `pipeline.py`

- [ ] **Step 1: Add --profile argument to pipeline.py**

```python
parser.add_argument("--profile", type=str, default="wys_hongloumeng",
                    help="Copybook profile name")
```

- [ ] **Step 2: Use profile for PDF_PATH and output paths**

```python
from src.copybook_config import get_profile
profile = get_profile(args.profile)
# Use profile.pdf_path instead of PDF_PATH
# Use profile.pages_dir instead of PAGES_DIR
```

- [ ] **Step 3: Verify backward compatibility**

```bash
python pipeline.py 24 --no-correct
# Should work identically to before (default profile = wys_hongloumeng)
```

- [ ] **Step 4: Commit**

```bash
git add pipeline.py
git commit -m "feat: wire CopybookProfile through pipeline.py"
```

---

## Phase 3: Split char_segmenter.py

### Task 7: Extract `src/detection.py`

**Files:**
- Create: `src/detection.py`
- Modify: `src/char_segmenter.py` (remove extracted functions, add imports)

- [ ] **Step 1: Create detection.py with extracted functions**

Move from char_segmenter.py:
- `detect_main_content_bbox`
- `get_ocr_char_boxes`

```python
"""OCR detection module: content cropping + character box detection."""
import cv2
import numpy as np
from src.types import CharBox


def detect_main_content_bbox(gray, min_density_ratio=0.15, window=100):
    """...""" # exact current implementation


def get_ocr_char_boxes(gray):
    """...""" # exact current implementation, returning list[CharBox]
```

- [ ] **Step 2: Update char_segmenter.py imports**

```python
from src.detection import detect_main_content_bbox, get_ocr_char_boxes
# Remove the function definitions
```

- [ ] **Step 3: Regression test**

```bash
python pipeline.py 24 --no-correct --output-dir output/exp/refactor_test/
# Diff against baseline — must be identical
```

- [ ] **Step 4: Commit**

```bash
git add src/detection.py src/char_segmenter.py
git commit -m "refactor: extract detection.py from char_segmenter.py"
```

### Task 8: Extract `src/segmentation.py`

**Files:**
- Create: `src/segmentation.py`
- Modify: `src/char_segmenter.py`

- [ ] **Step 1: Create segmentation.py**

Move from char_segmenter.py:
- `classify_columns`
- `split_mixed_columns`
- `filter_calligraphy_columns`
- `detect_missing_chars_in_gaps`

```python
"""Column segmentation module: classification, splitting, filtering, gap detection."""
import cv2
import numpy as np
from src.types import CharBox


def classify_columns(all_chars):
    """...""" # exact current implementation


def split_mixed_columns(columns, size_threshold=120):
    """...""" # exact current implementation


def filter_calligraphy_columns(columns, min_chars=2, min_col_width=130, **kwargs):
    """...""" # exact current implementation


def detect_missing_chars_in_gaps(gray, sorted_chars, x_min, x_max, ...):
    """...""" # exact current implementation
```

- [ ] **Step 2: Update char_segmenter.py imports**

```python
from src.segmentation import (
    classify_columns, split_mixed_columns,
    filter_calligraphy_columns, detect_missing_chars_in_gaps
)
```

- [ ] **Step 3: Regression test + commit**

```bash
python pipeline.py 24 --no-correct --output-dir output/exp/refactor_test/
# Diff must be zero
git add src/segmentation.py src/char_segmenter.py
git commit -m "refactor: extract segmentation.py from char_segmenter.py"
```

### Task 9: Extract `src/refinement.py` + rename pipeline.py

**Files:**
- Create: `src/refinement.py`
- Rename: `src/char_segmenter.py` → `src/pipeline.py` (the segment_characters main flow)

- [ ] **Step 1: Create refinement.py**

Move from char_segmenter.py:
- `refine_char_bbox`
- `compute_iou`
- `remove_overlapping_boxes`

```python
"""CC refinement module: bounding box refinement, dedup, noise filtering."""
import cv2
import numpy as np
from src.types import CharBox


def refine_char_bbox(gray, x_min, x_max, y_min, y_max, ...):
    """...""" # exact current implementation


def compute_iou(box1, box2):
    """...""" # exact current implementation


def remove_overlapping_boxes(characters, iou_threshold=0.3):
    """...""" # exact current implementation
```

- [ ] **Step 2: Rename char_segmenter.py → pipeline.py (inside src/)**

The `segment_characters` function (the main flow) stays in `src/pipeline.py`, which now imports from detection, segmentation, and refinement.

```python
"""Pipeline main flow: orchestrates detection → segmentation → refinement."""
from src.types import CharBox
from src.detection import detect_main_content_bbox, get_ocr_char_boxes
from src.segmentation import (
    classify_columns, split_mixed_columns,
    filter_calligraphy_columns, detect_missing_chars_in_gaps
)
from src.refinement import refine_char_bbox, remove_overlapping_boxes
import numpy as np


def segment_characters(gray, config=None):
    """Main flow: OCR detection + CC refinement (non-overlapping)."""
    # ... exact current implementation from char_segmenter.py:segment_characters
```

- [ ] **Step 3: Update all imports across the codebase**

Files that import from `src.char_segmenter`:
- `pipeline.py` (root)
- `review_server.py`
- Any test files

Change all `from src.char_segmenter import ...` to `from src.pipeline import ...` or `from src.detection import ...` etc.

- [ ] **Step 4: Regression test + commit**

```bash
python pipeline.py 24 --no-correct --output-dir output/exp/refactor_test/
# Diff must be zero
git add -A src/
git commit -m "refactor: split char_segmenter into detection/segmentation/refinement/pipeline"
```

### Task 10: Full regression on all pages

- [ ] **Step 1: Run pipeline on ALL reviewed pages**

```bash
# Get all reviewed page numbers
for f in output/pages/page_*_reviewed.json; do
    page=$(basename "$f" | sed 's/page_\([0-9]*\)_.*/\1/')
    python pipeline.py $page --no-correct --output-dir output/exp/refactor_test/
done
```

- [ ] **Step 2: Diff all pages against baseline**

```python
# run_refactor_diff.py
import json, os, glob

baseline_dir = 'output/exp/refactor_baseline'
test_dir = 'output/exp/refactor_test'
diffs = 0
for f in sorted(glob.glob(f'{baseline_dir}/page_*_ocr_results.json')):
    name = os.path.basename(f)
    test_f = os.path.join(test_dir, name)
    if not os.path.exists(test_f):
        print(f'MISSING: {name}')
        continue
    with open(f) as fh: old = json.load(fh)
    with open(test_f) as fh: new = json.load(fh)
    if len(old) != len(new):
        print(f'SIZE DIFF: {name} old={len(old)} new={len(new)}')
        diffs += 1
        continue
    for i, (o, n) in enumerate(zip(old, new)):
        for k in ['x','y','w','h','col','row','text','confidence']:
            if o.get(k) != n.get(k):
                print(f'DIFF: {name}[{i}] {k}: {o.get(k)} != {n.get(k)}')
                diffs += 1
print(f'\nTotal diffs: {diffs}')
```

Expected: "Total diffs: 0"

- [ ] **Step 3: Commit baseline comparison results**

```bash
git add -A output/exp/refactor_test/
git commit -m "chore: regression test results for refactor"
```

---

## Phase 4: Split review_server.py

### Task 11: Extract `src/data.py`

**Files:**
- Create: `src/data.py`
- Modify: `review_server.py`

- [ ] **Step 1: Create data.py**

Extract from review_server.py:
- `load_data(page_num, pages_dir)` — lines ~32-56
- `load_img(page_num, pages_dir)` — lines ~58-65
- `img_to_b64(img)` — lines ~67-69
- `get_clean_data(data)` — lines ~71-79
- `get_last_page()` / `save_last_page()` — lines ~14-26

```python
"""Data loading functions for the review server."""
import os, json, cv2, base64


def load_data(page_num, pages_dir):
    """Load OCR data and overlay corrections."""
    # exact current implementation


def load_img(page_num, pages_dir):
    """Load page image (processed or original)."""
    # exact current implementation


def img_to_b64(img):
    """Convert cv2 image to base64 PNG."""
    # exact current implementation


def get_clean_data(data):
    """Filter deleted items and build index mapping."""
    # exact current implementation
```

- [ ] **Step 2: Update review_server.py imports**

```python
from src.data import load_data, load_img, img_to_b64, get_clean_data
from src.data import get_last_page, save_last_page
```

- [ ] **Step 3: Verify review_server still works**

```bash
python review_server.py
# Open http://127.0.0.1:5000/?p=24
# Verify page loads correctly
```

- [ ] **Step 4: Commit**

```bash
git add src/data.py review_server.py
git commit -m "refactor: extract data loading functions to src/data.py"
```

### Task 12: Extract `src/obsidian.py`

**Files:**
- Create: `src/obsidian.py`
- Modify: `review_server.py`

- [ ] **Step 1: Create obsidian.py**

Extract from review_server.py — the `/submit` endpoint's Obsidian logic:
- DB note creation/update (char_db_update)
- Cropped image saving
- Note file writing with frontmatter

```python
"""Obsidian character database sync."""
import os, json, cv2


def save_cropped_chars(chars, cropped_dir, calligrapher, source_text, page_num):
    """Save cropped character images in reading order."""
    # extracted from review_server submit logic


def update_obsidian_note(char_data, vault_path, calligrapher, source_text):
    """Create or update a character note in Obsidian vault."""
    # extracted from review_server submit logic
```

- [ ] **Step 2: Update review_server.py to use src.obsidian**

- [ ] **Step 3: Verify submit flow works**

- [ ] **Step 4: Commit**

```bash
git add src/obsidian.py review_server.py
git commit -m "refactor: extract Obsidian sync to src/obsidian.py"
```

---

## Phase 5: Horizontal Layout Support

### Task 13: Add layout_direction to CopybookProfile and wire through pipeline

**Files:**
- Modify: `src/copybook_config.py`
- Modify: `src/segmentation.py` (classify_columns, detect_missing_chars_in_gaps)
- Modify: `src/pipeline.py` (segment_characters)

- [ ] **Step 1: Add layout_direction parameter to segment_characters**

```python
def segment_characters(gray, config=None, layout_direction="vertical"):
    """Main flow. layout_direction: 'vertical' or 'horizontal'."""
```

- [ ] **Step 2: Modify classify_columns for horizontal layout**

When `layout_direction="horizontal"`, cluster by Y-center instead of X-center:

```python
def classify_columns(all_chars, layout_direction="vertical"):
    if layout_direction == "horizontal":
        # Cluster by Y-center (rows instead of columns)
        chars_with_center = [(c, (c.y + c.h) / 2) for c in all_chars]
    else:
        # Cluster by X-center (columns)
        chars_with_center = [(c, (c.x + c.w) / 2) for c in all_chars]
```

- [ ] **Step 3: Modify detect_missing_chars_in_gaps for horizontal**

For horizontal layout, search X-gaps instead of Y-gaps.

- [ ] **Step 4: Verify vertical layout unchanged**

```bash
python pipeline.py 24 --no-correct --output-dir output/exp/refactor_test/
# Diff must be zero (default is vertical)
```

- [ ] **Step 5: Commit**

```bash
git add src/copybook_config.py src/segmentation.py src/pipeline.py
git commit -m "feat: add layout_direction support for horizontal/vertical text"
```

---

## Phase 6: Review Server HTML Extract

### Task 14: Extract HTML templates from review_server.py

**Files:**
- Create: `templates/review.html`
- Modify: `review_server.py`

- [ ] **Step 1: Extract the main HTML template**

Move the inline HTML string from review_server.py's `index()` route to `templates/review.html`.

- [ ] **Step 2: Update review_server to use Jinja2 template**

```python
@app.route('/')
def index():
    return render_template('review.html', page=get_last_page())
```

- [ ] **Step 3: Verify review server works**

- [ ] **Step 4: Commit**

```bash
git add templates/review.html review_server.py
git commit -m "refactor: extract inline HTML to templates/review.html"
```

---

## Final Verification

### Task 15: End-to-end regression

- [ ] **Step 1: Run pipeline on all 29 pages**

- [ ] **Step 2: Diff every page against golden baseline**

- [ ] **Step 3: Run evaluator**

```bash
python src/evaluator.py
# Score must be 94.27 (unchanged)
```

- [ ] **Step 4: Test review_server.py**

```bash
python review_server.py
# Open http://127.0.0.1:5000/?p=24
# Verify: page loads, boxes render, paragraph view works, submit works
```

- [ ] **Step 5: Test char_viewer.py**

```bash
python char_viewer.py
# Open http://127.0.0.1:5001/
# Verify: char browser loads, compose works
```

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "refactor: complete dataclass migration + module split + multi-book config"
```
