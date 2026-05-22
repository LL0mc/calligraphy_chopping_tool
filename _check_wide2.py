import json
with open('output/pages/page_024_ocr_results.json', encoding='utf-8') as f:
    data = json.load(f)
for d in data:
    if d['col'] == 1 and d['row'] == 6:
        print(f'OCR: x={d["x"]} y={d["y"]} w={d["w"]} h={d["h"]} text={d["text"]}')
    if d['col'] == 1 and d['row'] in (4,5,7):
        print(f'OCR col=1 row={d["row"]}: x={d["x"]} y={d["y"]} w={d["w"]} h={d["h"]} text={d["text"]}')
