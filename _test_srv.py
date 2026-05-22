import urllib.request
r = urllib.request.urlopen('http://127.0.0.1:5000/?p=24', timeout=10)
print(f'Status: {r.status}')
body = r.read().decode('utf-8')
print(f'Length: {len(body)}')
checks = ['charTable', 'canvasOverlay', '保存', '拖拽', '选中']
for c in checks:
    print(f'  {c}: {"YES" if c in body else "NO"}')
print(f'Chinese: {"此" in body}')
