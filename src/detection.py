"""OCR detection module: content bbox detection and OCR character box extraction."""
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

    if content_start is None or content_end is None or content_top is None or content_bottom is None:
        return (0, 0, w, h)

    margin = 20
    return (
        max(0, content_start - margin),
        max(0, content_top - margin),
        min(w, content_end + margin),
        min(h, content_bottom + margin)
    )


def get_ocr_char_boxes(gray: np.ndarray) -> list:
    """获取OCR检测到的字符框（按行分组，返回单字级别）"""
    try:
        from rapidocr import RapidOCR
        try:
            from rapidocr.utils.typings import OCRVersion, LangRec, LangDet
            ocr = RapidOCR(params={
                'Det.ocr_version': OCRVersion.PPOCRV5,
                'Det.lang_type': LangDet.CH,
                'Rec.ocr_version': OCRVersion.PPOCRV5,
                'Rec.lang_type': LangRec.CH,
            })
        except Exception:
            ocr = RapidOCR()
        result = ocr(gray, return_word_box=True)

        all_chars = []
        for line_idx, line_chars in enumerate(result.word_results):
            if not line_chars:
                continue
            for char_idx, item in enumerate(line_chars):
                if isinstance(item, tuple) and len(item) == 3:
                    char_text, char_score, char_box = item
                    x_coords = [p[0] for p in char_box]
                    y_coords = [p[1] for p in char_box]
                    x_min = int(min(x_coords))
                    x_max = int(max(x_coords))
                    y_min = int(min(y_coords))
                    y_max = int(max(y_coords))
                    all_chars.append((x_min, x_max, y_min, y_max, char_text, char_score, line_idx, char_idx))
        return all_chars
    except Exception as e:
        print(f"[OCR] 获取单字框失败: {e}")
        return []
