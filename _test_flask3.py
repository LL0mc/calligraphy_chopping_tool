import sys; sys.path.insert(0, '.')
from annotate_flask import app
with app.test_client() as c:
    resp = c.get('/?page=24')
    print(f'Status: {resp.status_code}')
    if resp.status_code == 200:
        html = resp.get_data(as_text=True)
        print(f'Length: {len(html)}')
        checks = ['charTable', 'pageImage', 'selLabel', 'editPanel', 'canvasOverlay']
        for ch in checks:
            found = ch in html
            print(f'  {ch}: {"YES" if found else "NO"}')
        if '此' in html or '枉' in html:
            print('Chinese chars: OK')
        elif '\ufffd' in html:
            print('Chinese chars: MOJIBAKE')
        else:
            print('Chinese chars: check snippet:')
            print(html[2000:2500])
    else:
        print(resp.get_data(as_text=True)[:1000])
