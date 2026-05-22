"""Debug script: trace why annotation text (贾宝玉) on page 091 is filtered out"""
import sys, cv2, json
sys.path.insert(0, '.')
import numpy as np
from config import PAGES_DIR, PDF_PATH, DPI_SCALE
from src.pdf_renderer import render_pdf_page
from src.page_preprocessor import preprocess_page
from src.char_segmenter import (
    get_ocr_char_boxes, classify_columns, split_mixed_columns,
    filter_calligraphy_columns, detect_main_content_bbox
)

page_idx = 90  # 0-based, so page 91
page_num = page_idx + 1

print("=" * 80)
print(f"DEBUG ISSUE 4: Page {page_num} (index {page_idx}) - Annotation text trace")
print("=" * 80)

# 1. Load page
page_image_path = render_pdf_page(PDF_PATH, page_idx, PAGES_DIR, DPI_SCALE)
preprocessed_path = f"{PAGES_DIR}/page_{page_num:03d}_processed.png"
gray = preprocess_page(page_image_path, preprocessed_path, remove_lines=False)
original = cv2.imread(page_image_path, cv2.IMREAD_GRAYSCALE)
print(f"\nPage size: {original.shape[::-1]} (w x h)")

# 2. Content bbox + crop
content_x_min, content_y_min, content_x_max, content_y_max = detect_main_content_bbox(original)
print(f"\n[Content BBox]: ({content_x_min},{content_y_min})-({content_x_max},{content_y_max})")
gray_cropped = original[content_y_min:content_y_max, content_x_min:content_x_max]
print(f"[Cropped size]: {gray_cropped.shape[::-1]} (w x h)")

# 3. Raw OCR char boxes
all_chars = get_ocr_char_boxes(gray_cropped)
all_chars = [(
    c[0] + content_x_min, c[1] + content_x_min,
    c[2] + content_y_min, c[3] + content_y_min,
    c[4], c[5], c[6], c[7]
) for c in all_chars]

print(f"\n{'='*80}")
print(f"STEP 0: RAW OCR DETECTED CHARACTERS ({len(all_chars)} total)")
print(f"{'='*80}")
# Group by line_idx for clarity
by_line = {}
for c in all_chars:
    line_idx = c[6]  # line from OCR
    if line_idx not in by_line:
        by_line[line_idx] = []
    by_line[line_idx].append(c)

for line_idx in sorted(by_line.keys()):
    chars = by_line[line_idx]
    print(f"\n  OCR Line {line_idx}:")
    for c in chars:
        x_min, x_max, y_min, y_max, text, score, _, char_idx = c
        w, h = x_max - x_min, y_max - y_min
        center_x = (x_min + x_max) / 2
        center_y = (y_min + y_max) / 2
        repr_text = repr(text)
        marker = " <<< CANDIDATE ANNOTATION" if text in ('贾', '宝', '玉', '（', '）', '(', ')') else ""
        print(f"    ch{char_idx}: {repr_text:10s} score={score:.3f} "
              f"x=({x_min:4d},{x_max:4d}) w={w:3d} "
              f"y=({y_min:4d},{y_max:4d}) h={h:3d} "
              f"center_x={center_x:7.1f}{marker}")

# 4. Punctuation filtering (as done in segment_characters)
print(f"\n{'='*80}")
print(f"STEP 1: PUNCTUATION FILTERING")
print(f"{'='*80}")
punctuation = set('（）()[]【】{}《》<>""\'\'.,;:!?、。！？；：，．')
punctuation_boxes = []
filtered_chars = []
for c in all_chars:
    if c[4] in punctuation or len(c[4].strip()) == 0:
        punctuation_boxes.append((c[0], c[2], c[1] - c[0], c[3] - c[2]))
        print(f"  REMOVED (punctuation): {repr(c[4])} at x=({c[0]},{c[1]}) y=({c[2]},{c[3]})")
    else:
        filtered_chars.append(c)
        print(f"  KEPT: {repr(c[4])} at x=({c[0]},{c[1]}) y=({c[2]},{c[3]})")
print(f"\n  -> After filtering: {len(filtered_chars)} chars kept, {len(punctuation_boxes)} punctuation boxes")

# 5. classify_columns
print(f"\n{'='*80}")
print(f"STEP 2: CLASSIFY COLUMNS")
print(f"{'='*80}")
columns = classify_columns(filtered_chars)
for col_idx, x_min, x_max, chars in columns:
    col_width = x_max - x_min
    print(f"\n  Column {col_idx}: x=[{x_min:4d}, {x_max:4d}] width={col_width:3d}  chars={len(chars)}")
    for c in chars:
        x_min2, x_max2, y_min, y_max, text, score, _, _ = c
        w, h = x_max2 - x_min2, y_max - y_min
        print(f"    {repr(text):8s} x=({x_min2:4d},{x_max2:4d}) w={w:3d} center_x={(x_min2+x_max2)/2:7.1f}")
    # Check for annotation candidates
    for c in chars:
        if c[4] in ('贾', '宝', '玉'):
            print(f"    *** ANNOTATION CHAR '{c[4]}' FOUND IN COL {col_idx} ***")

# 6. split_mixed_columns
print(f"\n{'='*80}")
print(f"STEP 3: SPLIT MIXED COLUMNS (size_threshold=120)")
print(f"{'='*80}")
split_cols = split_mixed_columns(columns, size_threshold=120)
for col_idx, x_min, x_max, chars in split_cols:
    col_width = x_max - x_min
    print(f"\n  Sub-column {col_idx}: x=[{x_min:4d}, {x_max:4d}] width={col_width:3d}  chars={len(chars)}")
    for c in chars:
        x_min2, x_max2, y_min, y_max, text, score, _, _ = c
        w, h = x_max2 - x_min2, y_max - y_min
        print(f"    {repr(text):8s} x=({x_min2:4d},{x_max2:4d}) w={w:3d} h={h:3d} center_x={(x_min2+x_max2)/2:7.1f}")
    if any(c[4] in ('贾', '宝', '玉') for c in chars):
        print(f"    *** ANNOTATION CHARS PRESENT IN THIS SUB-COLUMN ***")

# 7. filter_calligraphy_columns
print(f"\n{'='*80}")
print(f"STEP 4: FILTER CALLIGRAPHY COLUMNS (min_chars=3, min_col_width=130)")
print(f"{'='*80}")
calligraphy_columns = filter_calligraphy_columns(
    split_cols, min_chars=3, min_col_width=130
)
print(f"\nFiltered from {len(split_cols)} columns -> {len(calligraphy_columns)} columns kept")
for col_idx, x_min, x_max, chars in calligraphy_columns:
    col_width = x_max - x_min
    print(f"\n  Kept Column {col_idx}: x=[{x_min:4d}, {x_max:4d}] width={col_width:3d}  chars={len(chars)}")
    for c in chars:
        x_min2, x_max2, y_min, y_max, text, score, _, _ = c
        w, h = x_max2 - x_min2, y_max - y_min
        print(f"    {repr(text):8s} x=({x_min2:4d},{x_max2:4d}) w={w:3d}")

# 8. Show which columns were dropped and why
print(f"\n{'='*80}")
print(f"STEP 5: ANALYSIS OF DROPPED COLUMNS")
print(f"{'='*80}")
split_col_names = {}
for col_idx, x_min, x_max, chars in split_cols:
    col_width = x_max - x_min
    kept = any(
        abs(x_min - c[1]) < 2 and abs(x_max - c[2]) < 2 and len(chars) == len(c[3])
        for c in calligraphy_columns
    )
    # simpler check
    kept2 = False
    for _, k_xmin, k_xmax, k_chars in calligraphy_columns:
        if k_xmin == x_min and k_xmax == x_max and len(k_chars) == len(chars):
            kept2 = True
            break
    
    reason = ""
    if not kept2:
        reasons = []
        if col_width < 130:
            reasons.append(f"col_width={col_width} < 130")
        if len(chars) < 3:
            reasons.append(f"char_count={len(chars)} < 3")
        reason = " -> DROPPED: " + "; ".join(reasons)
    
    has_annotation = any(c[4] in ('贾', '宝', '玉') for c in chars)
    tag = " [HAS ANNOTATION TEXT]" if has_annotation else ""
    print(f"  Sub-col {col_idx}: x=[{x_min:4d},{x_max:4d}] w={col_width:3d} chars={len(chars)}{tag}{reason}")

# 9. Exhaustive search: find ALL characters in the rightmost ~200px
print(f"\n{'='*80}")
print(f"STEP 6: EXHAUSTIVE SEARCH - Characters in rightmost region of page")
print(f"{'='*80}")
right_threshold = original.shape[1] - 200  # last 200px
print(f"Searching for chars with x_max > {right_threshold}")
print(f"\nAll raw OCR chars (including punctuation) with x_max > {right_threshold}:")
right_chars = [c for c in all_chars if c[1] > right_threshold]
right_chars_sorted = sorted(right_chars, key=lambda c: (c[2], c[0]))
for c in right_chars_sorted:
    x_min, x_max, y_min, y_max, text, score, line_idx, char_idx = c
    w, h = x_max - x_min, y_max - y_min
    print(f"  {repr(text):8s} score={score:.3f} x=({x_min:4d},{x_max:4d}) w={w:3d} "
          f"y=({y_min:4d},{y_max:4d}) h={h:3d} center_x={(x_min+x_max)/2:7.1f}")

# 10. Trace what the OCR_spit_mixed_columns_book does
print(f"\n{'='*80}")
print(f"STEP 7: DETAILED TRACE - Annotation chars through pipeline")
print(f"{'='*80}")
for target in ('贾', '宝', '玉', '（', '）', '(', ')'):
    found = [(i, c) for i, c in enumerate(all_chars) if c[4] == target]
    if found:
        for idx, c in found:
            x_min, x_max, y_min, y_max, text, score, line_idx, char_idx = c
            w, h = x_max - x_min, y_max - y_min
            print(f"\n  '{target}': raw OCR ch{char_idx} line{line_idx} "
                  f"x=({x_min},{x_max}) w={w} y=({y_min},{y_max}) h={h}")
            
            # Step 1: punctuation filter
            if target in punctuation:
                print(f"    -> Step1(punctuation): REMOVED (classified as punctuation)")
            else:
                print(f"    -> Step1(punctuation): KEPT")
                
                # Step 2: classify_columns - find which col it went to
                for col_idx, _, _, col_chars in columns:
                    if any(x_min == cc[0] and x_max == cc[1] for cc in col_chars if cc[4] == target):
                        col_width = max(cc[1] for cc in col_chars) - min(cc[0] for cc in col_chars)
                        print(f"    -> Step2(classify): Column {col_idx} (width={col_width})")
                        break
                
                # Step 3: split_mixed_columns
                for s_idx, _, _, s_chars in split_cols:
                    if any(x_min == cc[0] and x_max == cc[1] for cc in s_chars if cc[4] == target):
                        s_width = max(cc[1] for cc in s_chars) - min(cc[0] for cc in s_chars)
                        print(f"    -> Step3(split): Sub-col {s_idx} (width={s_width}, chars={len(s_chars)})")
                        
                        # Check all chars in this sub-column
                        print(f"       All chars in sub-col {s_idx}:")
                        for sc in s_chars:
                            sw = sc[1] - sc[0]
                            print(f"         {repr(sc[4]):8s} w={sw:3d} h={sc[3]-sc[2]:3d}")
                        break
                
                # Step 4: filter_calligraphy_columns
                found_in_final = False
                for f_idx, _, _, f_chars in calligraphy_columns:
                    if any(x_min == cc[0] and x_max == cc[1] for cc in f_chars if cc[4] == target):
                        found_in_final = True
                        break
                if found_in_final:
                    print(f"    -> Step4(filter): KEPT in final output")
                else:
                    # Find which sub-col it was in and why it was dropped
                    for s_idx, s_xmin, s_xmax, s_chars in split_cols:
                        if any(x_min == cc[0] and x_max == cc[1] for cc in s_chars if cc[4] == target):
                            col_w = s_xmax - s_xmin
                            n_chars = len(s_chars)
                            reasons = []
                            if col_w < 130:
                                reasons.append(f"col_width={col_w} < 130")
                            if n_chars < 3:
                                reasons.append(f"n_chars={n_chars} < 3")
                            print(f"    -> Step4(filter): DROPPED ({'; '.join(reasons)})")
                            break

    else:
        if target in punctuation:
            print(f"\n  '{target}': not found in raw OCR output (annotations may use different parenthesis style)")

# 11. Summary of OCR results JSON if it exists
json_path = f"{PAGES_DIR}/page_{page_num:03d}_ocr_results.json"
try:
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"\n{'='*80}")
    print(f"STEP 8: EXISTING OCR RESULTS JSON - checking for annotation text")
    print(f"{'='*80}")
    for item in data:
        if item['text'] in ('贾', '宝', '玉'):
            print(f"  FOUND: col={item['col']} row={item['row']} "
                  f"text={repr(item['text'])} conf={item['confidence']:.3f} "
                  f"x={item['x']} y={item['y']} w={item['w']} h={item['h']}")
    if not any(item['text'] in ('贾', '宝', '玉') for item in data):
        print("  Annotation text (贾/宝/玉) is NOT present in existing OCR results.")
        # Check if they were ever detected at all
        all_texts = [item['text'] for item in data]
        print(f"  All texts in existing results: {all_texts}")
except FileNotFoundError:
    print(f"\n  No existing OCR results JSON at {json_path}")

print(f"\n{'='*80}")
print("DEBUG COMPLETE")
print(f"{'='*80}")
