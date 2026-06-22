"""单字切割模块 v12：OCR定位 + 连通域精确裁剪"""
import os
import cv2
import numpy as np
from src.types import CharBox


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

    if content_start is None or content_end is None or content_top is None or content_bottom is None:
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
        try:
            from rapidocr.utils.typings import OCRVersion, LangRec, LangDet
            ocr = RapidOCR(params={
                'Det.ocr_version': OCRVersion.PPOCRV5,
                'Det.lang_type': LangDet.CH,
                'Rec.ocr_version': OCRVersion.PPOCRV5,
                'Rec.lang_type': LangRec.CH,
            })
        except Exception:
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
        min_col_width=config.get("min_col_width", 130)
    )
    print(f"[过滤] 保留 {len(calligraphy_columns)} 个书法列")

    all_characters = []
    for new_col_idx, (old_col_idx, x_min, x_max, chars) in enumerate(calligraphy_columns):
        sorted_chars = sorted(chars, key=lambda c: c[2])
        claimed_boxes = []  # 每列独立的声明列表，从上到下处理
        
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
                exclude_boxes=punctuation_boxes,
                claimed_regions=claimed_boxes
            )
            
            # Claim this refined box so subsequent chars don't steal its components
            claimed_boxes.append((new_x, new_y, new_x + new_w, new_y + new_h))
            
            area = new_w * new_h
            char_img = gray[new_y:new_y+new_h, new_x:new_x+new_w]

            all_characters.append(CharBox(
                x=new_x, y=new_y, w=new_w, h=new_h,
                img=char_img, area=area,
                col_idx=new_col_idx, row_idx=row_idx,
                text=text, score=score,
            ))

        print(f"[切割] 列 {new_col_idx + 1} (x={x_min}-{x_max}): {len(sorted_chars)} 个字符")

    # 移除重叠框
    print(f"[去重] 去重前: {len(all_characters)} 个字符")
    all_characters = remove_overlapping_boxes(all_characters, iou_threshold=config.get("iou_threshold", 0.3))
    print(f"[去重] 去重后: {len(all_characters)} 个字符")

    # 后处理：过滤噪声框（空文字低置信度 + 异常小框）
    col_chars = {}
    for char in all_characters:
        col_idx = char.col_idx
        if col_idx not in col_chars:
            col_chars[col_idx] = []
        col_chars[col_idx].append(char)

    cleaned = []
    for col_idx, chars in col_chars.items():
        areas = [c.area for c in chars]
        if not areas:
            continue
        median_area = np.median(areas)
        for char in chars:
            text = char.text
            score = char.score
            area = char.area
            if not text.strip() and score < 0.5:
                print(f"[过滤] 列 {col_idx + 1}: 空文字低置信框 (conf={score:.2f}, area={area:.0f})")
                continue
            cleaned.append(char)
        print(f"[后处理] 列 {col_idx + 1}: 中位面积 {median_area:.0f}, 最大面积 {max(areas):.0f}")

    all_characters = cleaned
    print(f"[过滤] 过滤后: {len(all_characters)} 个字符")

    return all_characters


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
