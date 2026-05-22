import cv2, json
for name in ['page_024_processed.png', 'page_024.png']:
    img = cv2.imread('output/pages/' + name)
    if img is not None:
        h, w = img.shape[:2]
        print(f'{name}: {w}x{h}')

with open('output/pages/page_024_corrected.json', encoding='utf-8') as f:
    data = json.load(f)
print('First 3:')
for d in data[:3]:
    t = d.get('corrected_text', d.get('text', ''))
    print(f'  col={d["col"]} row={d["row"]} text={t} x={d["x"]} y={d["y"]} w={d["w"]} h={d["h"]}')
