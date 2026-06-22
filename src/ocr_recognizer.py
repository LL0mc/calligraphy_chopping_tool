"""OCR识别模块：对单字进行识别并返回置信度"""
import cv2
import numpy as np
from typing import List, Tuple
from src.types import OcrResult, CharBox

# 全局OCR实例，避免重复加载
_rapidocr_instance = None

def get_rapidocr():
    global _rapidocr_instance
    if _rapidocr_instance is None:
        from rapidocr import RapidOCR
        try:
            from rapidocr.utils.typings import OCRVersion, LangRec
            _rapidocr_instance = RapidOCR(params={
                'Rec.ocr_version': OCRVersion.PPOCRV5,
                'Rec.lang_type': LangRec.CH,
            })
        except Exception:
            _rapidocr_instance = RapidOCR()
    return _rapidocr_instance


def expand_box(gray: np.ndarray, x: int, y: int, w: int, h: int,
               strategy: str = "square", padding: int = 10) -> Tuple[int, int, int, int]:
    """扩展字符框，提高OCR识别准确率"""
    img_h, img_w = gray.shape[:2]
    
    if strategy == "none":
        return (x, y, w, h)
    
    if strategy == "fixed":
        new_x = max(0, x - padding)
        new_y = max(0, y - padding)
        new_w = min(img_w - new_x, w + padding * 2)
        new_h = min(img_h - new_y, h + padding * 2)
        return (new_x, new_y, new_w, new_h)
    
    if strategy == "square":
        size = max(w, h) + padding * 2
        new_x = max(0, x + w // 2 - size // 2)
        new_y = max(0, y + h // 2 - size // 2)
        new_w = min(img_w - new_x, size)
        new_h = min(img_h - new_y, size)
        return (new_x, new_y, new_w, new_h)
    
    return (x, y, w, h)


def recognize_single_char(char_img: np.ndarray) -> Tuple[str, float]:
    """使用rapidocr识别单个字符
    
    Returns:
        (识别文字, 置信度)
    """
    try:
        ocr = get_rapidocr()
        
        # 确保是灰度图
        if len(char_img.shape) == 3:
            char_img = cv2.cvtColor(char_img, cv2.COLOR_BGR2GRAY)
        
        # 尝试原图识别
        result = ocr(char_img)
        if result and result.txts:
            text = result.txts[0]
            score = result.scores[0]
            # 只取第一个字符
            if len(text) > 1:
                text = text[0]
            return (text, score)
        
        # 如果失败，尝试反色
        inverted = 255 - char_img
        result = ocr(inverted)
        if result and result.txts:
            text = result.txts[0]
            score = result.scores[0]
            if len(text) > 1:
                text = text[0]
            return (text, score)
            
    except Exception as e:
        print(f"[OCR] 识别失败: {e}")
    
    return ('', 0.0)


def recognize_characters(gray: np.ndarray, characters: list,
                         engine: str = "rapidocr",
                         expand_strategy: str = "square",
                         expand_padding: int = 15) -> list:
    """对切割出的字符进行OCR识别"""
    results = []
    
    for idx, char in enumerate(characters):
        x, y, w, h = char.x, char.y, char.w, char.h

        # If original text from OCR is available and high-confidence, use it directly
        if char.text and len(str(char.text).strip()) > 0 and char.score >= 0.6:
            text = char.text
            score = char.score
        else:
            # Re-OCR: expand box and recognize
            ex, ey, ew, eh = expand_box(gray, x, y, w, h, 
                                         strategy=expand_strategy, 
                                         padding=expand_padding)
            
            # 裁剪扩展后的图像
            char_img = gray[ey:ey+eh, ex:ex+ew]
            
            # 识别
            text, score = recognize_single_char(char_img)
            
            # 如果识别为空，尝试不扩展
            if not text and expand_strategy != "none":
                orig_img = gray[y:y+h, x:x+w]
                text, score = recognize_single_char(orig_img)
        
        results.append(OcrResult(
            x=x, y=y, w=w, h=h,
            col_idx=char.col_idx, row_idx=char.row_idx,
            original_text=char.text, original_score=char.score,
            ocr_text=text, ocr_score=score,
            expand_strategy=expand_strategy,
        ))
        
        if (idx + 1) % 10 == 0:
            print(f"[OCR] 已识别 {idx + 1}/{len(characters)} 个字符")
    
    print(f"[OCR] 识别完成: {len(results)} 个字符")
    return results
