"""随机5页全流程：OCR→精修→按置信度着色标注，评估框质量"""
import os, sys, random, cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw, ImageFont
from config import PDF_PATH, PAGES_DIR, DPI_SCALE
from src.pdf_renderer import render_pdf_page
from src.char_segmenter import (
    detect_main_content_bbox, get_ocr_char_boxes,
    classify_columns, split_mixed_columns, filter_calligraphy_columns,
    refine_char_bbox, remove_overlapping_boxes
)

random.seed(42)
OUT = PAGES_DIR

FONT_PATH = "C:/Windows/Fonts/msyh.ttc"
try:
    font_label = ImageFont.truetype(FONT_PATH, 14)
    font_legend = ImageFont.truetype(FONT_PATH, 16)
    font_title = ImageFont.truetype(FONT_PATH, 22)
except:
    font_label = ImageFont.load_default()
    font_legend = ImageFont.load_default()
    font_title = ImageFont.load_default()

CONF_COLORS = [
    (0.0,   (50, 50, 255)),   # 红: <0.3
    (0.3,   (0, 165, 255)),   # 橙: 0.3-0.5
    (0.5,   (0, 255, 255)),   # 黄: 0.5-0.7
    (0.7,   (255, 180, 0)),   # 蓝绿: 0.7-0.9
    (0.9,   (0, 220, 0)),     # 绿: >=0.9
]
def get_conf_color(score):
    for thr, color in reversed(CONF_COLORS):
        if score >= thr: return color
    return CONF_COLORS[0][1]

CONF_LABELS = [
    ("<0.3 (极低)", (50,50,255)),
    ("0.3-0.5 (低)", (0,165,255)),
    ("0.5-0.7 (中)", (0,255,255)),
    ("0.7-0.9 (较高)", (255,180,0)),
    (">=0.9 (高)", (0,220,0)),
]

def put_chinese(img, text, pos, color=(0,255,0), size=14):
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    font = font_label
    if size >= 18: font = font_legend
    if size >= 22: font = font_title
    draw.text(pos, text, fill=(color[2], color[1], color[0]), font=font)
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

available = [24, 27, 30, 49, 53, 91, 184, 187, 210]
chosen = sorted(random.sample(available, 5))
print(f"选中页码: {chosen}")

reread_cache = {}  # page_idx -> gray

for PAGE in chosen:
    PAGE_IDX = PAGE - 1
    print(f"\n{'='*50}")
    print(f"第 {PAGE} 页")

    # 1. 获取页面
    if PAGE_IDX not in reread_cache:
        img_path = os.path.join(OUT, f"page_{PAGE:03d}.png")
        if not os.path.exists(img_path):
            img_path = render_pdf_page(PDF_PATH, PAGE_IDX, OUT, DPI_SCALE)
        gray = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
        if gray is None:
            print(f"  !! 加载失败: {img_path}")
            continue
        reread_cache[PAGE_IDX] = gray
    gray = reread_cache[PAGE_IDX]
    h, w = gray.shape

    # 2. 内容裁剪 + OCR
    cx_min, cy_min, cx_max, cy_max = detect_main_content_bbox(gray)
    cropped = gray[cy_min:cy_max, cx_min:cx_max]
    all_chars_raw = get_ocr_char_boxes(cropped)

    punctuation = set('（）()[]【】{}《》<>""\'\'.,;:!?、。！？；：，．')
    chars_global = []
    punct_global = []
    for c in all_chars_raw:
        is_p = c[4] in punctuation or len(c[4].strip()) == 0
        entry = (c[0]+cx_min, c[1]+cx_min, c[2]+cy_min, c[3]+cy_min,
                 c[4], c[5], c[6], c[7])
        if is_p: punct_global.append(entry)
        else:    chars_global.append(entry)
    punct_boxes = [(p[0], p[2], p[1]-p[0], p[3]-p[2]) for p in punct_global]
    print(f"  OCR单字: {len(chars_global)}  标点: {len(punct_global)}")

    # 3. 分列过滤
    columns = classify_columns(chars_global)
    split_cols = split_mixed_columns(columns, size_threshold=120)
    calli_cols = filter_calligraphy_columns(split_cols, min_chars=2, min_col_width=130)

    # 4. 精修
    refined = []
    for new_ci, (_, xm, xM, chs) in enumerate(calli_cols):
        sorted_chs = sorted(chs, key=lambda c: c[2])
        claimed_boxes = []
        for ri, c in enumerate(sorted_chs):
            x1, x2, y1, y2, text, score, li, ci = c
            nx, ny, nw, nh = refine_char_bbox(gray, x1, x2, y1, y2,
                                               exclude_boxes=punct_boxes,
                                               claimed_regions=claimed_boxes)
            if nw > 0 and nh > 0 and ny+nh <= h and nx+nw <= w:
                refined.append((nx, ny, nw, nh, gray[ny:ny+nh, nx:nx+nw],
                                nw*nh, new_ci, ri, text, score))
                claimed_boxes.append((nx, ny, nx + nw, ny + nh))

    # 5. 去重
    refined = remove_overlapping_boxes(refined, iou_threshold=0.3)

    # 6. 过大框收缩
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
                final.append((nx_, ny_, nw_, nh_,
                             gray[ny_:ny_+nh_, nx_:nx_+nw_],
                             nw_*nh_, c[6], c[7], c[8], c[9]))
            else:
                final.append(c)
    print(f"  精修后: {len(final)} 字符")

    # 7. 着色绘制
    vis = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    for c in final:
        x, y, bw, bh, _, _, ci, ri, text, score = c
        color = get_conf_color(score)
        cv2.rectangle(vis, (x, y), (x+bw, y+bh), color, 2)
        label = f"{text} {score:.2f}"
        lx = x+2; ly = y-4 if y > 14 else y+bh+14
        vis = put_chinese(vis, label, (lx, ly), color, 14)

    # 8. 图例
    leg_y = 30; leg_x = 20
    vis = put_chinese(vis, f"第{PAGE}页 | 共{len(final)}字",
                      (leg_x, 5), (0,0,0), 22)
    for label, color in CONF_LABELS:
        cv2.rectangle(vis, (leg_x, leg_y), (leg_x+40, leg_y+14), color, -1)
        cv2.putText(vis, label, (leg_x+46, leg_y+12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (50,50,50), 1)
        leg_y += 22

    # 9. 统计输出
    stats = {}
    for thr, _ in CONF_COLORS:
        n = sum(1 for c in final if c[9] >= thr)
        stats[f">={thr:.1f}"] = n
    print(f"  置信度分布: ", end="")
    for k, v in stats.items():
        print(f"{k}:{v} ", end="")
    print()

    out_path = os.path.join(OUT, f"page_{PAGE:03d}_conf_boxes.png")
    cv2.imwrite(out_path, vis)
    print(f"  输出: {out_path}")

print(f"\n完成! 结果在 {OUT} 目录下 *_conf_boxes.png")
