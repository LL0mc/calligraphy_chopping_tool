"""为5个随机页面生成OCR可视化图"""
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
from src.ocr_recognizer import recognize_characters, draw_ocr_results
from src.confidence_handler import classify_by_confidence, get_confidence_summary, export_results

# 5个随机页面 (0-based)
test_pages = [26, 48, 90, 183, 209]

# OCR配置
OCR_ENGINE = "rapidocr"
EXPAND_STRATEGY = "square"
EXPAND_PADDING = 15

for page_idx in test_pages:
    page_num = page_idx + 1
    print(f"\n{'='*60}")
    print(f"生成第 {page_num} 页可视化...")
    print('='*60)
    
    try:
        page_image_path = render_pdf_page(PDF_PATH, page_idx, PAGES_DIR, DPI_SCALE)
        preprocessed_path = f"{PAGES_DIR}/page_{page_num:03d}_processed.png"
        gray = preprocess_page(page_image_path, preprocessed_path, remove_lines=False)
        original_gray = cv2.imread(page_image_path, cv2.IMREAD_GRAYSCALE)
        
        config = {
            "min_chars_per_col": 2,
            "min_char_width": 100,
            "min_char_height": 100,
            "size_threshold": 120,
            "binary_threshold": 140,
            "bbox_padding": 5,
        }
        
        characters = segment_characters(original_gray, config)
        
        if not characters:
            print("  [警告] 未检测到任何字符")
            continue
        
        print(f"\n  开始OCR识别...")
        ocr_results = recognize_characters(
            original_gray, characters,
            engine=OCR_ENGINE,
            expand_strategy=EXPAND_STRATEGY,
            expand_padding=EXPAND_PADDING
        )
        
        classified = classify_by_confidence(ocr_results)
        print(f"\n  {get_confidence_summary(classified)}")
        
        # 获取列信息
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
        calligraphy_cols = filter_calligraphy_columns(split_cols, min_chars=2, min_col_width=130)
        columns = [(c[1], c[2]) for c in calligraphy_cols]
        
        # 绘制OCR结果
        vis_path = f"{PAGES_DIR}/page_{page_num:03d}_ocr_{EXPAND_STRATEGY}.png"
        draw_ocr_results(original_gray, ocr_results, columns, vis_path)
        
        # 导出结果
        export_path = f"{PAGES_DIR}/page_{page_num:03d}_ocr_results.json"
        export_results(ocr_results, export_path)
        
        # 保存字符
        char_output_dir = f"{CHARACTERS_DIR}/page_{page_num:03d}"
        save_characters(characters, char_output_dir, page_num)
        
        print(f"  可视化: {vis_path}")
        print(f"  结果: {export_path}")
        
    except Exception as e:
        import traceback
        print(f"  [错误] {e}")
        traceback.print_exc()

print(f"\n{'='*60}")
print("完成！")
print('='*60)
