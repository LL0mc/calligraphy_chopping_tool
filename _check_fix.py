import urllib.request, json
r = urllib.request.urlopen('http://127.0.0.1:5000/?p=24')
body = r.read().decode('utf-8')
# extract bx variable
import re
m = re.search(r'var bx = (\[.*?\]);', body, re.DOTALL)
if m:
    bx = json.loads(m.group(1))
    for b in bx:
        if b['idx'] in (5, 6):
            print(f'  idx={b["idx"]}: col={b["col"]} row={b["row"]} text={b["text"]} x={b["x"]} y={b["y"]} w={b["w"]} h={b["h"]}')
