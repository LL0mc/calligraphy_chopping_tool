"""调试脚本：v17 OCR定位+形态学笔画覆盖融合，输出 boxes 图"""
import os
import sys
import cv2

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import PDF_PATH, PAGES_DIR, DPI_SCALE
from src.pdf_renderer import render_pdf_page
from src.char_segmenter import segment_characters, draw_character_boxes

TEST_PAGES = [24, 30, 53, 187]

def main():
    print("=" * 60)
    print("v17 调试：OCR定位+形态学笔画覆盖融合")
    print("=" * 60)

    for page_1based in TEST_PAGES:
        page_idx = page_1based - 1
        print(f"\n{'='*40}")
        print(f"处理第 {page_1based} 页")
        print(f"{'='*40}")

        page_image_path = render_pdf_page(PDF_PATH, page_idx, PAGES_DIR, DPI_SCALE)
        original_gray = cv2.imread(page_image_path, cv2.IMREAD_GRAYSCALE)
        if original_gray is None:
            print(f"[错误] 无法读取: {page_image_path}")
            continue

        config = {
            "size_threshold": 120,
            "min_chars_per_col": 2,
            "min_char_width": 140,
            "min_char_height": 140,
            "binary_threshold": 140,
            "bbox_padding": 5,
        }

        characters = segment_characters(original_gray, config)
        if not characters:
            print("[警告] 未检测到字符")
            continue

        vis_path = os.path.join(PAGES_DIR, f"page_{page_1based:03d}_v17_boxes.png")
        draw_character_boxes(original_gray, characters, output_path=vis_path)
        print(f"[可视化] 已保存: {vis_path}")

    print("\n" + "=" * 60)
    print("完成！请查看 boxes 图并反馈")
    print("=" * 60)

if __name__ == "__main__":
    main()
