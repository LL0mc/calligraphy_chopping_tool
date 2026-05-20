import cv2
import numpy as np
import sys
sys.path.insert(0, '.')
from config import PDF_PATH, PAGES_DIR, DPI_SCALE, TEST_PAGE_INDEX
from src.pdf_renderer import render_pdf_page
from src.char_segmenter import get_ocr_char_boxes, detect_main_content_bbox

# Render page
page_image_path = render_pdf_page(PDF_PATH, TEST_PAGE_INDEX, PAGES_DIR, DPI_SCALE)
gray = cv2.imread(page_image_path, cv2.IMREAD_GRAYSCALE)

# Get content bbox
content_x_min, content_y_min, content_x_max, content_y_max = detect_main_content_bbox(gray)
gray_cropped = gray[content_y_min:content_y_max, content_x_min:content_x_max]

# Get OCR boxes
all_chars = get_ocr_char_boxes(gray_cropped)
all_chars = [(c[0]+content_x_min, c[1]+content_x_min, c[2]+content_y_min, c[3]+content_y_min, c[4], c[5], c[6], c[7]) for c in all_chars]

punctuation = set('（）()[]【】{}《》<>""\'\'.,;:!?、。！？；：，．')
col2 = [c for c in all_chars if 1100 <= (c[0]+c[1])/2 <= 1360 and c[4] not in punctuation]
col2.sort(key=lambda c: c[2])

print('Column 2 characters:')
for i, c in enumerate(col2):
    print(f'  {i}: {c[4]} at y={c[2]}-{c[3]}, x={c[0]}-{c[1]}')

# Find gap between 天 and 入
for i in range(len(col2)-1):
    if col2[i][4] == '天' and col2[i+1][4] == '入':
        gap_start = col2[i][3]
        gap_end = col2[i+1][2]
        print(f'\nGap between 天 and 入: y={gap_start}-{gap_end} (gap size: {gap_end - gap_start})')
        print(f'X range: {col2[i][0]}-{col2[i][1]}')
        
        # Extract the gap region
        x1, x2 = col2[i][0] - 20, col2[i][1] + 20
        y1, y2 = gap_start, gap_end
        roi = gray[y1:y2, x1:x2]
        cv2.imwrite('output/wang_gap.png', roi)
        print(f'Saved gap region to output/wang_gap.png ({roi.shape})')
        
        # Check if there's any dark content in the gap
        dark_mask = gray[y1:y2, x1:x2] < 130
        dark_ratio = np.sum(dark_mask) / dark_mask.size
        print(f'Dark pixel ratio in gap: {dark_ratio:.3f}')
        
        # Also check a larger region around the gap
        y1_large = col2[i][3] - 30
        y2_large = col2[i+1][2] + 30
        roi_large = gray[y1_large:y2_large, x1:x2]
        cv2.imwrite('output/wang_gap_large.png', roi_large)
        print(f'Saved larger gap region to output/wang_gap_large.png ({roi_large.shape})')
