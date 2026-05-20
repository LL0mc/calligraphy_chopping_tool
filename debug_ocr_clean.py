"""Clean visualization of OCR character boxes, grouped by line"""
import cv2
import numpy as np
import sys
sys.path.append('src')

def visualize_ocr_clean(page=184):
    img_path = f'output/pages/page_{page:03d}.png'
    gray = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    h, w = gray.shape
    
    from rapidocr import RapidOCR
    ocr = RapidOCR()
    result = ocr(gray, return_word_box=True)
    
    # Create visualization
    vis = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    
    # Colors for different lines
    line_colors = [
        (0, 255, 0),    # Green
        (255, 0, 0),    # Blue
        (0, 0, 255),    # Red
        (255, 255, 0),  # Cyan
        (255, 0, 255),  # Magenta
        (0, 255, 255),  # Yellow
        (128, 128, 255),
        (128, 255, 128),
        (255, 128, 128),
        (200, 200, 200),
    ]
    
    word_results = result.word_results
    print(f"Total lines: {len(word_results)}")
    
    total_chars = 0
    for line_idx, line_chars in enumerate(word_results):
        if not line_chars:
            continue
            
        color = line_colors[line_idx % len(line_colors)]
        
        # Draw line-level box (lighter)
        line_box = result.boxes[line_idx]
        pts = np.array([[int(p[0]), int(p[1])] for p in line_box], dtype=np.int32)
        cv2.polylines(vis, [pts], True, (100, 100, 100), 1)  # Gray for line box
        
        # Draw each character box
        for char_idx, (text, score, box) in enumerate(line_chars):
            pts = np.array([[int(p[0]), int(p[1])] for p in box], dtype=np.int32)
            cv2.polylines(vis, [pts], True, color, 2)
            
            # Label with text and score
            cx = int(np.mean([p[0] for p in box]))
            cy = int(np.mean([p[1] for p in box]))
            label = f"{text}"
            cv2.putText(vis, label, (cx - 10, cy + 5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            
            total_chars += 1
    
    print(f"Total characters: {total_chars}")
    
    out_path = f'output/pages/page_{page:03d}_ocr_clean.png'
    cv2.imwrite(out_path, vis)
    print(f"Saved: {out_path}")
    
    # Also create a version with just the main calligraphy characters (large ones)
    vis_main = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    main_count = 0
    
    for line_idx, line_chars in enumerate(word_results):
        if not line_chars:
            continue
        
        color = line_colors[line_idx % len(line_colors)]
        
        for char_idx, (text, score, box) in enumerate(line_chars):
            # Calculate box size
            x_coords = [p[0] for p in box]
            y_coords = [p[1] for p in box]
            bw = max(x_coords) - min(x_coords)
            bh = max(y_coords) - min(y_coords)
            
            # Only show large characters (> 80px in both dimensions)
            if bw > 80 and bh > 80:
                pts = np.array([[int(p[0]), int(p[1])] for p in box], dtype=np.int32)
                cv2.polylines(vis_main, [pts], True, color, 2)
                
                cx = int(np.mean([p[0] for p in box]))
                cy = int(np.mean([p[1] for p in box]))
                label = f"{text}"
                cv2.putText(vis_main, label, (cx - 10, cy + 5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                
                main_count += 1
    
    print(f"Main characters (>80px): {main_count}")
    
    out_path_main = f'output/pages/page_{page:03d}_ocr_main_chars.png'
    cv2.imwrite(out_path_main, vis_main)
    print(f"Saved: {out_path_main}")

if __name__ == '__main__':
    visualize_ocr_clean()
