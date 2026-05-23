"""OCR识别模块：对单字进行识别并返回置信度"""
import cv2
import numpy as np
from typing import List, Tuple

# 全局OCR实例，避免重复加载
_rapidocr_instance = None

def get_rapidocr():
    global _rapidocr_instance
    if _rapidocr_instance is None:
        from rapidocr import RapidOCR
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
        x, y, w, h = char[0], char[1], char[2], char[3]
        
        # If original text from OCR is available and high-confidence, use it directly
        if char[8] and len(str(char[8]).strip()) > 0 and char[9] >= 0.6:
            text = char[8]
            score = char[9]
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
        
        results.append({
            'x': x, 'y': y, 'w': w, 'h': h,
            'col_idx': char[6], 'row_idx': char[7],
            'original_text': char[8], 'original_score': char[9],
            'ocr_text': text, 'ocr_score': score,
            'expand_strategy': expand_strategy
        })
        
        if (idx + 1) % 10 == 0:
            print(f"[OCR] 已识别 {idx + 1}/{len(characters)} 个字符")
    
    print(f"[OCR] 识别完成: {len(results)} 个字符")
    return results


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
        x, y, w, h = result['x'], result['y'], result['w'], result['h']
        text = result['ocr_text']
        score = result['ocr_score']
        
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
