import cv2
import numpy as np
import sys
sys.path.insert(0, '.')
from config import PDF_PATH, PAGES_DIR, DPI_SCALE, TEST_PAGE_INDEX
from src.pdf_renderer import render_pdf_page
from src.char_segmenter import get_ocr_char_boxes, detect_main_content_bbox
from cnocr import CnOcr

# Render page
page_image_path = render_pdf_page(PDF_PATH, TEST_PAGE_INDEX, PAGES_DIR, DPI_SCALE)
gray = cv2.imread(page_image_path, cv2.IMREAD_GRAYSCALE)

# Get content bbox
content_x_min, content_y_min, content_x_max, content_y_max = detect_main_content_bbox(gray)

# Get OCR boxes with RapidOCR
gray_cropped = gray[content_y_min:content_y_max, content_x_min:content_x_max]
all_chars = get_ocr_char_boxes(gray_cropped)
all_chars = [(c[0]+content_x_min, c[1]+content_x_min, c[2]+content_y_min, c[3]+content_y_min, c[4], c[5], c[6], c[7]) for c in all_chars]

punctuation = set('（）()[]【】{}《》<>""\'\'.,;:!?、。！？；：，．')
col2 = [c for c in all_chars if 1100 <= (c[0]+c[1])/2 <= 1360 and c[4] not in punctuation]
col2.sort(key=lambda c: c[2])

# Find gap between 天 and 入
for i in range(len(col2)-1):
    if col2[i][4] == '天' and col2[i+1][4] == '入':
        gap_start = col2[i][3]
        gap_end = col2[i+1][2]
        x1, x2 = col2[i][0] - 20, col2[i][1] + 20
        
        # Extract the gap region
        roi = gray[gap_start:gap_end, x1:x2]
        
        # Try cnocr on this region
        print(f'Trying cnocr on gap region ({roi.shape})...')
        ocr = CnOcr()
        result = ocr.ocr(roi)
        print(f'cnocr result: {result}')
        
        # Also try on a slightly larger region
        y1_large = gap_start - 20
        y2_large = gap_end + 20
        roi_large = gray[max(0, y1_large):min(gray.shape[0], y2_large), x1:x2]
        result_large = ocr.ocr(roi_large)
        print(f'cnocr result (larger region): {result_large}')
