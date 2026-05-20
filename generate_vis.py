"""生成3页的边界框可视化"""
import sys
import cv2
sys.path.insert(0, '.')

from config import PDF_PATH, PAGES_DIR, CHARACTERS_DIR, DPI_SCALE
from src.pdf_renderer import render_pdf_page
from src.page_preprocessor import preprocess_page
from src.char_segmenter import (
    segment_characters, save_characters, draw_character_boxes, 
    get_ocr_char_boxes, classify_columns, split_mixed_columns, 
    filter_calligraphy_columns, detect_main_content_bbox
)

test_pages = [29, 52, 186]  # 第30, 53, 187页

for page_idx in test_pages:
    page_num = page_idx + 1
    print(f"\n生成第 {page_num} 页可视化...")
    
    # 渲染
    page_image_path = render_pdf_page(PDF_PATH, page_idx, PAGES_DIR, DPI_SCALE)
    preprocessed_path = f"{PAGES_DIR}/page_{page_num:03d}_processed.png"
    gray = preprocess_page(page_image_path, preprocessed_path, remove_lines=False)
    original_gray = cv2.imread(page_image_path, cv2.IMREAD_GRAYSCALE)
    
    # 切割
    config = {
        "min_chars_per_col": 2,
        "min_char_width": 100,
        "min_char_height": 100,
        "size_threshold": 120,
        "binary_threshold": 140,
        "bbox_padding": 5,
    }
    characters = segment_characters(original_gray, config)
    
    # 获取列信息用于可视化
    content_x_min, content_y_min, content_x_max, content_y_max = detect_main_content_bbox(original_gray)
    gray_cropped = original_gray[content_y_min:content_y_max, content_x_min:content_x_max]
    
    all_chars = get_ocr_char_boxes(gray_cropped)
    all_chars = [(
        c[0] + content_x_min, c[1] + content_x_min,
        c[2] + content_y_min, c[3] + content_y_min,
        c[4], c[5], c[6], c[7]
    ) for c in all_chars]
    
    punctuation = set('（）()[]【】{}《》<>""\'\'.,;:!?、。！？；：，．')
    all_chars = [c for c in all_chars if c[4] not in punctuation and len(c[4].strip()) > 0]
    
    columns_info = classify_columns(all_chars)
    split_cols = split_mixed_columns(columns_info, size_threshold=120)
    calligraphy_cols = filter_calligraphy_columns(split_cols, min_chars=2, min_char_width=100, min_char_height=100)
    columns = [(c[1], c[2]) for c in calligraphy_cols]
    
    # 绘制边界框
    vis_path = f"{PAGES_DIR}/page_{page_num:03d}_boxes.png"
    draw_character_boxes(original_gray, characters, columns, vis_path)
    
    # 保存字符
    char_output_dir = f"{CHARACTERS_DIR}/page_{page_num:03d}"
    save_characters(characters, char_output_dir, page_num)
    
    print(f"  已保存 {len(characters)} 个字符")
    print(f"  可视化: {vis_path}")

print("\n完成！")
