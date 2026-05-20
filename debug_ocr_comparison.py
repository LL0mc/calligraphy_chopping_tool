"""Compare OCR results: cropped vs full image"""
import cv2
import numpy as np
import sys
sys.path.append('src')

def compare_ocr_sources(page=184):
    img_path = f'output/pages/page_{page:03d}.png'
    gray = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    h, w = gray.shape
    
    from rapidocr import RapidOCR
    ocr = RapidOCR()
    
    # Source 1: Full image OCR
    result_full = ocr(gray, return_word_box=True)
    
    # Source 2: Cropped image OCR
    from char_segmenter import detect_main_content_bbox
    cx_min, cy_min, cx_max, cy_max = detect_main_content_bbox(gray)
    gray_cropped = gray[cy_min:cy_max, cx_min:cx_max]
    result_cropped = ocr(gray_cropped, return_word_box=True)
    
    print(f"Full image: {len(result_full.word_results)} lines")
    print(f"Cropped image: {len(result_cropped.word_results)} lines")
    print(f"Crop offset: x={cx_min}, y={cy_min}")
    
    # Create comparison visualization
    vis = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    
    # Draw full image results in GREEN
    for line_idx, line_chars in enumerate(result_full.word_results):
        if not line_chars:
            continue
        for char_idx, (text, score, box) in enumerate(line_chars):
            pts = np.array([[int(p[0]), int(p[1])] for p in box], dtype=np.int32)
            cv2.polylines(vis, [pts], True, (0, 255, 0), 1)  # Green, thin
    
    # Draw cropped results (shifted back) in RED
    for line_idx, line_chars in enumerate(result_cropped.word_results):
        if not line_chars:
            continue
        for char_idx, (text, score, box) in enumerate(line_chars):
            # Shift coordinates back to full image
            shifted_box = [[p[0] + cx_min, p[1] + cy_min] for p in box]
            pts = np.array([[int(p[0]), int(p[1])] for p in shifted_box], dtype=np.int32)
            cv2.polylines(vis, [pts], True, (0, 0, 255), 1)  # Red, thin
    
    out_path = f'output/pages/page_{page:03d}_ocr_comparison.png'
    cv2.imwrite(out_path, vis)
    print(f"Saved: {out_path}")
    print("Green = full image OCR, Red = cropped+shifted OCR")
    
    # Count differences
    full_chars = []
    for line_chars in result_full.word_results:
        if line_chars:
            for text, score, box in line_chars:
                x_coords = [p[0] for p in box]
                y_coords = [p[1] for p in box]
                full_chars.append((min(x_coords), max(x_coords), min(y_coords), max(y_coords), text))
    
    cropped_chars = []
    for line_chars in result_cropped.word_results:
        if line_chars:
            for text, score, box in line_chars:
                x_coords = [p[0] + cx_min for p in box]
                y_coords = [p[1] + cy_min for p in box]
                cropped_chars.append((min(x_coords), max(x_coords), min(y_coords), max(y_coords), text))
    
    print(f"\nFull image chars: {len(full_chars)}")
    print(f"Cropped+shifted chars: {len(cropped_chars)}")
    
    # Show first 5 of each
    print("\nFirst 5 full image chars:")
    for c in full_chars[:5]:
        print(f"  ({c[0]}, {c[1]}, {c[2]}, {c[3]}) '{c[4]}'")
    
    print("\nFirst 5 cropped+shifted chars:")
    for c in cropped_chars[:5]:
        print(f"  ({c[0]}, {c[1]}, {c[2]}, {c[3]}) '{c[4]}'")

if __name__ == '__main__':
    compare_ocr_sources()
