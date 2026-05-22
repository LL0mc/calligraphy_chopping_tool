"""Debug second-pass expansion effect"""
import sys, os, cv2, numpy as np
sys.path.insert(0, 'src')
from src.char_segmenter import (detect_main_content_bbox, get_ocr_char_boxes,
    classify_columns, split_mixed_columns, filter_calligraphy_columns,
    refine_char_bbox, remove_overlapping_boxes)
from config import PDF_PATH, PAGES_DIR, DPI_SCALE
from src.pdf_renderer import render_pdf_page

OUT = PAGES_DIR
punct = set('（）()[]{}《》""\'\'.,;:!?、。！？；：，．')

for PAGE in [78, 27]:
    print(f'=== Page {PAGE} ===')
    gray = cv2.imread(os.path.join(OUT, f'page_{PAGE:03d}.png'), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        gray = render_pdf_page(PDF_PATH, PAGE-1, OUT, DPI_SCALE)
        gray = cv2.imread(os.path.join(OUT, f'page_{PAGE:03d}.png'), cv2.IMREAD_GRAYSCALE)
    h, w = gray.shape
    cx, cy, cx2, cy2 = detect_main_content_bbox(gray)
    cropped = gray[cy:cy2, cx:cx2]
    all_chars = get_ocr_char_boxes(cropped)
    chars_g, punct_g = [], []
    for c in all_chars:
        is_p = c[4] in punct or len(c[4].strip()) == 0
        entry = (c[0]+cx, c[1]+cx, c[2]+cy, c[3]+cy, c[4], c[5])
        if is_p: punct_g.append(entry)
        else: chars_g.append(entry)
    punct_boxes = [(p[0], p[2], p[1]-p[0], p[3]-p[2]) for p in punct_g]

    cols = classify_columns(chars_g)
    split_cols = split_mixed_columns(cols, 120)
    calli_cols = filter_calligraphy_columns(split_cols, min_chars=2)

    refined = []
    for new_ci, (_, xm, xM, chs) in enumerate(calli_cols):
        sorted_chs = sorted(chs, key=lambda c: c[2])
        claimed = []
        for ri, c in enumerate(sorted_chs):
            x1, x2, y1, y2, text, score = c
            nx, ny, nw, nh = refine_char_bbox(gray, x1, x2, y1, y2,
                                                exclude_boxes=punct_boxes,
                                                claimed_regions=claimed)
            if nw > 0 and nh > 0 and ny+nh <= h and nx+nw <= w:
                refined.append((nx, ny, nw, nh, gray[ny:ny+nh, nx:nx+nw],
                                nw*nh, new_ci, ri, text, score))
                claimed.append((nx, ny, nx + nw, ny + nh))
                if text == '光':
                    print(f'  光 refine: x=[{nx},{nx+nw}] y=[{ny},{ny+nh}] w={nw} h={nh}')
                if PAGE == 27 and text:
                    prev_chars = [r for r in refined if r[6]==new_ci and abs(r[1]-ny) < 200]
                    for r in prev_chars:
                        if r[1] < ny:
                            print(f'  col={new_ci} ri={ri} "{text}" y=[{ny},{ny+nh}] h={nh} OVERLAPS prev ri={r[7]} "{r[8]}" y=[{r[1]},{r[1]+r[3]}] h={r[3]}')
            else:
                if text:
                    print(f'  SKIP: {text} at y=[{y1},{y2}] h={nh}')

    print(f'  after refine: {len(refined)}')
    col_map = {}
    for c in refined:
        col_map.setdefault(c[6], []).append(c)
    for ci, cl in col_map.items():
        print(f'  col {ci}: {len(cl)} chars')

    # Check for overlaps before NMS
    for i, a in enumerate(refined):
        for j, b in enumerate(refined):
            if i >= j: continue
            # Compute IoU
            ax1, ay1, ax2, ay2 = a[0], a[1], a[0]+a[2], a[1]+a[3]
            bx1, by1, bx2, by2 = b[0], b[1], b[0]+b[2], b[1]+b[3]
            ix1 = max(ax1, bx1); iy1 = max(ay1, by1)
            ix2 = min(ax2, bx2); iy2 = min(ay2, by2)
            inter = max(0, ix2-ix1) * max(0, iy2-iy1)
            union = a[2]*a[3] + b[2]*b[3] - inter
            if union > 0 and inter/union > 0.15:
                print(f'  OVERLAP ({inter/union:.2f}): a="{a[8]}" y=[{ay1},{ay2}] h={a[3]}  b="{b[8]}" y=[{by1},{by2}] h={b[3]}')

    refined = remove_overlapping_boxes(refined, iou_threshold=0.3)
    print(f'  after nms: {len(refined)}')

    # List all characters with text
    for c in sorted(refined, key=lambda x: (x[6], x[7])):
        x, y, bw, bh, _, _, ci, ri, text, score = c
        if text:
            print(f'  col={ci} ri={ri} "{text}" x=[{x},{x+bw}] y=[{y},{y+bh}]')
