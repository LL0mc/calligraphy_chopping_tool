import json
with open('output/pages/page_024_corrected.json', encoding='utf-8') as f:
    data = json.load(f)
# Check if any box is unusually wide (>2x median)
import statistics
widths = [d['w'] for d in data if d.get('corrected_text', d.get('text', '')).strip()]
median_w = statistics.median(widths)
print(f'Median width: {median_w}')
for d in data:
    w = d['w']
    if w > median_w * 1.8:
        t = d.get('corrected_text', d.get('text', ''))
        print(f'WIDE: col={d["col"]} row={d["row"]} text={t} w={w} h={d["h"]}')
