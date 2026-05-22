import json
with open('output/pages/page_024_corrected.json', encoding='utf-8') as f:
    data = json.load(f)
for d in data[:8]:
    print(f'x={d["x"]:4d} y={d["y"]:4d} w={d["w"]:3d} h={d["h"]:3d}')
print('---')
# Check column x ranges
cols = {}
for d in data:
    cols.setdefault(d['col'], []).append(d['x'])
for c in sorted(cols):
    xs = cols[c]
    print(f'  col {c}: x range {min(xs)}-{max(xs)}')
