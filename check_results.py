import json

with open('output/pages/page_091_ocr_results_v5.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

col3 = [r for r in data if r['col'] == 3]
print('Page 91 Col 3:')
for r in col3:
    print(f"  Row {r['row']}: {r['text']}")

with open('output/pages/page_184_ocr_results_v5.json', 'r', encoding='utf-8') as f:
    data184 = json.load(f)

col1_184 = [r for r in data184 if r['col'] == 1]
print('\nPage 184 Col 1 last char:')
print(col1_184[-1] if col1_184 else 'None')

col5_184 = [r for r in data184 if r['col'] == 5]
print('\nPage 184 Col 5 last chars:')
for r in col5_184[-5:]:
    print(f"  Row {r['row']}: {r['text']}")

with open('output/pages/page_027_ocr_results_v5.json', 'r', encoding='utf-8') as f:
    data27 = json.load(f)

col1_27 = [r for r in data27 if r['col'] == 1]
print('\nPage 27 Col 1 last char:')
print(col1_27[-1] if col1_27 else 'None')

with open('output/pages/page_049_ocr_results_v5.json', 'r', encoding='utf-8') as f:
    data49 = json.load(f)

col2_49 = [r for r in data49 if r['col'] == 2]
print('\nPage 49 Col 2 Row 1 (欲):')
print(col2_49[0] if col2_49 else 'None')
