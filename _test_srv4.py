import urllib.request
r = urllib.request.urlopen('http://127.0.0.1:5000/?p=24', timeout=10)
body = r.read().decode('utf-8')
print(f'Len: {len(body)}')
print(f'Has data:image/png: {"data:image/png" in body}')
print(f'Has SCALE var: {"SCALE" in body}')
# check a few chars near the start
idx = body.find('var bx =')
if idx >= 0:
    snippet = body[idx:idx+300]
    print(f'bx snippet: {snippet[:200]}')
