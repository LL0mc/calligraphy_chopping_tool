"""测试5个随机页面"""
import sys
import cv2
import random
sys.path.insert(0, '.')

from config import PDF_PATH, PAGES_DIR, CHARACTERS_DIR, DPI_SCALE
from src.pdf_renderer import render_pdf_page
from src.page_preprocessor import preprocess_page
from src.char_segmenter import segment_characters, save_characters
from src.ocr_recognizer import recognize_characters, draw_ocr_results
from src.confidence_handler import classify_by_confidence, get_confidence_summary, export_results

# 随机选择5个页面（避开前几页和最后几页）
random.seed(42)
all_pages = list(range(20, 220))  # 假设PDF有200+页
test_pages = sorted(random.sample(all_pages, 5))

print(f"随机选择的5个页面 (0-based): {test_pages}")
print(f"对应页码: {[p+1 for p in test_pages]}")

# OCR配置
OCR_ENGINE = "rapidocr"
EXPAND_STRATEGY = "square"
EXPAND_PADDING = 15

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
        
        # 导出结果
        export_path = f"{PAGES_DIR}/page_{page_num:03d}_ocr_results.json"
        export_results(ocr_results, export_path)
        
        # 保存字符
        char_output_dir = f"{CHARACTERS_DIR}/page_{page_num:03d}"
        save_characters(characters, char_output_dir, page_num)
        
        print(f"\n  识别结果预览 (前10个):")
        for r in ocr_results[:10]:
            text = r['ocr_text'] or '?'
            print(f"    列{r['col_idx']+1} 行{r['row_idx']+1}: {text} ({r['ocr_score']:.2f})")
        if len(ocr_results) > 10:
            print(f"    ... 共 {len(ocr_results)} 个字符")
        
    except Exception as e:
        import traceback
        print(f"  [错误] {e}")
        traceback.print_exc()

print(f"\n{'='*60}")
print("测试完成！")
print('='*60)
