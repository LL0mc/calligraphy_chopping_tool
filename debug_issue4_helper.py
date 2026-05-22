"""Helper to read OCR results JSON for page 091"""
import sys, json, os
sys.path.insert(0, '.')
from config import PAGES_DIR

json_path = os.path.join(PAGES_DIR, 'page_091_ocr_results.json')
if os.path.exists(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print('All entries in existing OCR results:')
    for item in data:
        print(f'  col={item["col"]} row={item["row"]:2d} text={repr(item["text"])} conf={item["confidence"]:.3f} w={item["w"]:3d} h={item["h"]:3d}')
else:
    print(f'File not found: {json_path}')

# Also dump the raw OCR character info from image
sys.path.insert(0, '.')
from src.pdf_renderer import render_pdf_page
from src.page_preprocessor import preprocess_page
from src.char_segmenter import get_ocr_char_boxes, detect_main_content_bbox
import cv2
from config import PDF_PATH, PAGES_DIR, DPI_SCALE

page_idx = 90
page_num = page_idx + 1
page_image_path = os.path.join(PAGES_DIR, f'page_{page_num:03d}.png')
original = cv2.imread(page_image_path, cv2.IMREAD_GRAYSCALE)
content_x_min, content_y_min, content_x_max, content_y_max = detect_main_content_bbox(original)
gray_cropped = original[content_y_min:content_y_max, content_x_min:content_x_max]
all_chars = get_ocr_char_boxes(gray_cropped)
all_chars = [(
    c[0] + content_x_min, c[1] + content_x_min,
    c[2] + content_y_min, c[3] + content_y_min,
    c[4], c[5], c[6], c[7]
) for c in all_chars]

print(f'\n--- OCR Lines with char texts (UTF-8) ---')
for line_idx in sorted(set(c[6] for c in all_chars)):
    line_chars = [c for c in all_chars if c[6] == line_idx]
    texts = [f'  ch{c[7]}: {repr(c[4])} w={c[1]-c[0]} h={c[3]-c[2]} x=({c[0]},{c[1]})' for c in sorted(line_chars, key=lambda x: x[7])]
    print(f'Line {line_idx}:')
    for t in texts:
        print(t)
