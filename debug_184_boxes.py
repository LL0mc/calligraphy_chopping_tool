import cv2
import numpy as np
import os
import sys
sys.path.append('src')

from char_segmenter import (
    detect_main_content_bbox,
    get_ocr_char_boxes,
    refine_char_bbox,
    classify_columns,
    split_mixed_columns,
    filter_calligraphy_columns,
    detect_missing_chars_in_gaps,
    remove_overlapping_boxes,
    compute_iou,
    draw_character_boxes
)

def draw_boxes_on_image(img, boxes, color=(0, 255, 0), thickness=2):
    """Draw boxes on image. boxes is list of (x, y, w, h)"""
    vis = img.copy()
    if len(vis.shape) == 2:
        vis = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR)
    
    for i, box in enumerate(boxes):
        x, y, w, h = box
        cv2.rectangle(vis, (x, y), (x + w, y + h), color, thickness)
        # Label with index
        cv2.putText(vis, str(i), (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    return vis

def main():
    page = 184
    img_path = f'output/pages/page_{page:03d}.png'
    gray = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    h, w = gray.shape
    
    # Config
    config = {
        'min_char_width': 100,
        'min_char_height': 100,
        'min_annotation_width': 40,
        'min_annotation_height': 40,
        'binary_threshold': 140,
        'bbox_padding': 5,
        'gap_threshold': 80,
        'missing_char_min_area': 300,
        'iou_threshold': 0.3
    }

    # 1. Content Crop
    content_x_min, content_y_min, content_x_max, content_y_max = detect_main_content_bbox(gray)
    gray_cropped = gray[content_y_min:content_y_max, content_x_min:content_x_max]
    
    # 2. First OCR
    all_chars = get_ocr_char_boxes(gray_cropped)
    # Adjust coordinates to global
    all_chars = [(
        c[0] + content_x_min, c[1] + content_x_min,
        c[2] + content_y_min, c[3] + content_y_min,
        c[4], c[5], c[6], c[7]
    ) for c in all_chars]
    
    # Filter punctuation
    punctuation = set('（）()[]【】{}《》<>""\'\'.,;:!?、。！？；：，．')
    punctuation_boxes = []
    filtered_chars = []
    for c in all_chars:
        if c[4] in punctuation or len(c[4].strip()) == 0:
            punctuation_boxes.append((c[0], c[2], c[1] - c[0], c[3] - c[2]))
        else:
            filtered_chars.append(c)
    all_chars = filtered_chars
    
    print(f"[Stage 1] Detected {len(all_chars)} chars from OCR")
    
    # Save Stage 1 Image - Clean visualization with line colors and text labels
    line_colors = [
        (0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0),
        (255, 0, 255), (0, 255, 255), (128, 128, 255), (128, 255, 128),
        (255, 128, 128), (200, 200, 200)
    ]
    
    vis_stage1 = gray.copy()
    if len(vis_stage1.shape) == 2:
        vis_stage1 = cv2.cvtColor(vis_stage1, cv2.COLOR_GRAY2BGR)
    
    for c in all_chars:
        x_min, x_max, y_min, y_max, text, score, line_idx, char_idx = c
        color = line_colors[line_idx % len(line_colors)]
        
        # Draw box
        cv2.rectangle(vis_stage1, (x_min, y_min), (x_max, y_max), color, 2)
        
        # Label with character text
        cx = (x_min + x_max) // 2
        cy = (y_min + y_max) // 2
        cv2.putText(vis_stage1, text, (cx - 8, cy + 6), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    
    cv2.imwrite(f'output/pages/page_{page:03d}_stage1_raw_ocr.png', vis_stage1)
    print(f"Saved Stage 1: page_{page:03d}_stage1_raw_ocr.png")

    # 3. Column Classification & Filtering
    columns = classify_columns(all_chars)
    split_cols = split_mixed_columns(columns, size_threshold=config.get("size_threshold", 120))
    calligraphy_columns = filter_calligraphy_columns(
        split_cols,
        min_chars=config.get("min_chars_per_col", 3),
        min_char_width=config.get("min_char_width", 150),
        min_char_height=config.get("min_char_height", 150)
    )
    
    # 4. Refine Boxes (Connected Components)
    all_characters = []
    for new_col_idx, (old_col_idx, x_min, x_max, chars) in enumerate(calligraphy_columns):
        sorted_chars = sorted(chars, key=lambda c: c[2])
        
        # Detect missing
        missing_chars = detect_missing_chars_in_gaps(
            gray, sorted_chars, x_min, x_max,
            gap_threshold=config.get("gap_threshold", 100),
            binary_threshold=config.get("binary_threshold", 140),
            min_area=config.get("missing_char_min_area", 500)
        )
        if missing_chars:
            sorted_chars = sorted(sorted_chars + missing_chars, key=lambda c: c[2])

        for row_idx, (cx_min, cx_max, cy_min, cy_max, text, score, line_idx, char_idx) in enumerate(sorted_chars):
            new_x, new_y, new_w, new_h = refine_char_bbox(
                gray, cx_min, cx_max, cy_min, cy_max,
                binary_threshold=config.get("binary_threshold", 140),
                padding=config.get("bbox_padding", 5),
                exclude_boxes=punctuation_boxes
            )
            
            area = new_w * new_h
            char_img = gray[new_y:new_y+new_h, new_x:new_x+new_w]

            all_characters.append((
                new_x, new_y, new_w, new_h, char_img, area,
                new_col_idx, row_idx, text, score
            ))

    print(f"[Stage 2] Refined {len(all_characters)} characters")
    
    # Save Stage 2 Image (Before Dedup and Shrinking)
    boxes_stage2 = [(c[0], c[1], c[2], c[3]) for c in all_characters]
    img_stage2 = draw_boxes_on_image(gray, boxes_stage2, color=(0, 255, 0)) # Green
    cv2.imwrite(f'output/pages/page_{page:03d}_stage2_refined.png', img_stage2)
    print(f"Saved Stage 2: page_{page:03d}_stage2_refined.png")

    # 5. Remove Overlapping
    all_characters = remove_overlapping_boxes(all_characters, iou_threshold=config.get("iou_threshold", 0.3))
    print(f"[Stage 3] After Dedup: {len(all_characters)} characters")

    # Save Stage 3 Image (After Dedup, Before Shrinking)
    boxes_stage3 = [(c[0], c[1], c[2], c[3]) for c in all_characters]
    img_stage3 = draw_boxes_on_image(gray, boxes_stage3, color=(0, 0, 255)) # Blue
    cv2.imwrite(f'output/pages/page_{page:03d}_stage3_deduped.png', img_stage3)
    print(f"Saved Stage 3: page_{page:03d}_stage3_deduped.png")

    # 6. Post-processing (Shrinking)
    col_chars = {}
    for char in all_characters:
        col_idx = char[6]
        if col_idx not in col_chars:
            col_chars[col_idx] = []
        col_chars[col_idx].append(char)
    
    for col_idx, chars in col_chars.items():
        areas = [c[2] * c[3] for c in chars]
        if not areas:
            continue
        median_area = np.median(areas)
        
        for i, char in enumerate(chars):
            area = char[2] * char[3]
            if area > median_area * 3.0 and median_area > 1000:
                target_size = int(np.sqrt(median_area))
                cx = char[0] + char[2] // 2
                cy = char[1] + char[3] // 2
                
                new_w = min(char[2], target_size)
                new_h = min(char[3], target_size)
                
                new_x = max(0, cx - new_w // 2)
                new_y = max(0, cy - new_h // 2)
                
                chars[i] = (
                    new_x, new_y, new_w, new_h,
                    gray[new_y:new_y+new_h, new_x:new_x+new_w],
                    new_w * new_h,
                    char[6], char[7], char[8], char[9]
                )
    
    all_characters = []
    for col_idx in sorted(col_chars.keys()):
        all_characters.extend(col_chars[col_idx])
        
    print(f"[Stage 4] Final: {len(all_characters)} characters")

    # Save Stage 4 Image (Final)
    boxes_stage4 = [(c[0], c[1], c[2], c[3]) for c in all_characters]
    img_stage4 = draw_boxes_on_image(gray, boxes_stage4, color=(255, 255, 0)) # Yellow
    cv2.imwrite(f'output/pages/page_{page:03d}_stage4_final.png', img_stage4)
    print(f"Saved Stage 4: page_{page:03d}_stage4_final.png")

if __name__ == '__main__':
    main()
