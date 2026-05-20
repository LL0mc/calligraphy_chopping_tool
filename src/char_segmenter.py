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
    """获取OCR检测到的字符框"""
    try:
        from rapidocr import RapidOCR
        ocr = RapidOCR()
        result = ocr(gray, return_word_box=True)

        all_chars = []
        for line_idx, word_group in enumerate(result.word_results):
            char_idx = 0
            for item in word_group:
                if isinstance(item, tuple) and len(item) == 3:
                    char_text, char_score, char_box = item
                    x_coords = [p[0] for p in char_box]
                    y_coords = [p[1] for p in char_box]
                    x_min = int(min(x_coords))
                    x_max = int(max(x_coords))
                    y_min = int(min(y_coords))
                    y_max = int(max(y_coords))
                    all_chars.append((x_min, x_max, y_min, y_max, char_text, char_score, line_idx, char_idx))
                    char_idx += 1
        return all_chars
    except Exception as e:
        print(f"[OCR] 获取单字框失败: {e}")
        return []


def refine_char_bbox(gray: np.ndarray, x_min: int, x_max: int, y_min: int, y_max: int,
                     binary_threshold: int = 140, padding: int = 5,
                     search_margin_x: int = 40, search_margin_y: int = 60,
                     merge_radius: int = 80) -> tuple:
    """以OCR框为中心，用连通域精确裁剪字符"""
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
    
    merged_x_min = roi_w
    merged_y_min = roi_h
    merged_x_max = 0
    merged_y_max = 0
    found_any = False
    
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < 30:
            continue
            
        x = stats[i, cv2.CC_STAT_LEFT]
        y = stats[i, cv2.CC_STAT_TOP]
        bw = stats[i, cv2.CC_STAT_WIDTH]
        bh = stats[i, cv2.CC_STAT_HEIGHT]
        
        cx = x + bw // 2
        cy = y + bh // 2
        
        if abs(cx - center_x) < merge_radius and abs(cy - center_y) < merge_radius:
            merged_x_min = min(merged_x_min, x)
            merged_y_min = min(merged_y_min, y)
            merged_x_max = max(merged_x_max, x + bw)
            merged_y_max = max(merged_y_max, y + bh)
            found_any = True
    
    if not found_any:
        return (x_min, y_min, x_max - x_min, y_max - y_min)
    
    new_x_min = max(0, search_x1 + merged_x_min - padding)
    new_y_min = max(0, search_y1 + merged_y_min - padding)
    new_w = min(w - new_x_min, (merged_x_max - merged_x_min) + padding * 2)
    new_h = min(h - new_y_min, (merged_y_max - merged_y_min) + padding * 2)
    
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
                                min_char_width: int = 100, min_char_height: int = 100) -> list:
    """过滤出书法列"""
    result = []
    for col_idx, x_min, x_max, chars in columns:
        avg_width = np.mean([c[1] - c[0] for c in chars])
        avg_height = np.mean([c[3] - c[2] for c in chars])

        if avg_width >= min_char_width and avg_height >= min_char_height and len(chars) >= min_chars:
            result.append((col_idx, x_min, x_max, chars))

    return result


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
    all_chars = [c for c in all_chars if c[4] not in punctuation and len(c[4].strip()) > 0]
    
    print(f"[OCR] 检测到 {len(all_chars)} 个单字（已过滤标点）")

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

        for row_idx, (cx_min, cx_max, cy_min, cy_max, text, score, line_idx, char_idx) in enumerate(sorted_chars):
            new_x, new_y, new_w, new_h = refine_char_bbox(
                gray, cx_min, cx_max, cy_min, cy_max,
                binary_threshold=config.get("binary_threshold", 140),
                padding=config.get("bbox_padding", 5)
            )
            
            area = new_w * new_h
            char_img = gray[new_y:new_y+new_h, new_x:new_x+new_w]

            all_characters.append((
                new_x, new_y, new_w, new_h, char_img, area,
                new_col_idx, row_idx, text, score
            ))

        print(f"[切割] 列 {new_col_idx + 1} (x={x_min}-{x_max}): {len(sorted_chars)} 个字符")

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
