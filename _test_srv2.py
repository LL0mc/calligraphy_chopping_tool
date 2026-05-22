import sys; sys.path.insert(0, '.')
from review_server import app
with app.test_client() as c:
    resp = c.get('/?p=24')
    print(f'Status: {resp.status_code}')
    print(resp.get_data(as_text=True)[:2000])
