"""单字切割模块 v12：OCR定位 + 连通域精确裁剪"""
import os
import cv2
import numpy as np


def detect_main_content_bbox(gray: np.ndarray, min_density_ratio: float = 0.15, window: int = 100) -> tuple:
    """检测主要内容区域的边界框"""
    h, w = gray.shape
    dark_mask = gray < 130
    col_dark = np.sum(dark_mask, axis=0)
    row_dark = np.sum(dark_mask, axis=1)
    threshold = h * min_density_ratio

    content_start = None
    for x in range(0, w - window, 10):
        if col_dark[x:x+window].mean() > threshold:
            content_start = x
            break

    content_end = None
    for x in range(w - window, 0, -10):
        if col_dark[x-window:x].mean() > threshold:
            content_end = x
            break

    content_top = None
    for y in range(0, h - window, 10):
        if row_dark[y:y+window].mean() > threshold:
            content_top = y
            break

    content_bottom = None
    for y in range(h - window, 0, -10):
        if row_dark[y-window:y].mean() > threshold:
            content_bottom = y
            break

    if content_start is None or content_end is None:
        return (0, 0, w, h)

    margin = 20
    return (
        max(0, content_start - margin),
        max(0, content_top - margin),
        min(w, content_end + margin),
        min(h, content_bottom + margin)
    )


def get_ocr_char_boxes(gray: np.ndarray) -> list:
    """获取OCR检测到的字符框（按行分组，返回单字级别）"""
    try:
        from rapidocr import RapidOCR
        ocr = RapidOCR()
        result = ocr(gray, return_word_box=True)

        all_chars = []
        for line_idx, line_chars in enumerate(result.word_results):
            if not line_chars:
                continue
            for char_idx, item in enumerate(line_chars):
                if isinstance(item, tuple) and len(item) == 3:
                    char_text, char_score, char_box = item
                    x_coords = [p[0] for p in char_box]
                    y_coords = [p[1] for p in char_box]
                    x_min = int(min(x_coords))
                    x_max = int(max(x_coords))
                    y_min = int(min(y_coords))
                    y_max = int(max(y_coords))
                    all_chars.append((x_min, x_max, y_min, y_max, char_text, char_score, line_idx, char_idx))
        return all_chars
    except Exception as e:
        print(f"[OCR] 获取单字框失败: {e}")
        return []


def refine_char_bbox(gray: np.ndarray, x_min: int, x_max: int, y_min: int, y_max: int,
                     binary_threshold: int = 140, padding: int = 5,
                     search_margin_x: int = 40, search_margin_y: int = 60,
                     merge_radius: int = 80,
                     exclude_boxes: list = None) -> tuple:
    """以OCR框为中心，用连通域精确裁剪字符，排除标点区域（两阶段修正）"""
    h, w = gray.shape
    
    # Stage 1: Rough localization with punctuation exclusion
    search_x1 = max(0, x_min - search_margin_x)
    search_x2 = min(w, x_max + search_margin_x)
    search_y1 = max(0, y_min - search_margin_y)
    search_y2 = min(h, y_max + search_margin_y)
    
    roi = gray[search_y1:search_y2, search_x1:search_x2]
    _, binary = cv2.threshold(roi, binary_threshold, 255, cv2.THRESH_BINARY)
    
    # Mask out punctuation areas
    if exclude_boxes:
        for ex_x1, ex_y1, ex_w, ex_h in exclude_boxes:
            rx1 = max(0, ex_x1 - search_x1)
            ry1 = max(0, ex_y1 - search_y1)
            rx2 = min(roi.shape[1], ex_x1 + ex_w - search_x1)
            ry2 = min(roi.shape[0], ex_y1 + ex_h - search_y1)
            if rx2 > rx1 and ry2 > ry1:
                binary[ry1:ry2, rx1:rx2] = 0
    
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
    
    roi_h, roi_w = binary.shape
    center_x = (x_min - search_x1 + x_max - search_x1) // 2
    center_y = (y_min - search_y1 + y_max - search_y1) // 2
    
    # Collect candidate components
    candidates = []
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        # Filter very small noise
        if area < 20:
            continue
            
        x = stats[i, cv2.CC_STAT_LEFT]
        y = stats[i, cv2.CC_STAT_TOP]
        bw = stats[i, cv2.CC_STAT_WIDTH]
        bh = stats[i, cv2.CC_STAT_HEIGHT]
        
        cx = x + bw // 2
        cy = y + bh // 2
        
        # Check distance to center
        dist = ((cx - center_x) ** 2 + (cy - center_y) ** 2) ** 0.5
        if dist < merge_radius:
            candidates.append((x, y, bw, bh, area, cx, cy))
    
    if not candidates:
        return (x_min, y_min, x_max - x_min, y_max - y_min)
    
    # Stage 2: Merge and refine
    # Sort candidates by area descending to prioritize main character parts
    candidates.sort(key=lambda c: c[4], reverse=True)
    
    # Merge nearby candidates
    merged_x_min = roi_w
    merged_y_min = roi_h
    merged_x_max = 0
    merged_y_max = 0
    
    # Use the largest component as seed
    seed = candidates[0]
    merged_x_min = min(merged_x_min, seed[0])
    merged_y_min = min(merged_y_min, seed[1])
    merged_x_max = max(merged_x_max, seed[0] + seed[2])
    merged_y_max = max(merged_y_max, seed[1] + seed[3])
    
    # Only merge components that are close to the seed or to the current merged box
    # Use a smaller radius for merging to avoid including noise
    merge_dist = 30
    
    for i in range(1, len(candidates)):
        c = candidates[i]
        # Check distance to seed center
        c_cx = c[0] + c[2] // 2
        c_cy = c[1] + c[3] // 2
        seed_cx = seed[0] + seed[2] // 2
        seed_cy = seed[1] + seed[3] // 2
        
        dist_to_seed = ((c_cx - seed_cx) ** 2 + (c_cy - seed_cy) ** 2) ** 0.5
        
        # Also check distance to current merged box
        # Find closest point on merged box to component center
        closest_x = max(merged_x_min, min(c_cx, merged_x_max))
        closest_y = max(merged_y_min, min(c_cy, merged_y_max))
        dist_to_box = ((c_cx - closest_x) ** 2 + (c_cy - closest_y) ** 2) ** 0.5
        
        if dist_to_seed < merge_dist or dist_to_box < merge_dist:
            merged_x_min = min(merged_x_min, c[0])
            merged_y_min = min(merged_y_min, c[1])
            merged_x_max = max(merged_x_max, c[0] + c[2])
            merged_y_max = max(merged_y_max, c[1] + c[3])
    
    # Final box in global coordinates
    new_x_min = max(0, search_x1 + merged_x_min - padding)
    new_y_min = max(0, search_y1 + merged_y_min - padding)
    new_w = min(w - new_x_min, (merged_x_max - merged_x_min) + padding * 2)
    new_h = min(h - new_y_min, (merged_y_max - merged_y_min) + padding * 2)
    
    # Post-processing: If the refined box is much larger than the OCR box, check if we should shrink it
    ocr_w = x_max - x_min
    ocr_h = y_max - y_min
    ocr_area = ocr_w * ocr_h
    new_area = new_w * new_h
    
    # If new box is > 2x OCR area and OCR box had a significant component, prefer OCR box centered on largest component
    if new_area > ocr_area * 2.0 and ocr_area > 1000:
        # Check if seed component is mostly within OCR box
        seed_x1 = search_x1 + seed[0]
        seed_y1 = search_y1 + seed[1]
        seed_x2 = seed_x1 + seed[2]
        seed_y2 = seed_y1 + seed[3]
        
        # Intersection with OCR box
        inter_x1 = max(seed_x1, x_min)
        inter_y1 = max(seed_y1, y_min)
        inter_x2 = min(seed_x2, x_max)
        inter_y2 = min(seed_y2, y_max)
        
        if inter_x2 > inter_x1 and inter_y2 > inter_y1:
            inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
            seed_area = seed[2] * seed[3]
            
            # If most of the seed is within OCR box, use a tighter box around seed
            if inter_area > seed_area * 0.5:
                new_x_min = max(0, seed_x1 - padding)
                new_y_min = max(0, seed_y1 - padding)
                new_w = min(w - new_x_min, seed[2] + padding * 2)
                new_h = min(h - new_y_min, seed[3] + padding * 2)
    
    # Post-processing: Ensure box doesn't overlap with exclude_boxes significantly
    if exclude_boxes:
        for ex_x1, ex_y1, ex_w, ex_h in exclude_boxes:
            # Calculate IoU with exclude box
            inter_x1 = max(new_x_min, ex_x1)
            inter_y1 = max(new_y_min, ex_y1)
            inter_x2 = min(new_x_min + new_w, ex_x1 + ex_w)
            inter_y2 = min(new_y_min + new_h, ex_y1 + ex_h)
            
            if inter_x2 > inter_x1 and inter_y2 > inter_y1:
                inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
                box_area = new_w * new_h
                if box_area > 0 and inter_area / box_area > 0.3:
                    # Trim the box to exclude the punctuation area
                    if inter_x1 == ex_x1:
                        new_x_min = max(new_x_min, ex_x1 + ex_w)
                    elif inter_x2 == ex_x1 + ex_w:
                        new_w = min(new_w, ex_x1 - new_x_min)
                    
                    if inter_y1 == ex_y1:
                        new_y_min = max(new_y_min, ex_y1 + ex_h)
                    elif inter_y2 == ex_y1 + ex_h:
                        new_h = min(new_h, ex_y1 - new_y_min)
                    
                    new_w = max(10, new_w)
                    new_h = max(10, new_h)
    
    return (new_x_min, new_y_min, new_w, new_h)


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
    """拆分混合列（大字和小字）"""
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
                                 min_char_width: int = 100, min_char_height: int = 100,
                                 min_annotation_width: int = 50, min_annotation_height: int = 50) -> list:
    """过滤出书法列，同时保留同列的小字标注"""
    result = []
    # First pass: identify main calligraphy columns
    main_cols = []
    for col_idx, x_min, x_max, chars in columns:
        avg_width = np.mean([c[1] - c[0] for c in chars])
        avg_height = np.mean([c[3] - c[2] for c in chars])

        if avg_width >= min_char_width and avg_height >= min_char_height and len(chars) >= min_chars:
            main_cols.append((col_idx, x_min, x_max, chars))

    # Second pass: merge small chars from nearby columns into main columns
    # Or keep small char columns if they are close to a main column
    processed_small_cols = set()
    for i, (main_col_idx, main_x_min, main_x_max, main_chars) in enumerate(main_cols):
        # Find small char columns that overlap or are adjacent to this main column
        for col_idx, x_min, x_max, chars in columns:
            if col_idx == main_col_idx:
                continue
            
            # Check x-overlap or proximity
            if x_max >= main_x_min - 50 and x_min <= main_x_max + 50:
                # Check if these are small chars
                avg_width = np.mean([c[1] - c[0] for c in chars])
                avg_height = np.mean([c[3] - c[2] for c in chars])
                
                if avg_width < min_char_width or avg_height < min_char_height:
                    # Filter small chars by annotation threshold
                    valid_small_chars = []
                    for c in chars:
                        w = c[1] - c[0]
                        h = c[3] - c[2]
                        if w >= min_annotation_width and h >= min_annotation_height:
                            valid_small_chars.append(c)
                    
                    if valid_small_chars:
                        # Merge into main column
                        merged_chars = main_chars + valid_small_chars
                        # Re-sort by y
                        merged_chars.sort(key=lambda c: c[2])
                        # Update main column
                        main_cols[i] = (main_col_idx, min(main_x_min, x_min), max(main_x_max, x_max), merged_chars)
                        processed_small_cols.add(col_idx)

    # Add main columns to result
    for col in main_cols:
        result.append(col)

    # Add any remaining columns that meet the main threshold (in case we missed any)
    for col_idx, x_min, x_max, chars in columns:
        if col_idx not in [c[0] for c in main_cols] and col_idx not in processed_small_cols:
            avg_width = np.mean([c[1] - c[0] for c in chars])
            avg_height = np.mean([c[3] - c[2] for c in chars])
            if avg_width >= min_char_width and avg_height >= min_char_height and len(chars) >= min_chars:
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
                
                if distance < 40:
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
        gap_end = h  # Use full image height
        
        # Estimate gap size based on average character height
        avg_height = np.mean([c[3] - c[2] for c in sorted_chars])
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
                    
                    aspect_ratio = bw / bh if bh > 0 else 0
                    if aspect_ratio < 0.2 or aspect_ratio > 5.0:
                        continue
                    
                    candidates.append((x, x + bw, y, y + bh, area, bw, bh))
                
                if candidates:
                    # Take the largest candidate
                    best = max(candidates, key=lambda c: c[4])
                    missing.append((best[0], best[1], best[2], best[3], '?', 0.0, -1, -1))
    
    return missing


def segment_characters(gray: np.ndarray, config: dict = None) -> list:
    """主流程：OCR定位 + 连通域精确裁剪（不重叠）"""
    if config is None:
        config = {}

    h, w = gray.shape

    content_x_min, content_y_min, content_x_max, content_y_max = detect_main_content_bbox(gray)
    print(f"[内容裁剪] 主内容区域: ({content_x_min},{content_y_min})-({content_x_max},{content_y_max})")
    
    gray_cropped = gray[content_y_min:content_y_max, content_x_min:content_x_max]
    
    all_chars = get_ocr_char_boxes(gray_cropped)
    
    all_chars = [(
        c[0] + content_x_min, c[1] + content_x_min,
        c[2] + content_y_min, c[3] + content_y_min,
        c[4], c[5], c[6], c[7]
    ) for c in all_chars]
    
    punctuation = set('（）()[]【】{}《》<>""\'\'.,;:!?、。！？；：，．')
    punctuation_boxes = []
    filtered_chars = []
    for c in all_chars:
        if c[4] in punctuation or len(c[4].strip()) == 0:
            punctuation_boxes.append((c[0], c[2], c[1] - c[0], c[3] - c[2]))
        else:
            filtered_chars.append(c)
    all_chars = filtered_chars
    
    print(f"[OCR] 检测到 {len(all_chars)} 个单字（已过滤标点，排除 {len(punctuation_boxes)} 个标点区域）")

    columns = classify_columns(all_chars)
    print(f"[分列] 检测到 {len(columns)} 列")

    split_cols = split_mixed_columns(columns, size_threshold=config.get("size_threshold", 120))
    print(f"[拆分] 拆分为 {len(split_cols)} 个子列")

    calligraphy_columns = filter_calligraphy_columns(
        split_cols,
        min_chars=config.get("min_chars_per_col", 3),
        min_char_width=config.get("min_char_width", 150),
        min_char_height=config.get("min_char_height", 150)
    )
    print(f"[过滤] 保留 {len(calligraphy_columns)} 个书法列")

    all_characters = []
    for new_col_idx, (old_col_idx, x_min, x_max, chars) in enumerate(calligraphy_columns):
        sorted_chars = sorted(chars, key=lambda c: c[2])
        
        # 检测遗漏字符
        missing_chars = detect_missing_chars_in_gaps(
            gray, sorted_chars, x_min, x_max,
            gap_threshold=config.get("gap_threshold", 100),
            binary_threshold=config.get("binary_threshold", 140),
            min_area=config.get("missing_char_min_area", 500)
        )
        
        if missing_chars:
            print(f"[遗漏检测] 列 {new_col_idx + 1} 发现 {len(missing_chars)} 个遗漏字符")
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

        print(f"[切割] 列 {new_col_idx + 1} (x={x_min}-{x_max}): {len(sorted_chars)} 个字符")

    # 移除重叠框
    print(f"[去重] 去重前: {len(all_characters)} 个字符")
    all_characters = remove_overlapping_boxes(all_characters, iou_threshold=config.get("iou_threshold", 0.3))
    print(f"[去重] 去重后: {len(all_characters)} 个字符")

    # 后处理：修正过大的框（通常是列末尾的遗漏字符）
    # 按列分组
    col_chars = {}
    for char in all_characters:
        col_idx = char[6]
        if col_idx not in col_chars:
            col_chars[col_idx] = []
        col_chars[col_idx].append(char)
    
    # 对每列检查异常大的框
    for col_idx, chars in col_chars.items():
        areas = [c[2] * c[3] for c in chars]
        if not areas:
            continue
        median_area = np.median(areas)
        print(f"[后处理] 列 {col_idx + 1}: 中位面积 {median_area:.0f}, 最大面积 {max(areas):.0f}")
        
        for i, char in enumerate(chars):
            area = char[2] * char[3]
            # 如果面积大于中位数的3倍，尝试缩小
            if area > median_area * 3.0 and median_area > 1000:
                print(f"[后处理] 列 {col_idx + 1} 行 {char[7] + 1}: 面积 {area:.0f} 过大，缩小")
                # 计算目标尺寸（基于中位数面积的平方根）
                target_size = int(np.sqrt(median_area))
                # 保持中心不变，缩小框
                cx = char[0] + char[2] // 2
                cy = char[1] + char[3] // 2
                
                new_w = min(char[2], target_size)
                new_h = min(char[3], target_size)
                
                new_x = max(0, cx - new_w // 2)
                new_y = max(0, cy - new_h // 2)
                
                # 更新字符信息
                chars[i] = (
                    new_x, new_y, new_w, new_h,
                    gray[new_y:new_y+new_h, new_x:new_x+new_w],
                    new_w * new_h,
                    char[6], char[7], char[8], char[9]
                )
    
    # 重新合并所有字符
    all_characters = []
    for col_idx in sorted(col_chars.keys()):
        all_characters.extend(col_chars[col_idx])

    return all_characters


def save_characters(characters: list, output_dir: str, page_num: int, pad_size: int = 10) -> list:
    os.makedirs(output_dir, exist_ok=True)
    saved_paths = []

    for x, y, w, h, char_img, area, col_idx, row_idx, text, score in characters:
        char_size = max(w, h) + pad_size * 2
        bg = np.full((char_size, char_size), 255, dtype=np.uint8)

        offset_x = (char_size - w) // 2
        offset_y = (char_size - h) // 2
        bg[offset_y:offset_y + h, offset_x:offset_x + w] = char_img

        filename = f"page{page_num:03d}_col{col_idx+1:02d}_row{row_idx+1:02d}.png"
        filepath = os.path.join(output_dir, filename)
        cv2.imwrite(filepath, bg)
        saved_paths.append(filepath)

    return saved_paths


def compute_iou(box1: tuple, box2: tuple) -> float:
    """计算两个框的IoU (x, y, w, h)"""
    x1_1, y1_1, w1, h1 = box1
    x1_2, y1_2, w2, h2 = box2
    x2_1, y2_1 = x1_1 + w1, y1_1 + h1
    x2_2, y2_2 = x1_2 + w2, y1_2 + h2
    
    inter_x1 = max(x1_1, x1_2)
    inter_y1 = max(y1_1, y1_2)
    inter_x2 = min(x2_1, x2_2)
    inter_y2 = min(y2_1, y2_2)
    
    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    
    area1 = w1 * h1
    area2 = w2 * h2
    union_area = area1 + area2 - inter_area
    
    return inter_area / union_area if union_area > 0 else 0


def remove_overlapping_boxes(characters: list, iou_threshold: float = 0.3) -> list:
    """移除重叠的字符框，保留面积较大的框"""
    if not characters:
        return []
    
    # 按面积降序排序
    sorted_chars = sorted(characters, key=lambda c: c[2] * c[3], reverse=True)
    
    keep = []
    for char in sorted_chars:
        box = (char[0], char[1], char[2], char[3])
        is_overlap = False
        for kept in keep:
            kept_box = (kept[0], kept[1], kept[2], kept[3])
            iou = compute_iou(box, kept_box)
            if iou > iou_threshold:
                is_overlap = True
                break
        if not is_overlap:
            keep.append(char)
    
    # 按列和行重新排序
    keep.sort(key=lambda c: (c[6], c[7]))
    return keep


def draw_character_boxes(original_image: np.ndarray, characters: list,
                         columns: list = None, output_path: str = None) -> np.ndarray:
    color_img = cv2.cvtColor(original_image, cv2.COLOR_GRAY2BGR)

    if columns:
        for col_start, col_end in columns:
            cv2.line(color_img, (col_start, 0), (col_start, original_image.shape[0]), (0, 0, 255), 2)
            cv2.line(color_img, (col_end, 0), (col_end, original_image.shape[0]), (0, 0, 255), 2)

    colors = [(0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0),
              (255, 0, 255), (0, 255, 255), (128, 128, 255)]

    col_dict = {}
    for char in characters:
        col_idx = char[6]
        if col_idx not in col_dict:
            col_dict[col_idx] = []
        col_dict[col_idx].append(char)

    for col_idx, col_chars in col_dict.items():
        color = colors[col_idx % len(colors)]
        for char in col_chars:
            x, y, w, h = char[0], char[1], char[2], char[3]
            score = char[9] if len(char) > 9 else 0

            cv2.rectangle(color_img, (x, y), (x + w, y + h), color, 2)
            label = f"{score:.2f}"
            cv2.putText(color_img, label, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

    if output_path:
        cv2.imwrite(output_path, color_img)
        print(f"[可视化] 保存边界框图: {output_path}")

    return color_img
