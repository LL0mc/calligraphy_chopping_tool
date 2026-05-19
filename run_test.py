"""测试脚本：以单页为例运行完整切割流程 v15"""
import os
import sys
import cv2

# 设置UTF-8输出编码
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    PDF_PATH, PAGES_DIR, CHARACTERS_DIR, DPI_SCALE, TEST_PAGE_INDEX
)
from src.pdf_renderer import render_pdf_page
from src.page_preprocessor import preprocess_page
from src.char_segmenter import (
    segment_characters, save_characters, draw_character_boxes, get_ocr_char_boxes,
    classify_columns, split_mixed_columns, filter_calligraphy_columns, detect_main_content_bbox
)


def main():
    print("=" * 60)
    print("单字切割测试 v15 (内容裁剪 + OCR单字框 + 精确裁剪)")
    print("=" * 60)

    page_num = TEST_PAGE_INDEX + 1  # 转为1-based
    print(f"\n测试页码: 第 {page_num} 页\n")

    # Step 1: 渲染 PDF 页面
    print("-" * 40)
    print("Step 1: 渲染 PDF 页面")
    print("-" * 40)
    page_image_path = render_pdf_page(
        PDF_PATH, TEST_PAGE_INDEX, PAGES_DIR, DPI_SCALE
    )

    # Step 2: 页面预处理
    print("\n" + "-" * 40)
    print("Step 2: 页面预处理")
    print("-" * 40)
    preprocessed_path = os.path.join(PAGES_DIR, f"page_{page_num:03d}_processed.png")
    gray = preprocess_page(page_image_path, preprocessed_path, remove_lines=False)

    # 加载原始图片用于OCR
    original_gray = cv2.imread(page_image_path, cv2.IMREAD_GRAYSCALE)

    # Step 3: 单字切割
    print("\n" + "-" * 40)
    print("Step 3: 单字切割")
    print("-" * 40)
    config = {
        "min_chars_per_col": 2,
        "min_char_width": 100,
        "min_char_height": 100,
        "size_threshold": 120,
        "binary_threshold": 140,
        "bbox_padding": 5,
        "clean_min_ratio": 0.05,
    }
    characters = segment_characters(original_gray, config)

    if not characters:
        print("\n[警告] 未检测到任何字符！可能需要调整参数。")
        return

    # Step 4: 保存字符图片
    print("\n" + "-" * 40)
    print("Step 4: 保存字符图片")
    print("-" * 40)
    char_output_dir = os.path.join(CHARACTERS_DIR, f"page_{page_num:03d}")
    saved_paths = save_characters(characters, char_output_dir, page_num)
    print(f"已保存 {len(saved_paths)} 个字符图片到: {char_output_dir}")

    # Step 5: 绘制边界框可视化
    print("\n" + "-" * 40)
    print("Step 5: 生成可视化结果")
    print("-" * 40)

    # 加载原始渲染图片用于绘制边界框
    original = cv2.imread(page_image_path, cv2.IMREAD_GRAYSCALE)
    vis_path = os.path.join(PAGES_DIR, f"page_{page_num:03d}_boxes.png")

    # 获取列信息用于可视化（只显示书法列）
    # 先裁剪到主内容区域
    content_x_min, content_y_min, content_x_max, content_y_max = detect_main_content_bbox(original_gray)
    gray_cropped = original_gray[content_y_min:content_y_max, content_x_min:content_x_max]
    
    all_chars = get_ocr_char_boxes(gray_cropped)
    # 转换回原图坐标
    all_chars = [(
        c[0] + content_x_min, c[1] + content_x_min,
        c[2] + content_y_min, c[3] + content_y_min,
        c[4], c[5], c[6], c[7]
    ) for c in all_chars]
    
    # 过滤标点
    punctuation = set('（）()[]【】{}《》<>""\'\'.,;:!?、。！？；：，．')
    all_chars = [c for c in all_chars if c[4] not in punctuation and len(c[4].strip()) > 0]
    
    columns_info = classify_columns(all_chars)
    split_cols = split_mixed_columns(columns_info, size_threshold=120)
    calligraphy_cols = filter_calligraphy_columns(split_cols, min_chars=2, min_char_width=100, min_char_height=100)
    columns = [(c[1], c[2]) for c in calligraphy_cols]

    draw_character_boxes(original, characters, columns, vis_path)

    # 打印字符统计信息
    print("\n" + "-" * 40)
    print("字符统计信息")
    print("-" * 40)
    areas = [c[5] for c in characters]
    widths = [c[2] for c in characters]
    heights = [c[3] for c in characters]

    print(f"字符总数: {len(characters)}")
    print(f"面积范围: {min(areas)} ~ {max(areas)} (平均: {sum(areas) / len(areas):.0f})")
    print(f"宽度范围: {min(widths)} ~ {max(widths)} (平均: {sum(widths) / len(widths):.0f})")
    print(f"高度范围: {min(heights)} ~ {max(heights)} (平均: {sum(heights) / len(heights):.0f})")

    # 按列统计
    columns_dict = {}
    for c in characters:
        col_idx = c[6]
        if col_idx not in columns_dict:
            columns_dict[col_idx] = []
        columns_dict[col_idx].append(c)

    print(f"\n列分布:")
    for col_idx in sorted(columns_dict.keys()):
        col_chars = columns_dict[col_idx]
        x_range = (min(c[0] for c in col_chars), max(c[0]+c[2] for c in col_chars))
        texts = [c[8] for c in col_chars]
        print(f"  列 {col_idx + 1}: x={x_range[0]}-{x_range[1]}, {len(col_chars)} 个字符")
        print(f"    文字: {' '.join(texts)}")

    print("\n" + "=" * 60)
    print("测试完成！")
    print(f"输出文件:")
    print(f"  - 渲染图片: {page_image_path}")
    print(f"  - 预处理图片: {preprocessed_path}")
    print(f"  - 边界框可视化: {vis_path}")
    print(f"  - 单字图片目录: {char_output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
