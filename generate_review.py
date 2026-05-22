"""生成离线校对 HTML：浏览器直接打开，编辑结果存 localStorage → 导出 JSON"""
import sys, os, json, cv2, numpy as np, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import PAGES_DIR

def load_data(page_num):
    for suffix in ['_corrected.json', '_ocr_results.json']:
        p = os.path.join(PAGES_DIR, f"page_{page_num:03d}{suffix}")
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                return json.load(f)
    return None

def load_img(page_num):
    for name in [f"page_{page_num:03d}_processed.png", f"page_{page_num:03d}.png"]:
        p = os.path.join(PAGES_DIR, name)
        if os.path.exists(p):
            img = cv2.imread(p)
            if img is not None:
                return img
    return None

def annotate_image(data, page_img, page_num):
    img = page_img.copy()
    h, w = img.shape[:2]
    scale = min(1600/h, 1600/w, 1.0)
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale)
    boxes = []
    for i, d in enumerate(data):
        x = int(d['x'] * scale); y = int(d['y'] * scale)
        bw = int(d['w'] * scale); bh = int(d['h'] * scale)
        text = d.get('corrected_text', d.get('text', ''))
        if d.get('manual_corrected'):
            color = (0, 200, 255); thick = 2
        elif d.get('auto_corrected'):
            color = (255, 200, 0); thick = 2
        else:
            color = (150, 150, 150); thick = 1
        cv2.rectangle(img, (x, y), (x+bw, y+bh), color, thick)
        cv2.putText(img, f"{i+1}:{text}", (x+2, y+14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
        boxes.append({
            'idx': i, 'col': d['col'], 'row': d['row'],
            'text': text, 'ocr': d.get('text',''),
            'auto': d.get('auto_corrected', False),
            'manual': d.get('manual_corrected', False),
            'x': d['x'], 'y': d['y'], 'w': d['w'], 'h': d['h'],
            'orig_x': d['x'], 'orig_y': d['y'], 'orig_w': d['w'], 'orig_h': d['h'],
        })
    _, buf = cv2.imencode('.png', img)
    b64 = base64.b64encode(buf).decode()
    return b64, boxes

def generate_html(page_num):
    data = load_data(page_num)
    img = load_img(page_num)
    if data is None or img is None:
        print(f"Page {page_num} not found")
        return None
    img_b64, boxes = annotate_image(data, img, page_num)
    boxes_json = json.dumps(boxes, ensure_ascii=False)
    html = HTML_TEMPLATE.format(page=page_num, img_b64=img_b64,
                                boxes_json=boxes_json, total=len(data))
    out_path = os.path.join(PAGES_DIR, f"page_{page_num:03d}_review.html")
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"已生成: {out_path}")
    return out_path

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh">
<head><meta charset="utf-8">
<title>字帖校对 - 第{page}页</title>
<style>
* {{margin:0;padding:0;box-sizing:border-box;}}
body {{font-family:'Microsoft YaHei',sans-serif;background:#1a1a2e;color:#eee;padding:16px;}}
h2 {{margin-bottom:12px;color:#f0f0f0;}}
.toolbar {{display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap;}}
.toolbar button,.toolbar input {{padding:6px 12px;border-radius:4px;border:none;background:#0f3460;color:#fff;cursor:pointer;}}
.toolbar button:hover {{background:#16213e;}}
.container {{display:flex;gap:16px;}}
.left {{flex:3;}}
.left img {{width:100%;border-radius:8px;box-shadow:0 4px 20px rgba(0,0,0,0.5);}}
.right {{flex:2;display:flex;flex-direction:column;gap:8px;}}
#filterInput {{width:100%;padding:6px;background:#1a1a2e;color:#fff;border:1px solid #333;border-radius:4px;}}
.table-wrap {{overflow-y:auto;max-height:60vh;}}
table {{width:100%;border-collapse:collapse;font-size:13px;}}
th {{background:#0f3460;padding:6px;text-align:left;position:sticky;top:0;}}
td {{padding:4px 6px;border-bottom:1px solid #333;cursor:pointer;}}
tr:hover {{background:#16213e;}}
tr.sel {{background:#1a5276;}}
.s-ok {{color:#7dcea0;}} .s-auto {{color:#f9e79f;}} .s-man {{color:#85c1e9;}}
.edit-panel {{background:#16213e;padding:16px;border-radius:8px;}}
.edit-panel label {{display:inline-block;width:30px;color:#aaa;font-size:13px;}}
.edit-panel input {{background:#1a1a2e;color:#fff;border:1px solid #333;padding:4px 8px;border-radius:4px;margin:2px;}}
.edit-panel .w80 {{width:80px;}}
.btn {{padding:6px 16px;border-radius:4px;border:none;cursor:pointer;color:#fff;}}
.btn-sv {{background:#27ae60;}} .btn-sv:hover {{background:#2ecc71;}}
.btn-nv {{background:#2980b9;}} .btn-nv:hover {{background:#3498db;}}
.btn-adj {{background:#7f8c8d;padding:3px 8px;font-size:12px;}}
#charImg {{max-width:100px;max-height:100px;border:1px solid #555;border-radius:4px;vertical-align:middle;}}
.msg {{padding:4px 8px;border-radius:4px;margin-top:4px;display:inline-block;}}
.msg.ok {{background:#1a5276;color:#7dcea0;}}
.summary {{color:#888;font-size:13px;margin-bottom:8px;}}
</style></head>
<body>
<h2>📜 第{page}页 · {total}字</h2>
<div class="toolbar">
  <span>页码:</span><input type="number" id="pageInput" value="{page}" min="1" style="width:60px">
  <button onclick="loadPage()">📂 加载</button>
  <button onclick="exportJSON()">📥 导出修改</button>
  <button onclick="clearAll()">🗑️ 清除待导出</button>
  <span id="statusMsg"></span>
</div>
<div class="container">
  <div class="left">
    <img id="pageImage" src="data:image/png;base64,{img_b64}" alt="page">
  </div>
  <div class="right">
    <input id="filterInput" placeholder="筛选..." oninput="filterTable()">
    <div class="table-wrap">
    <table id="charTable">
      <thead><tr><th>#</th><th>列</th><th>行</th><th>文字</th><th>OCR</th><th>X</th><th>Y</th></tr></thead>
      <tbody id="tableBody"></tbody>
    </table>
    </div>
    <div class="edit-panel" id="editPanel">
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
        <img id="charImg" src="" alt="裁剪图">
        <div>
          <div><label>字</label><input id="editText" class="w80">
          <span style="color:#888;margin-left:8px;">OCR: <span id="editOcr">-</span></span></div>
          <div style="margin-top:4px;">
            <span class="coord"><label>X</label><input id="editX" class="w80" type="number"></span>
            <span class="coord"><label>Y</label><input id="editY" class="w80" type="number"></span>
            <span class="coord"><label>W</label><input id="editW" class="w80" type="number"></span>
            <span class="coord"><label>H</label><input id="editH" class="w80" type="number"></span>
          </div>
          <div style="margin-top:4px;">
            <button class="btn-adj" onclick="adj(-5,0,0,0)">←5</button>
            <button class="btn-adj" onclick="adj(5,0,0,0)">→5</button>
            <button class="btn-adj" onclick="adj(0,-5,0,0)">↑5</button>
            <button class="btn-adj" onclick="adj(0,5,0,0)">↓5</button>
            <button class="btn-adj" onclick="adj(0,0,-5,0)">W-5</button>
            <button class="btn-adj" onclick="adj(0,0,5,0)">W+5</button>
            <button class="btn-adj" onclick="adj(0,0,0,-5)">H-5</button>
            <button class="btn-adj" onclick="adj(0,0,0,5)">H+5</button>
          </div>
        </div>
      </div>
      <div style="margin-top:8px;">
        <button class="btn btn-sv" onclick="saveChar()">💾 保存</button>
        <button class="btn btn-nv" onclick="move(-1)">◀ 上一</button>
        <button class="btn btn-nv" onclick="move(1)">下一 ▶</button>
        <span id="saveMsg" class="msg"></span>
      </div>
    </div>
  </div>
</div>
<script>
let boxes = {boxes_json};
let selIdx = 0;
let pending = {{}}; // idx -> {{text,x,y,w,h}}

function renderTable() {{
  let tb = document.getElementById('tableBody');
  tb.innerHTML = boxes.map((b,i) => {{
    let text = pending[i] ? pending[i].text : b.text;
    let cls = pending[i] ? 's-man' : (b.manual ? 's-man' : (b.auto ? 's-auto' : 's-ok'));
    return `<tr onclick="select(${{i}})" id="row_${{i}}" class="${{i===selIdx?'sel':''}}">` +
      `<td>${{i+1}}</td><td>${{b.col}}</td><td>${{b.row}}</td>` +
      `<td class="${{cls}}">${{text}}</td><td>${{b.ocr}}</td><td>${{b.x}}</td><td>${{b.y}}</td></tr>`;
  }}).join('');
}}

function select(idx) {{
  selIdx = idx;
  let b = boxes[idx];
  document.querySelectorAll('tr').forEach(r => r.classList.remove('sel'));
  let row = document.getElementById('row_'+idx);
  if (row) row.classList.add('sel');
  let p = pending[idx] || {{}};
  document.getElementById('editText').value = p.text !== undefined ? p.text : b.text;
  document.getElementById('editOcr').textContent = b.ocr;
  document.getElementById('editX').value = p.x !== undefined ? p.x : b.x;
  document.getElementById('editY').value = p.y !== undefined ? p.y : b.y;
  document.getElementById('editW').value = p.w !== undefined ? p.w : b.w;
  document.getElementById('editH').value = p.h !== undefined ? p.h : b.h;
  document.getElementById('saveMsg').className = 'msg';
  document.getElementById('saveMsg').textContent = '';
  // cropped image
  let img = document.getElementById('pageImage');
  let c = document.createElement('canvas');
  let scale = img.naturalWidth / img.width; // but img is the annotated version
  // use the original page image that's embedded
  // For simplicity, just show the area
  document.getElementById('charImg').src = '';
}}

function saveChar() {{
  let idx = selIdx;
  let text = document.getElementById('editText').value;
  let x = parseInt(document.getElementById('editX').value);
  let y = parseInt(document.getElementById('editY').value);
  let w = parseInt(document.getElementById('editW').value);
  let h = parseInt(document.getElementById('editH').value);
  pending[idx] = {{text, x, y, w, h}};
  renderTable();
  document.getElementById('saveMsg').className = 'msg ok';
  document.getElementById('saveMsg').textContent = '✅ 已保存 (待导出)';
}}

function adj(dx, dy, dw, dh) {{
  let x = parseInt(document.getElementById('editX').value) + dx;
  let y = parseInt(document.getElementById('editY').value) + dy;
  let w = parseInt(document.getElementById('editW').value) + dw;
  let h = parseInt(document.getElementById('editH').value) + dh;
  if (w<5) w=5; if (h<5) h=5;
  document.getElementById('editX').value = x;
  document.getElementById('editY').value = y;
  document.getElementById('editW').value = w;
  document.getElementById('editH').value = h;
}}

function move(dir) {{
  let i = selIdx + dir;
  if (i >= 0 && i < boxes.length) select(i);
}}

function filterTable() {{
  let q = document.getElementById('filterInput').value;
  document.querySelectorAll('#tableBody tr').forEach(r => {{
    r.style.display = q ? (r.textContent.includes(q) ? '' : 'none') : '';
  }});
}}

function exportJSON() {{
  let out = {{page: {page}, corrections: []}};
  for (let idx in pending) {{
    let b = boxes[idx];
    let p = pending[idx];
    out.corrections.push({{
      idx: parseInt(idx),
      col: b.col, row: b.row,
      text: p.text,
      x: p.x, y: p.y, w: p.w, h: p.h
    }});
  }}
  let blob = new Blob([JSON.stringify(out, null, 2)], {{type:'application/json'}});
  let a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `page_{{page}}_corrections.json`;
  a.click();
  document.getElementById('statusMsg').textContent = `📥 已导出 ${{Object.keys(pending).length}} 处修改`;
}}

function clearAll() {{
  pending = {{}};
  renderTable();
  document.getElementById('statusMsg').textContent = '🗑️ 已清除待导出';
}}

function loadPage() {{
  let p = document.getElementById('pageInput').value;
  window.location.href = `page_${{String(p).padStart(3,'0')}}_review.html`;
}}

renderTable();
select(0);
</script></body></html>"""

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('pages', nargs='+', type=int)
    args = parser.parse_args()
    for p in args.pages:
        generate_html(p)
