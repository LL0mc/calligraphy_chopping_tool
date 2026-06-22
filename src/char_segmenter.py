"""单字切割模块 v12：OCR定位 + 连通域精确裁剪
Re-exported from detection/segmentation/refinement submodules.
"""
import numpy as np
from src.types import CharBox
from src.detection import detect_main_content_bbox, get_ocr_char_boxes
from src.segmentation import (
    classify_columns, split_mixed_columns,
    filter_calligraphy_columns, detect_missing_chars_in_gaps,
)
from src.refinement import (
    refine_char_bbox, compute_iou, remove_overlapping_boxes,
)


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
