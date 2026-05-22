"""Show page status"""
import sys, json
sys.stdout.reconfigure(encoding='utf-8')
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

with open('output/pages/page_024_corrected.json', encoding='utf-8') as f:
    data = json.load(f)

cols = {}
for d in data:
    col = d['col']
    t = d.get('corrected_text', d.get('text', ''))
    auto = d.get('auto_corrected', False)
    orig = d.get('text', '')
    cols.setdefault(col, []).append((d['row'], t, orig, auto))

for col in sorted(cols.keys()):
    items = sorted(cols[col])
    print(f'--- Column {col} ---')
    for r, t, orig, auto in items:
        flag = 'A' if auto else ('?' if (len(t)==0 or (len(t)==1 and ord(t)<128)) else ' ')
        print(f'  Row {r:2d}: {t} (OCR:{orig}) [{flag}]')
    print()
