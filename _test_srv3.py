import urllib.request
r = urllib.request.urlopen('http://127.0.0.1:5000/?p=24', timeout=10)
print(f'Status: {r.status}')
body = r.read().decode('utf-8')
print(f'Len: {len(body)}')
checks = ['此', 'id="cv"', 'delChar', '拖拽', '保存', '删除', 'data:image/jpeg']
for c in checks:
    print(f'  {c}: {"YES" if c in body else "NO"}')
