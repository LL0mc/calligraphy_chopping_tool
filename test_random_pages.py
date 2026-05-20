"""测试3个随机页面"""
import sys
import cv2
sys.path.insert(0, '.')

from config import PDF_PATH, PAGES_DIR, CHARACTERS_DIR, DPI_SCALE
from src.pdf_renderer import render_pdf_page
from src.page_preprocessor import preprocess_page
from src.char_segmenter import segment_characters, save_characters

test_pages = [29, 52, 186]  # 第30, 53, 187页 (0-based)

for page_idx in test_pages:
    page_num = page_idx + 1
    print(f"\n{'='*60}")
    print(f"测试第 {page_num} 页")
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
        
        if characters:
            char_output_dir = f"{CHARACTERS_DIR}/page_{page_num:03d}"
            save_characters(characters, char_output_dir, page_num)
            
            # 统计
            print(f"\n  字符总数: {len(characters)}")
            
            # 按列统计
            cols = {}
            for c in characters:
                col_idx = c[6]
                if col_idx not in cols:
                    cols[col_idx] = []
                cols[col_idx].append(c)
            
            for col_idx in sorted(cols.keys()):
                col_chars = cols[col_idx]
                texts = [c[8] for c in col_chars]
                print(f"  列 {col_idx + 1}: {len(col_chars)} 个字符")
                print(f"    文字: {' '.join(texts)}")
        else:
            print("  [警告] 未检测到任何字符")
            
    except Exception as e:
        print(f"  [错误] {e}")

print(f"\n{'='*60}")
print("测试完成！")
print('='*60)
