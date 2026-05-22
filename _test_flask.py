import sys
sys.path.insert(0, '.')
from annotate_flask import app
with app.test_client() as c:
    resp = c.get('/?page=24')
    print(f'Status: {resp.status_code}')
    if resp.status_code == 200:
        html = resp.get_data(as_text=True)
        print(f'OK: {len(html)} bytes')
        for ch in ['charTable', 'pageImage', 'editPanel', 'selectChar']:
            print(f'  {ch}: {"YES" if ch in html else "NO"}')
    else:
        print(resp.get_data(as_text=True)[:500])
