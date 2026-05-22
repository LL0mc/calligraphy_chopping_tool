import json
# Check corrected JSON for row 6
with open('output/pages/page_024_corrected.json', encoding='utf-8') as f:
    data = json.load(f)
for d in data:
    if d['col'] == 1 and d['row'] in (5,6,7):
        print(f'Corrected col=1 row={d["row"]}: x={d["x"]} y={d["y"]} w={d["w"]} h={d["h"]} ocr={d["text"]} corrected={d.get("corrected_text","")}')
