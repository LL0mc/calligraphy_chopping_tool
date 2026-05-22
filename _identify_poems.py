"""Identify poems on processed pages"""
import sys, json, os, logging
logging.disable(logging.CRITICAL)
os.environ['RAPIDOCR_LOG_LEVEL'] = 'CRITICAL'

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

from src.char_segmenter import get_ocr_char_boxes, detect_main_content_bbox, classify_columns, split_mixed_columns, filter_calligraphy_columns
from src.pdf_renderer import render_pdf_page
from config import PDF_PATH, PAGES_DIR, DPI_SCALE
import cv2

pages = [23, 26, 29, 48, 52, 90, 183, 186, 209]
for pg in pages:
    pn = pg + 1
    img_path = os.path.join(PAGES_DIR, f'page_{pn:03d}.png')
    if not os.path.exists(img_path):
        render_pdf_page(PDF_PATH, pg, PAGES_DIR, DPI_SCALE)
    gray = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    cx, cy, cx2, cy2 = detect_main_content_bbox(gray)
    cropped = gray[cy:cy2, cx:cx2]
    chars = get_ocr_char_boxes(cropped)
    punct = set('（）()[]【】{}《》"".,;:!?、。！？；：，．')
    chars2 = [(c[0]+cx,c[1]+cx,c[2]+cy,c[3]+cy,c[4],c[5],c[6],c[7]) for c in chars if c[4] not in punct and len(c[4].strip())>0]
    cols = classify_columns(chars2)
    sp = split_mixed_columns(cols, 120)
    cf = filter_calligraphy_columns(sp, min_chars=2)
    print(f'=== Page {pn} ===')
    for ci, (_, xm, xM, chs) in enumerate(cf):
        txt = ''.join(c[4] for c in chs)
        print(f'  Col {ci+1}: {txt}')
