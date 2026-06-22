"""Deprecated utilities moved from char_segmenter.py (kept for reference)."""
import os
import cv2
import numpy as np
from src.types import CharBox, OcrResult


def save_characters(characters: list[CharBox], output_dir: str, page_num: int, pad_size: int = 10) -> list:
    os.makedirs(output_dir, exist_ok=True)
    saved_paths = []

    for char in characters:
        char_size = max(char.w, char.h) + pad_size * 2
        bg = np.full((char_size, char_size), 255, dtype=np.uint8)

        offset_x = (char_size - char.w) // 2
        offset_y = (char_size - char.h) // 2
        bg[offset_y:offset_y + char.h, offset_x:offset_x + char.w] = char.img

        filename = f"page{page_num:03d}_col{char.col_idx+1:02d}_row{char.row_idx+1:02d}.png"
        filepath = os.path.join(output_dir, filename)
        cv2.imwrite(filepath, bg)
        saved_paths.append(filepath)

    return saved_paths


def draw_character_boxes(original_image: np.ndarray, characters: list[CharBox],
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
        col_idx = char.col_idx
        if col_idx not in col_dict:
            col_dict[col_idx] = []
        col_dict[col_idx].append(char)

    for col_idx, col_chars in col_dict.items():
        color = colors[col_idx % len(colors)]
        for char in col_chars:
            cv2.rectangle(color_img, (char.x, char.y), (char.x + char.w, char.y + char.h), color, 2)
            label = f"{char.score:.2f}"
            cv2.putText(color_img, label, (char.x, char.y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

    if output_path:
        cv2.imwrite(output_path, color_img)
        print(f"[可视化] 保存边界框图: {output_path}")

    return color_img


def draw_ocr_results(original_image: np.ndarray, ocr_results: list,
                     columns: list = None, output_path: str = None,
                     high_conf_threshold: float = 0.8,
                     low_conf_threshold: float = 0.5) -> np.ndarray:
    """绘制OCR识别结果，不同置信度用不同颜色"""
    color_img = cv2.cvtColor(original_image, cv2.COLOR_GRAY2BGR)

    if columns:
        for col_start, col_end in columns:
            cv2.line(color_img, (col_start, 0), (col_start, original_image.shape[0]), (128, 128, 128), 1)

    from PIL import Image, ImageDraw, ImageFont

    for result in ocr_results:
        x, y, w, h = result.x, result.y, result.w, result.h
        text = result.ocr_text
        score = result.ocr_score

        if score >= high_conf_threshold:
            color = (0, 255, 0)
        elif score >= low_conf_threshold:
            color = (0, 255, 255)
        else:
            color = (0, 0, 255)

        if not text:
            color = (0, 0, 128)

        cv2.rectangle(color_img, (x, y), (x + w, y + h), color, 2)

        # 转PIL绘制中文
        pil_img = Image.fromarray(cv2.cvtColor(color_img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)

        try:
            font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 18)
        except:
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/simsun.ttc", 18)
            except:
                font = ImageFont.load_default()

        if text:
            label = f"{text} {score:.2f}"
            draw.text((x, y - 22), label, fill=(color[2], color[1], color[0]), font=font)
        else:
            label = f"? {score:.2f}"
            draw.text((x, y - 22), label, fill=(color[2], color[1], color[0]), font=font)

        color_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    if output_path:
        cv2.imwrite(output_path, color_img)
        print(f"[可视化] 保存OCR结果图: {output_path}")

    return color_img
