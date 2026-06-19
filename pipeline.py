"""全流程批量处理：渲染 → 切割 → OCR → 校对 → 导出"""
import sys, os, json, logging
logging.disable(logging.CRITICAL)
os.environ['RAPIDOCR_LOG_LEVEL'] = 'CRITICAL'

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
from config import PDF_PATH, PAGES_DIR, DPI_SCALE
from src.pdf_renderer import render_pdf_page
from src.page_preprocessor import preprocess_page
from src.char_segmenter import (
    segment_characters, get_ocr_char_boxes,
    classify_columns, split_mixed_columns, filter_calligraphy_columns,
    detect_main_content_bbox
)
from src.ocr_recognizer import recognize_characters
from src.confidence_handler import export_results


def process_page(page_num, poems_data=None, ocr_engine="rapidocr",
                 expand_strategy="square", expand_padding=15,
                 remove_lines=False):
    """处理单页：渲染 → 切割 → OCR → 校对"""
    page_idx = page_num - 1
    print(f"\n=== 第{page_num}页 ===")

    # Step 1: Render
    page_image_path = render_pdf_page(PDF_PATH, page_idx, PAGES_DIR, DPI_SCALE)
    original_gray = cv2.imread(page_image_path, cv2.IMREAD_GRAYSCALE)

    # Step 2: Preprocess
    preprocessed_path = os.path.join(PAGES_DIR, f"page_{page_num:03d}_processed.png")
    preprocess_page(page_image_path, preprocessed_path, remove_lines=remove_lines)

    # Step 3: Segment characters
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
        print("  [跳过] 未检测到字符")
        return None

    # Step 4: OCR recognition
    ocr_results = recognize_characters(
        original_gray, characters,
        engine=ocr_engine,
        expand_strategy=expand_strategy,
        expand_padding=expand_padding
    )

    # Step 5: Export raw OCR
    raw_path = os.path.join(PAGES_DIR, f"page_{page_num:03d}_ocr_results.json")
    export_results(ocr_results, raw_path)
    print(f"  OCR完成: {len(ocr_results)} 个字符")

    return {"characters": characters, "ocr_results": ocr_results}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="字帖全流程处理")
    parser.add_argument("pages", nargs="+", type=int, help="页码（1-based）")
    parser.add_argument("--no-correct", action="store_true", help="（已弃用）")
    args = parser.parse_args()

    for page_num in args.pages:
        try:
            process_page(page_num)
        except Exception as e:
            import traceback
            print(f"  [错误] 第{page_num}页: {e}")
            traceback.print_exc()

    print("\n完成！")


if __name__ == "__main__":
    main()
