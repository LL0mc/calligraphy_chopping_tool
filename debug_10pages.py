"""10页全流程，输出conf_boxes图"""
import os, sys, random, cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw, ImageFont
from config import PDF_PATH, PAGES_DIR, DPI_SCALE
from src.pdf_renderer import render_pdf_page
from src.char_segmenter import (
    detect_main_content_bbox, get_ocr_char_boxes,
    classify_columns, split_mixed_columns, filter_calligraphy_columns,
    refine_char_bbox, remove_overlapping_boxes
)

random.seed(123)
OUT = PAGES_DIR

FONT_PATH = "C:/Windows/Fonts/msyh.ttc"
try:
    font_label = ImageFont.truetype(FONT_PATH, 14)
    font_legend = ImageFont.truetype(FONT_PATH, 16)
    font_title = ImageFont.truetype(FONT_PATH, 22)
except:
    font_label = font_legend = font_title = ImageFont.load_default()

CONF_COLORS = [(0.0,(50,50,255)),(0.3,(0,165,255)),(0.5,(0,255,255)),(0.7,(255,180,0)),(0.9,(0,220,0))]
def get_conf_color(s):
    for thr, color in reversed(CONF_COLORS):
        if s >= thr: return color
    return CONF_COLORS[0][1]

def put_chinese(img, text, pos, color=(0,255,0), size=14):
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    font = font_label if size < 18 else font_legend if size < 22 else font_title
    draw.text(pos, text, fill=(color[2], color[1], color[0]), font=font)
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

import numpy as np

chosen = [24, 27, 30, 91, 210, 78, 93, 151, 200, 215]
print(f"10 pages: {chosen}")

reread_cache = {}
for PAGE in chosen:
    PAGE_IDX = PAGE - 1
    print(f"\n=== Page {PAGE} ===")
    if PAGE_IDX not in reread_cache:
        img_path = os.path.join(OUT, f"page_{PAGE:03d}.png")
        if not os.path.exists(img_path):
            img_path = render_pdf_page(PDF_PATH, PAGE_IDX, OUT, DPI_SCALE)
        gray = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
        if gray is None:
            print(f"  FAIL: {img_path}")
            continue
        reread_cache[PAGE_IDX] = gray
    gray = reread_cache[PAGE_IDX]
    h, w = gray.shape

    cx, cy, cx2, cy2 = detect_main_content_bbox(gray)
    if cx2 - cx < 100:
        print(f"  SKIP: content too small")
        continue
    cropped = gray[cy:cy2, cx:cx2]
    all_chars = get_ocr_char_boxes(cropped)

    punct = set('（）()[]{}《》""\'\'.,;:!?、。！？；：，．')
    chars_g, punct_g = [], []
    for c in all_chars:
        is_p = c[4] in punct or len(c[4].strip()) == 0
        entry = (c[0]+cx, c[1]+cx, c[2]+cy, c[3]+cy, c[4], c[5])
        if is_p: punct_g.append(entry)
        else: chars_g.append(entry)
    punct_boxes = [(p[0], p[2], p[1]-p[0], p[3]-p[2]) for p in punct_g]
    print(f"  OCR: {len(chars_g)} chars, {len(punct_g)} punct")

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

    refined = remove_overlapping_boxes(refined, iou_threshold=0.3)

    col_map = {}
    for c in refined:
        col_map.setdefault(c[6], []).append(c)
    final = []
    for ci, cl in col_map.items():
        areas = [c[2]*c[3] for c in cl]
        if not areas: continue
        med = np.median(areas)
        for c in cl:
            a = c[2]*c[3]
            if a > med*3.0 and med > 1000:
                tgt = int(np.sqrt(med))
                cx_ = c[0]+c[2]//2; cy_ = c[1]+c[3]//2
                nw_ = min(c[2], tgt); nh_ = min(c[3], tgt)
                nx_ = max(0, cx_-nw_//2); ny_ = max(0, cy_-nh_//2)
                final.append((nx_, ny_, nw_, nh_, gray[ny_:ny_+nh_, nx_:nx_+nw_],
                              nw_*nh_, c[6], c[7], c[8], c[9]))
            else:
                final.append(c)
    print(f"  refined: {len(final)} chars")

    vis = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    for c in final:
        x, y, bw, bh, _, _, ci, ri, text, score = c
        color = get_conf_color(score)
        cv2.rectangle(vis, (x, y), (x+bw, y+bh), color, 2)
        label = f"{text} {score:.2f}"
        lx, ly = x+2, (y-4 if y > 14 else y+bh+14)
        vis = put_chinese(vis, label, (lx, ly), color, 14)

    leg_y = 30
    vis = put_chinese(vis, f"P{PAGE} | {len(final)} chars", (20, 5), (0,0,0), 22)
    for label, color in CONF_COLORS:
        cv2.rectangle(vis, (20, leg_y), (60, leg_y+14), color, -1)
        cv2.putText(vis, f">={label:.1f}", (66, leg_y+12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (50,50,50), 1)
        leg_y += 22

    out_path = os.path.join(OUT, f"page_{PAGE:03d}_conf_boxes.png")
    cv2.imwrite(out_path, vis)
    print(f"  -> {out_path}")

print(f"\nDone! {len(chosen)} images in {OUT}")
