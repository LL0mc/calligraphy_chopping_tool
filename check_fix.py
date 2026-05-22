"""Trace refine_char_bbox step by step for 喜"""
import os, cv2, numpy as np
from config import PAGES_DIR
from src.char_segmenter import detect_main_content_bbox, get_ocr_char_boxes

gray = cv2.imread(os.path.join(PAGES_DIR, 'page_093.png'), cv2.IMREAD_GRAYSCALE)
h, w = gray.shape
cx, cy, cx2, cy2 = detect_main_content_bbox(gray)

for c in get_ocr_char_boxes(gray[cy:cy2, cx:cx2]):
    if c[4] == '喜':
        x1, x2, y1, y2 = c[0]+cx, c[1]+cx, c[2]+cy, c[3]+cy
        break

print(f'喜: x=[{x1},{x2}] y=[{y1},{y2}]')

search_margin = max(y2-y1, x2-x1)
search_x1 = max(0, x1 - search_margin)
search_x2 = min(w, x2 + search_margin)
search_y1 = max(0, y1 - search_margin)
search_y2 = min(h, y2 + search_margin)

_, bin = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY_INV)
roi = bin[search_y1:search_y2, search_x1:search_x2]
roi_h, roi_w = roi.shape

num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(roi, connectivity=8)

center_x = (x1 + x2) / 2
center_y = (y1 + y2) / 2
merge_radius = 100

candidates = []
for j in range(1, num_labels):
    area = stats[j, cv2.CC_STAT_AREA]
    if area < 10: continue
    
    x = stats[j, cv2.CC_STAT_LEFT]
    y = stats[j, cv2.CC_STAT_TOP]
    bw = stats[j, cv2.CC_STAT_WIDTH]
    bh = stats[j, cv2.CC_STAT_HEIGHT]
    cx_comp = x + bw // 2
    cy_comp = y + bh // 2
    
    comp_x1g = search_x1 + x
    comp_y1g = search_y1 + y
    comp_x2g = comp_x1g + bw
    comp_y2g = comp_y1g + bh
    cx_g = search_x1 + cx_comp
    cy_g = search_y1 + cy_comp
    
    dist = ((cx_g - center_x)**2 + (cy_g - center_y)**2)**0.5
    overlap_ocr = (comp_x1g < x2 and comp_x2g > x1 and comp_y1g < y2 and comp_y2g > y1)
    extend = max(comp_x2g-x2, x1-comp_x1g, comp_y2g-y2, y1-comp_y1g, 0)
    passes = dist < merge_radius or (overlap_ocr and extend <= 50)
    touches_bdy = (x <= 0 or y <= 0 or x+bw >= roi_w or y+bh >= roi_h)
    
    if area > 500:
        print(f'Comp#{j}: area={area} y=[{comp_y1g},{comp_y2g}] h={bh} center=({cx_g},{cy_g}) dist={dist:.0f} overlap={overlap_ocr} extend={extend} passes={passes} bdy={touches_bdy}')
    
    if passes:
        candidates.append((x, y, bw, bh, area))

if candidates:
    merged_x_min = min(c[0] for c in candidates)
    merged_y_min = min(c[1] for c in candidates)
    merged_x_max = max(c[0] + c[2] for c in candidates)
    merged_y_max = max(c[1] + c[3] for c in candidates)
    
    padding = 5
    new_x_min = max(0, search_x1 + merged_x_min - padding)
    new_y_min = max(0, search_y1 + merged_y_min - padding)
    new_w = min(w - new_x_min, (merged_x_max - merged_x_min) + padding * 2)
    new_h = min(h - new_y_min, (merged_y_max - merged_y_min) + padding * 2)
    print(f'After merge: y=[{new_y_min},{new_y_min+new_h}] h={new_h} w={new_w}')
    
    ocr_area = (x2-x1) * (y2-y1)
    new_area = new_w * new_h
    print(f'New area={new_area}, OCR area={ocr_area}, ratio={new_area/ocr_area:.1f}')
    
    if new_area > ocr_area * 2.0 and ocr_area > 1000:
        internal = [c for c in candidates
                    if c[0] > 0 and c[1] > 0 and c[0]+c[2] < roi_w and c[1]+c[3] < roi_h]
        print(f'Internal-only trigger: {len(internal)} internal of {len(candidates)} candidates')
        if internal:
            print(f'  Using internal bounds')
    
    print(f'Final refine: y=[{new_y_min},{new_y_min+new_h}] h={new_h}')
else:
    print('NO candidates passed!')
