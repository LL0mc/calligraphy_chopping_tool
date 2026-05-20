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
        gap_size = gap_end - gap_start
        
        print(f'Gap between 天 and 入: y={gap_start}-{gap_end} (gap size: {gap_size})')
        print(f'X range: {x1}-{x2}')
        
        # Extract the gap region
        roi = gray[gap_start:gap_end, x1:x2]
        
        # Check dark pixel ratio
        dark_mask = roi < 130
        dark_ratio = np.sum(dark_mask) / dark_mask.size
        print(f'Dark pixel ratio in gap: {dark_ratio:.3f}')
        
        # Try connected component analysis on the gap
        _, binary = cv2.threshold(roi, 130, 255, cv2.THRESH_BINARY)
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
        
        print(f'Found {num_labels-1} connected components in gap')
        for j in range(1, num_labels):
            area = stats[j, cv2.CC_STAT_AREA]
            x = stats[j, cv2.CC_STAT_LEFT]
            y = stats[j, cv2.CC_STAT_TOP]
            w = stats[j, cv2.CC_STAT_WIDTH]
            h = stats[j, cv2.CC_STAT_HEIGHT]
            if area > 500:  # Only show significant components
                print(f'  Component {j}: area={area}, pos=({x},{y}), size=({w}x{h})')
        
        # If there's a significant component, it might be the missing character
        if gap_size > 100 and dark_ratio > 0.3:
            print(f'\nLikely missing character detected! Gap size: {gap_size}, dark ratio: {dark_ratio:.3f}')
            
            # Save the gap region for verification
            cv2.imwrite('output/wang_gap_debug.png', roi)
            print('Saved gap region to output/wang_gap_debug.png')
