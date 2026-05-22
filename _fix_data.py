"""Restore original coords from OCR results into corrected JSON"""
import json, sys, os
sys.path.insert(0, '.')
from src.corrector import load_poems, correct_page_ocr

pages_dir = 'output/pages'
page = 24

ocr_path = os.path.join(pages_dir, f'page_{page:03d}_ocr_results.json')

# Load poems and run correction (function expects file path)
poems = load_poems()
corrected, corrections = correct_page_ocr(ocr_path, poems, page)

# Save
out_path = os.path.join(pages_dir, f'page_{page:03d}_corrected.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(corrected, f, ensure_ascii=False, indent=2)

# Verify row 6
for d in corrected:
    if d['col'] == 1 and d['row'] == 6:
        print(f'Row 6 restored: x={d["x"]} y={d["y"]} w={d["w"]} h={d["h"]} text={d.get("corrected_text", d["text"])}')
print(f'Saved {len(corrected)} chars to {out_path}')
print(f'Corrections: {len(corrections)}')
