import urllib.request, urllib.error
try:
    req = urllib.request.Request('http://127.0.0.1:5000/?page=24')
    r = urllib.request.urlopen(req, timeout=10)
    print(f'Status: {r.status}')
    body = r.read()
    print(f'Length: {len(body)}')
    checks = [b'charTable', b'pageImage', b'editPanel']
    for c in checks:
        print(f'Contains {c.decode()}: {c in body}')
except urllib.error.HTTPError as e:
    print(f'HTTP Error: {e.code}')
    body = e.read().decode('utf-8', errors='replace')
    print(body[:2000])
except Exception as e:
    print(f'Error: {e}')
