"""Verify corrected OCR output"""
import json
with open('output/pages/page_024_ocr_results_corrected.json', encoding='utf-8') as f:
    data = json.load(f)
cols = {}
for d in data:
    col = d['col']
    if col not in cols:
        cols[col] = []
    t = d.get('corrected_text', d['text'])
    cols[col].append((d['row'], t))
for col in sorted(cols.keys()):
    items = sorted(cols[col])
    line = ' '.join(f'{r}:{t}' for r, t in items)
    print(f'Col {col}: {line}')
