"""Refinement module: bounding box refinement, IoU computation, and overlap removal."""
import cv2
import numpy as np
from src.types import CharBox


def refine_char_bbox(gray: np.ndarray, x_min: int, x_max: int, y_min: int, y_max: int,
                     binary_threshold: int = 140, padding: int = 5,
                     search_margin_x: int = 40, search_margin_y: int = 100,
                     merge_radius: int = 100,
                     exclude_boxes: list = None,
                     claimed_regions: list = None) -> tuple:
    """以OCR框为中心，用连通域精确裁剪字符，排除标点区域和已被前面字符声明的区域"""
    h, w = gray.shape
    
    search_x1 = max(0, x_min - search_margin_x)
    search_x2 = min(w, x_max + search_margin_x)
    search_y1 = max(0, y_min - search_margin_y)
    search_y2 = min(h, y_max + search_margin_y)
    
    roi = gray[search_y1:search_y2, search_x1:search_x2]
    _, binary = cv2.threshold(roi, binary_threshold, 255, cv2.THRESH_BINARY)
    
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
    
    roi_h, roi_w = binary.shape
    center_x = (x_min - search_x1 + x_max - search_x1) // 2
    center_y = (y_min - search_y1 + y_max - search_y1) // 2
    
    # Collect candidate components, excluding punctuation
    candidates = []
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < 20:
            continue
            
        x = stats[i, cv2.CC_STAT_LEFT]
        y = stats[i, cv2.CC_STAT_TOP]
        bw = stats[i, cv2.CC_STAT_WIDTH]
        bh = stats[i, cv2.CC_STAT_HEIGHT]
        
        cx = x + bw // 2
        cy = y + bh // 2
        
        # Component bounding box in global coordinates
        comp_x1 = search_x1 + x
        comp_x2 = comp_x1 + bw
        comp_y1 = search_y1 + y
        comp_y2 = comp_y1 + bh
        
        # Check if component overlaps with OCR box
        overlap_ocr = (comp_x1 < x_max and comp_x2 > x_min and comp_y1 < y_max and comp_y2 > y_min)
        
        # Skip punctuation components: those whose center falls in a punctuation box AND
        # whose bounding box does NOT overlap with the OCR box
        is_punct = False
        if exclude_boxes and not overlap_ocr:
            gcx = search_x1 + cx
            gcy = search_y1 + cy
            for ex_x1, ex_y1, ex_w, ex_h in exclude_boxes:
                if gcx >= ex_x1 and gcx < ex_x1 + ex_w and gcy >= ex_y1 and gcy < ex_y1 + ex_h:
                    is_punct = True
                    break
        if is_punct:
            continue
        
        # Check distance to center.
        # All components within merge_radius are candidates.
        # claimed_regions prevents stealing from adjacent characters.
        dist = ((cx - center_x) ** 2 + (cy - center_y) ** 2) ** 0.5
        if dist < merge_radius:
            # Skip components already claimed by a previous character in the same column
            if claimed_regions:
                gcx = search_x1 + cx
                gcy = search_y1 + cy
                claimed = False
                for cr_x1, cr_y1, cr_x2, cr_y2 in claimed_regions:
                    if gcx >= cr_x1 and gcx < cr_x2 and gcy >= cr_y1 and gcy < cr_y2:
                        claimed = True
                        break
                if claimed:
                    continue
            candidates.append((x, y, bw, bh, area, cx, cy))
    
    if not candidates:
        return (x_min, y_min, x_max - x_min, y_max - y_min)
    
    # Merge all candidates (already filtered by merge_radius from OCR center)
    merged_x_min = min(c[0] for c in candidates)
    merged_y_min = min(c[1] for c in candidates)
    merged_x_max = max(c[0] + c[2] for c in candidates)
    merged_y_max = max(c[1] + c[3] for c in candidates)
    
    # Final box in global coordinates
    new_x_min = max(0, search_x1 + merged_x_min - padding)
    new_y_min = max(0, search_y1 + merged_y_min - padding)
    new_w = min(w - new_x_min, (merged_x_max - merged_x_min) + padding * 2)
    new_h = min(h - new_y_min, (merged_y_max - merged_y_min) + padding * 2)
    
    # Post-processing: If the refined box is much larger than the OCR box,
    # exclude outer-background components (those touching ROI boundary)
    ocr_w = x_max - x_min
    ocr_h = y_max - y_min
    ocr_area = ocr_w * ocr_h
    new_area = new_w * new_h
    
    if new_area > ocr_area * 2.0 and ocr_area > 1000:
        internal = [c for c in candidates
                    if c[0] > 0 and c[1] > 0
                    and c[0] + c[2] < roi_w
                    and c[1] + c[3] < roi_h]
        if internal:
            nmi_x = min(c[0] for c in internal)
            nmi_y = min(c[1] for c in internal)
            nmx_x = max(c[0] + c[2] for c in internal)
            nmx_y = max(c[1] + c[3] for c in internal)
            new_x_min = max(0, search_x1 + nmi_x - padding)
            new_y_min = max(0, search_y1 + nmi_y - padding)
            new_w = min(w - new_x_min, (nmx_x - nmi_x) + padding * 2)
            new_h = min(h - new_y_min, (nmx_y - nmi_y) + padding * 2)
    
    return (new_x_min, new_y_min, new_w, new_h)


def compute_iou(box1: CharBox, box2: CharBox) -> float:
    """计算两个框的IoU"""
    x2_1, y2_1 = box1.x + box1.w, box1.y + box1.h
    x2_2, y2_2 = box2.x + box2.w, box2.y + box2.h
    inter_x1 = max(box1.x, box2.x)
    inter_y1 = max(box1.y, box2.y)
    inter_x2 = min(x2_1, x2_2)
    inter_y2 = min(y2_1, y2_2)
    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    union_area = box1.area + box2.area - inter_area
    return inter_area / union_area if union_area > 0 else 0


def remove_overlapping_boxes(characters: list[CharBox], iou_threshold: float = 0.3) -> list[CharBox]:
    """移除重叠的字符框，保留面积较大的框"""
    if not characters:
        return []
    sorted_chars = sorted(characters, key=lambda c: c.area, reverse=True)
    keep = []
    for char in sorted_chars:
        is_overlap = False
        for kept in keep:
            iou = compute_iou(char, kept)
            if iou > iou_threshold:
                is_overlap = True
                break
        if not is_overlap:
            keep.append(char)
    keep.sort(key=lambda c: (c.col_idx, c.row_idx))
    return keep
