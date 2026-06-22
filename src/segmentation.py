"""Segmentation module: column classification, splitting, filtering, and missing char detection."""
import cv2
import numpy as np


def classify_columns(all_chars: list) -> list:
    """按x中心坐标分列"""
    if not all_chars:
        return []

    chars_with_center = [(c, (c[0] + c[1]) / 2) for c in all_chars]
    chars_with_center.sort(key=lambda x: x[1])

    columns = []
    current_col_chars = [chars_with_center[0][0]]
    current_col_center_sum = chars_with_center[0][1]
    current_col_count = 1

    for char, center in chars_with_center[1:]:
        avg_center = current_col_center_sum / current_col_count
        if abs(center - avg_center) > 100:
            x_min = min(c[0] for c in current_col_chars)
            x_max = max(c[1] for c in current_col_chars)
            columns.append((len(columns), x_min, x_max, current_col_chars))
            current_col_chars = [char]
            current_col_center_sum = center
            current_col_count = 1
        else:
            current_col_chars.append(char)
            current_col_center_sum += center
            current_col_count += 1

    if current_col_chars:
        x_min = min(c[0] for c in current_col_chars)
        x_max = max(c[1] for c in current_col_chars)
        columns.append((len(columns), x_min, x_max, current_col_chars))

    return columns


def split_mixed_columns(columns: list, size_threshold: int = 120) -> list:
    """拆分混合列（大字和小字），行内注释（小字与大字x范围重叠）合并回主列"""
    result = []
    for col_idx, x_min, x_max, chars in columns:
        large_chars = []
        small_chars = []
        for c in chars:
            width = c[1] - c[0]
            height = c[3] - c[2]
            if width >= size_threshold and height >= size_threshold:
                large_chars.append(c)
            else:
                small_chars.append(c)

        if small_chars and large_chars:
            lx_min = min(c[0] for c in large_chars)
            lx_max = max(c[1] for c in large_chars)
            sx_min = min(c[0] for c in small_chars)
            sx_max = max(c[1] for c in small_chars)
            overlap = min(lx_max, sx_max) - max(lx_min, sx_min)
            if overlap > 0 and overlap >= (sx_max - sx_min) * 0.5:
                large_chars.extend(small_chars)
                large_chars.sort(key=lambda c: c[2])
                small_chars = []

        if large_chars:
            lx_min = min(c[0] for c in large_chars)
            lx_max = max(c[1] for c in large_chars)
            result.append((len(result), lx_min, lx_max, large_chars))

        if small_chars:
            sx_min = min(c[0] for c in small_chars)
            sx_max = max(c[1] for c in small_chars)
            result.append((len(result), sx_min, sx_max, small_chars))

    return result


def filter_calligraphy_columns(columns: list, min_chars: int = 2,
                                 min_col_width: int = 130,
                                 min_char_width: int = None, min_char_height: int = None,
                                 min_annotation_width: int = None, min_annotation_height: int = None,
                                 **kwargs) -> list:
    """过滤书法列：列宽 >= min_col_width 且中位字符面积 >= 12000px"""
    result = []
    for col_idx, x_min, x_max, chars in columns:
        col_width = x_max - x_min
        if col_width < min_col_width or len(chars) < min_chars:
            continue
        areas = [(c[1]-c[0]) * (c[3]-c[2]) for c in chars]
        median_area = sorted(areas)[len(areas)//2] if areas else 0
        if median_area < 12000:
            continue
        result.append((col_idx, x_min, x_max, chars))

    # Sort result by x_min
    result.sort(key=lambda c: c[1])
    # Re-index
    result = [(i, c[1], c[2], c[3]) for i, c in enumerate(result)]

    return result


def detect_missing_chars_in_gaps(gray: np.ndarray, sorted_chars: list, x_min: int, x_max: int,
                                   gap_threshold: int = 80, binary_threshold: int = 140,
                                   min_area: int = 300) -> list:
    """在字符间隙中检测遗漏的字符（包括列末尾）"""
    missing = []
    h, w = gray.shape
    
    # Check gaps between characters
    for i in range(len(sorted_chars) - 1):
        curr = sorted_chars[i]
        next_char = sorted_chars[i + 1]
        
        gap_start = curr[3]  # y_max of current
        gap_end = next_char[2]  # y_min of next
        gap_size = gap_end - gap_start
        
        if gap_size < gap_threshold:
            continue
        
        # Extract gap region
        search_x1 = max(0, x_min - 20)
        search_x2 = min(w, x_max + 20)
        roi = gray[gap_start:gap_end, search_x1:search_x2]
        
        # Check dark pixel ratio
        dark_mask = roi < binary_threshold
        dark_ratio = np.sum(dark_mask) / dark_mask.size
        
        if dark_ratio < 0.15:
            continue
        
        # Connected component analysis
        _, binary = cv2.threshold(roi, binary_threshold, 255, cv2.THRESH_BINARY)
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
        
        # Find significant components
        candidates = []
        for j in range(1, num_labels):
            area = stats[j, cv2.CC_STAT_AREA]
            if area < min_area:
                continue
            
            x = stats[j, cv2.CC_STAT_LEFT] + search_x1
            y = stats[j, cv2.CC_STAT_TOP] + gap_start
            bw = stats[j, cv2.CC_STAT_WIDTH]
            bh = stats[j, cv2.CC_STAT_HEIGHT]
            
            # Check if this component is within the column's x range
            if x + bw < x_min - 10 or x > x_max + 10:
                continue
            
            # Filter by aspect ratio
            aspect_ratio = bw / bh if bh > 0 else 0
            if aspect_ratio < 0.2 or aspect_ratio > 5.0:
                continue
            
            # Skip small components (likely punctuation residue)
            if bw < 50 or bh < 50:
                continue
            
            candidates.append((x, x + bw, y, y + bh, area, bw, bh))
        
        # Merge nearby candidates
        if not candidates:
            continue
        
        merged = []
        used = [False] * len(candidates)
        
        for i in range(len(candidates)):
            if used[i]:
                continue
            
            current = candidates[i]
            merged_box = list(current[:4])
            merged_area = current[4]
            merged_bw = current[5]
            merged_bh = current[6]
            used[i] = True
            
            for j in range(i + 1, len(candidates)):
                if used[j]:
                    continue
                
                other = candidates[j]
                center1_x = (current[0] + current[1]) / 2
                center1_y = (current[2] + current[3]) / 2
                center2_x = (other[0] + other[1]) / 2
                center2_y = (other[2] + other[3]) / 2
                
                distance = ((center1_x - center2_x) ** 2 + (center1_y - center2_y) ** 2) ** 0.5
                
                if distance < 80:
                    merged_box[0] = min(merged_box[0], other[0])
                    merged_box[1] = max(merged_box[1], other[1])
                    merged_box[2] = min(merged_box[2], other[2])
                    merged_box[3] = max(merged_box[3], other[3])
                    merged_area += other[4]
                    merged_bw = merged_box[1] - merged_box[0]
                    merged_bh = merged_box[3] - merged_box[2]
                    used[j] = True
            
            merged.append((merged_box[0], merged_box[1], merged_box[2], merged_box[3], merged_area, merged_bw, merged_bh))
        
        for x1, x2, y1, y2, area, bw, bh in merged:
            missing.append((x1, x2, y1, y2, '?', 0.0, -1, -1))
    
    # Check for missing character at the end of the column
    if sorted_chars:
        last_char = sorted_chars[-1]
        gap_start = last_char[3]
        
        # Estimate gap size based on average character height
        avg_height = np.mean([c[3] - c[2] for c in sorted_chars])
        
        # 限制搜索高度为2倍平均字高，避免远距离墨迹干扰
        gap_end = min(h, gap_start + int(2 * avg_height))
        gap_size = gap_end - gap_start
        
        # If there's enough space for at least half a character
        if gap_size > avg_height * 0.5:
            search_x1 = max(0, x_min - 20)
            search_x2 = min(w, x_max + 20)
            roi = gray[gap_start:gap_end, search_x1:search_x2]
            
            dark_mask = roi < binary_threshold
            dark_ratio = np.sum(dark_mask) / dark_mask.size
            
            if dark_ratio > 0.1:
                _, binary = cv2.threshold(roi, binary_threshold, 255, cv2.THRESH_BINARY)
                num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
                
                candidates = []
                for j in range(1, num_labels):
                    area = stats[j, cv2.CC_STAT_AREA]
                    if area < min_area * 0.5:  # Allow smaller area for last char
                        continue
                    
                    x = stats[j, cv2.CC_STAT_LEFT] + search_x1
                    y = stats[j, cv2.CC_STAT_TOP] + gap_start
                    bw = stats[j, cv2.CC_STAT_WIDTH]
                    bh = stats[j, cv2.CC_STAT_HEIGHT]
                    
                    if x + bw < x_min - 10 or x > x_max + 10:
                        continue
                    
                    # Ink-tail check: candidate too close to last char (< 25% avg_height)
                    inter_gap = y - last_char[3]
                    if inter_gap >= 0 and inter_gap < avg_height * 0.25:
                        continue
                    
                    # Overlap check: candidate significantly overlaps last char
                    inter_x1 = max(x, last_char[0])
                    inter_x2 = min(x + bw, last_char[1])
                    inter_y1 = max(y, last_char[2])
                    inter_y2 = min(y + bh, last_char[3])
                    inter_w = max(0, inter_x2 - inter_x1)
                    inter_h = max(0, inter_y2 - inter_y1)
                    inter_area = inter_w * inter_h
                    if inter_area > 0 and inter_area / area > 0.5:
                        continue
                    
                    aspect_ratio = bw / bh if bh > 0 else 0
                    if aspect_ratio < 0.2 or aspect_ratio > 5.0:
                        continue
                    
                    # Skip small components (likely punctuation residue)
                    if bw < 50 or bh < 50:
                        continue
                    
                    candidates.append((x, x + bw, y, y + bh, area, bw, bh))
                
                if candidates:
                    # Take the largest candidate
                    best = max(candidates, key=lambda c: c[4])
                    missing.append((best[0], best[1], best[2], best[3], '?', 0.0, -1, -1))
    
    return missing
