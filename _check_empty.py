import json
with open('output/pages/page_024_corrected.json', encoding='utf-8') as f:
    data = json.load(f)
print(f'Total: {len(data)}')
for i, d in enumerate(data):
    text = d.get('corrected_text', d.get('text', ''))
    if not text.strip():
        print(f'  #{i+1}: col={d["col"]} row={d["row"]} text=EMPTY x={d["x"]} y={d["y"]} w={d["w"]} h={d["h"]}')
