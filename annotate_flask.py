"""Flask 校对工具：全页图 + Canvas 鼠标拖框"""
import sys, os, json, cv2, numpy as np, base64, traceback
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flask import Flask, render_template_string, request, jsonify
from config import PAGES_DIR

app = Flask(__name__)

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

def get_clean_data(data):
    """Filter out entries with empty text. Return filtered list + mapping [filtered_idx -> original_idx]."""
    clean = []
    mapping = []
    for i, d in enumerate(data):
        if d.get('corrected_text', d.get('text', '')).strip():
            clean.append(d)
            mapping.append(i)
    return clean, mapping

def img_to_b64(img):
    _, buf = cv2.imencode('.png', img)
    return base64.b64encode(buf).decode()

def annotate_image(data, page_img, selected=0):
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
        if i == selected:
            color, thick = (0, 255, 0), 3
        elif d.get('manual_corrected'):
            color, thick = (0, 200, 255), 2
        elif d.get('auto_corrected'):
            color, thick = (255, 200, 0), 2
        else:
            color, thick = (150, 150, 150), 1
        cv2.rectangle(img, (x, y), (x+bw, y+bh), color, thick)
        cv2.putText(img, f"{i+1}:{text}", (x+2, y+14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
        boxes.append({
            'idx': i, 'col': d['col'], 'row': d['row'],
            'text': text, 'ocr': d.get('text', ''),
            'x': d['x'], 'y': d['y'], 'w': d['w'], 'h': d['h'],
        })
    return img_to_b64(img), boxes, scale

# ---- HTML Template ----
HTML_TPL = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>字帖校对 - 第{PAGE}页</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Microsoft YaHei',sans-serif;background:#1a1a2e;color:#eee;padding:16px}
.toolbar{display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
.toolbar button,.toolbar input{padding:6px 12px;border-radius:4px;border:none;background:#0f3460;color:#fff;cursor:pointer}
.toolbar button:hover{background:#16213e}
.container{display:flex;gap:16px}
.left{flex:3;position:relative}
.left img{width:100%;border-radius:8px;display:block}
#canvasOverlay{position:absolute;top:0;left:0;width:100%;height:100%;cursor:crosshair}
.right{flex:2;display:flex;flex-direction:column;gap:8px}
#filterInput{width:100%;padding:6px;background:#1a1a2e;color:#fff;border:1px solid #333;border-radius:4px}
.tw{overflow-y:auto;max-height:55vh}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#0f3460;padding:6px;text-align:left;position:sticky;top:0}
td{padding:4px 6px;border-bottom:1px solid #333;cursor:pointer}
tr:hover{background:#16213e}
tr.sel{background:#1a5276}
.s-ok{color:#7dcea0}.s-auto{color:#f9e79f}.s-man{color:#85c1e9}
.ep{background:#16213e;padding:16px;border-radius:8px}
.ep input{background:#1a1a2e;color:#fff;border:1px solid #333;padding:4px 8px;border-radius:4px;margin:2px}
.w80{width:80px}
.btn{padding:6px 16px;border-radius:4px;border:none;cursor:pointer;color:#fff}
.bsv{background:#27ae60}.bsv:hover{background:#2ecc71}
.bnv{background:#2980b9}.bnv:hover{background:#3498db}
.msg{padding:4px 8px;border-radius:4px;display:inline-block}
.msg.ok{background:#1a5276;color:#7dcea0}
#charImg{max-width:100px;max-height:100px;border:1px solid #555;border-radius:4px;vertical-align:middle;background:#111}
.hint{color:#888;font-size:12px;margin-top:4px}
</style>
</head>
<body>
<div class="toolbar">
  <span>页码:</span><input type="number" id="pageInput" value="{PAGE}" min="1" style="width:60px">
  <button onclick="loadPage()">📂 加载</button>
  <span>选中: <b id="selLabel">-</b> / {TOTAL}</span>
  <span id="statusMsg" style="color:#888;font-size:13px"></span>
</div>
<div class="container">
  <div class="left">
    <img id="pageImage" src="data:image/png;base64,{IMG_B64}" alt="page" crossorigin="anonymous">
    <canvas id="canvasOverlay"></canvas>
  </div>
  <div class="right">
    <input id="filterInput" placeholder="筛选文字/OCR..." oninput="filterTable()">
    <div class="tw"><table id="charTable">
      <thead><tr><th>#</th><th>列</th><th>行</th><th>文字</th><th>OCR</th><th>X</th><th>Y</th></tr></thead>
      <tbody id="tableBody"></tbody>
    </table></div>
    <div class="ep">
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
        <img id="charImg" src="" alt="裁剪">
        <div>
          <div><span style="color:#aaa">文字:</span>
            <input id="editText" class="w80">
            <span style="color:#888;margin-left:8px">OCR: <span id="editOcr">-</span></span>
          </div>
          <div style="margin-top:4px">
            <span><span style="color:#888;font-size:12px">X</span><input id="editX" class="w80" type="number"></span>
            <span><span style="color:#888;font-size:12px">Y</span><input id="editY" class="w80" type="number"></span>
            <span><span style="color:#888;font-size:12px">W</span><input id="editW" class="w80" type="number"></span>
            <span><span style="color:#888;font-size:12px">H</span><input id="editH" class="w80" type="number"></span>
          </div>
        </div>
      </div>
      <div style="margin-top:6px">
        <button class="btn bsv" onclick="saveChar()">💾 保存</button>
        <button class="btn bnv" onclick="moveIdx(-1)">◀ 上</button>
        <button class="btn bnv" onclick="moveIdx(1)">下 ▶</button>
        <span id="saveMsg" class="msg"></span>
      </div>
      <div class="hint">💡 拖拽方框边缘/角调整位置（鼠标拖动选中框的边或角）</div>
    </div>
  </div>
</div>
<script>
let boxes = {BOXES_JSON};
let selIdx = {SELECTED};
let dragging = null; // {{edge: 'l'|'r'|'t'|'b'|'tl'|'tr'|'bl'|'br'}}
let dragStart = null;
let HIT = 8; // hit test radius in CSS pixels

function renderTable() {
  let tb = document.getElementById('tableBody');
  tb.innerHTML = boxes.map((b,i) => {
    let cls = b.manual ? 's-man' : (b.auto ? 's-auto' : 's-ok');
    return `<tr onclick="selectChar(${i})" id="row_${i}" class="${i===selIdx?'sel':''}">` +
      `<td>${i+1}</td><td>${b.col}</td><td>${b.row}</td>` +
      `<td class="${cls}">${b.text}</td><td>${b.ocr}</td><td>${b.x}</td><td>${b.y}</td></tr>`;
  }).join('');
}

function selectChar(idx) {
  selIdx = idx;
  document.querySelectorAll('#tableBody tr').forEach(r => r.classList.remove('sel'));
  let r = document.getElementById('row_'+idx);
  if (r) r.classList.add('sel');
  let b = boxes[idx];
  document.getElementById('selLabel').textContent = idx+1;
  document.getElementById('editText').value = b.text;
  document.getElementById('editOcr').textContent = b.ocr;
  document.getElementById('editX').value = b.x;
  document.getElementById('editY').value = b.y;
  document.getElementById('editW').value = b.w;
  document.getElementById('editH').value = b.h;
  document.getElementById('saveMsg').className = 'msg';
  document.getElementById('saveMsg').textContent = '';
  fetchCharImg(idx);
  drawCanvas();
}

function fetchCharImg(idx) {
  fetch('/cropped?page={PAGE}&idx='+idx)
    .then(r=>r.json())
    .then(d=>{document.getElementById('charImg').src='data:image/png;base64,'+d.b64;});
}

function saveChar() {
  let b = boxes[selIdx];
  let data = {
    page: {PAGE}, idx: selIdx,
    text: document.getElementById('editText').value,
    x: parseInt(document.getElementById('editX').value),
    y: parseInt(document.getElementById('editY').value),
    w: parseInt(document.getElementById('editW').value),
    h: parseInt(document.getElementById('editH').value),
  };
  fetch('/save', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)})
    .then(r=>r.json()).then(d=>{
      document.getElementById('saveMsg').textContent = d.msg;
      document.getElementById('saveMsg').className = d.ok ? 'msg ok' : 'msg err';
      if (d.ok) {
        Object.assign(b, {text: data.text, x: data.x, y: data.y, w: data.w, h: data.h, manual: true});
        renderTable();
        fetchAnnotate();
      }
    });
}

function moveIdx(dir) {
  let i = selIdx + dir;
  if (i >= 0 && i < boxes.length) selectChar(i);
}

function filterTable() {
  let q = document.getElementById('filterInput').value;
  document.querySelectorAll('#tableBody tr').forEach(r => {
    r.style.display = q ? (r.textContent.includes(q) ? '' : 'none') : '';
  });
}

function fetchAnnotate() {
  fetch('/annotate?page={PAGE}&idx='+selIdx)
    .then(r=>r.json())
    .then(d=>{
      document.getElementById('pageImage').src='data:image/png;base64,'+d.img;
      boxes = d.boxes;
      renderTable();
      setTimeout(drawCanvas, 100);
    });
}

// ---- Canvas overlay for draggable boxes ----
function setupCanvas() {
  let img = document.getElementById('pageImage');
  let canvas = document.getElementById('canvasOverlay');
  function resize() {
    canvas.width = img.offsetWidth;
    canvas.height = img.offsetHeight;
    drawCanvas();
  }
  img.onload = resize;
  window.addEventListener('resize', resize);
  setTimeout(resize, 200);
  
  canvas.addEventListener('mousedown', onMouseDown);
  canvas.addEventListener('mousemove', onMouseMove);
  canvas.addEventListener('mouseup', onMouseUp);
  canvas.addEventListener('mouseleave', onMouseUp);
}

function getScale() {
  let img = document.getElementById('pageImage');
  // The image is displayed at img.offsetWidth CSS pixels wide
  // The original image width in the annotated version:
  // It was scaled to fit 1600px max dimension. We don't have the exact scale,
  // but we can compute it from the relationship between img.offsetWidth and naturalWidth
  // Actually, naturalWidth is the intrinsic size of the PNG (the annotated full-res image)
  let maxDim = Math.max(img.naturalWidth, img.naturalHeight);
  let dispScale = 1600 / maxDim;
  if (dispScale >= 1) dispScale = 1;
  let fullW = img.naturalWidth;
  let displayW = img.offsetWidth;
  // CSS pixels to original image pixels
  return fullW / displayW;
}

function getBoxCSS(idx) {
  let scale = getScale();
  let b = boxes[idx];
  return {
    x: b.x / scale, y: b.y / scale,
    w: b.w / scale, h: b.h / scale
  };
}

function drawCanvas() {
  let canvas = document.getElementById('canvasOverlay');
  let ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  let scale = getScale();
  
  if (selIdx >= 0 && selIdx < boxes.length) {
    let b = boxes[selIdx];
    let x = b.x / scale, y = b.y / scale;
    let w = b.w / scale, h = b.h / scale;
    
    // Semi-transparent green fill
    ctx.fillStyle = 'rgba(0,255,0,0.15)';
    ctx.fillRect(x, y, w, h);
    // Border
    ctx.strokeStyle = '#00ff00';
    ctx.lineWidth = 3;
    ctx.strokeRect(x, y, w, h);
    
    // Draw resize handles
    let hs = 8;
    ctx.fillStyle = '#00ff00';
    let handles = [
      [x, y, 'tl'], [x+w/2-hs/2, y, 't'], [x+w-hs, y, 'tr'],
      [x, y+h/2-hs/2, 'l'], [x+w-hs, y+h/2-hs/2, 'r'],
      [x, y+h-hs, 'bl'], [x+w/2-hs/2, y+h-hs, 'b'], [x+w-hs, y+h-hs, 'br']
    ];
    handles.forEach(([hx, hy]) => {
      ctx.fillRect(hx, hy, hs, hs);
    });
  }
}

function hitTest(cx, cy) {
  let scale = getScale();
  let b = boxes[selIdx];
  if (!b) return null;
  let x = b.x / scale, y = b.y / scale;
  let w = b.w / scale, h = b.h / scale;
  let hs = HIT;
  
  // Corner handles
  if (Math.abs(cx-x) < hs && Math.abs(cy-y) < hs) return 'tl';
  if (Math.abs(cx-(x+w)) < hs && Math.abs(cy-y) < hs) return 'tr';
  if (Math.abs(cx-x) < hs && Math.abs(cy-(y+h)) < hs) return 'bl';
  if (Math.abs(cx-(x+w)) < hs && Math.abs(cy-(y+h)) < hs) return 'br';
  // Edge handles
  if (cx >= x+w/2-10 && cx <= x+w/2+10 && Math.abs(cy-y) < hs) return 't';
  if (cx >= x+w/2-10 && cx <= x+w/2+10 && Math.abs(cy-(y+h)) < hs) return 'b';
  if (Math.abs(cx-x) < hs && cy >= y+h/2-10 && cy <= y+h/2+10) return 'l';
  if (Math.abs(cx-(x+w)) < hs && cy >= y+h/2-10 && cy <= y+h/2+10) return 'r';
  
  // Inside box - move
  if (cx >= x && cx <= x+w && cy >= y && cy <= y+h) return 'move';
  
  return null;
}

function cssToImage(cssX, cssY) {
  let scale = getScale();
  return {x: cssX * scale, y: cssY * scale};
}

function onMouseDown(e) {
  let rect = document.getElementById('canvasOverlay').getBoundingClientRect();
  let cx = e.clientX - rect.left;
  let cy = e.clientY - rect.top;
  let hit = hitTest(cx, cy);
  if (hit) {
    dragging = hit;
    dragStart = {cx, cy, ...boxes[selIdx]};
    document.getElementById('canvasOverlay').style.cursor = 'grabbing';
  } else {
    // Check if we clicked on any other box (select it)
    let scale = getScale();
    let imgX = cx * scale, imgY = cy * scale;
    // Search from last to first (top-most)
    // Actually boxes don't overlap, just find by position
    for (let i = boxes.length-1; i >= 0; i--) {
      let b = boxes[i];
      if (imgX >= b.x && imgX <= b.x+b.w && imgY >= b.y && imgY <= b.y+b.h) {
        selectChar(i);
        return;
      }
    }
  }
}

function onMouseMove(e) {
  let rect = document.getElementById('canvasOverlay').getBoundingClientRect();
  let cx = e.clientX - rect.left;
  let cy = e.clientY - rect.top;
  
  if (dragging && dragStart) {
    let imgPt = cssToImage(cx, cy);
    let startPt = cssToImage(dragStart.cx, dragStart.cy);
    let dx = imgPt.x - startPt.x;
    let dy = imgPt.y - startPt.y;
    let b = dragStart;
    let nx = b.x, ny = b.y, nw = b.w, nh = b.h;
    
    switch (dragging) {
      case 'move': nx = b.x + dx; ny = b.y + dy; break;
      case 'tl': nx = b.x + dx; ny = b.y + dy; nw = b.w - dx; nh = b.h - dy; break;
      case 'tr': ny = b.y + dy; nw = b.w + dx; nh = b.h - dy; break;
      case 'bl': nx = b.x + dx; nw = b.w - dx; nh = b.h + dy; break;
      case 'br': nw = b.w + dx; nh = b.h + dy; break;
      case 't': ny = b.y + dy; nh = b.h - dy; break;
      case 'b': nh = b.h + dy; break;
      case 'l': nx = b.x + dx; nw = b.w - dx; break;
      case 'r': nw = b.w + dx; break;
    }
    if (nw < 10) nw = 10;
    if (nh < 10) nh = 10;
    
    let box = boxes[selIdx];
    box.x = Math.round(nx); box.y = Math.round(ny);
    box.w = Math.round(nw); box.h = Math.round(nh);
    
    document.getElementById('editX').value = box.x;
    document.getElementById('editY').value = box.y;
    document.getElementById('editW').value = box.w;
    document.getElementById('editH').value = box.h;
    drawCanvas();
    return;
  }
  
  // Update cursor
  let hit = hitTest(cx, cy);
  let cursors = {
    'tl':'nwse-resize','tr':'nesw-resize','bl':'nesw-resize','br':'nwse-resize',
    't':'ns-resize','b':'ns-resize','l':'ew-resize','r':'ew-resize',
    'move':'grab'
  };
  document.getElementById('canvasOverlay').style.cursor = cursors[hit] || 'crosshair';
}

function onMouseUp(e) {
  if (dragging) {
    // Auto-save on drag end
    let box = boxes[selIdx];
    fetch('/save', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        page: {PAGE}, idx: selIdx,
        text: box.text,
        x: box.x, y: box.y, w: box.w, h: box.h
      })
    }).then(r=>r.json()).then(d=>{
      document.getElementById('saveMsg').textContent = d.msg;
      document.getElementById('saveMsg').className = d.ok ? 'msg ok' : 'msg err';
      if (d.ok) box.manual = true;
    });
  }
  dragging = null;
  dragStart = null;
}

function loadPage() {
  let p = document.getElementById('pageInput').value;
  window.location.href = '/?page=' + p;
}

document.addEventListener('DOMContentLoaded', () => {
  renderTable();
  if (boxes.length > 0) selectChar(0);
  setupCanvas();
});
</script>
</body></html>"""

# Store mapping per page
_clean_cache = {}

def get_clean_with_map(page_num):
    if page_num not in _clean_cache:
        raw = load_data(page_num)
        if raw is None:
            return None, None, None
        clean, mapping = get_clean_data(raw)
        _clean_cache[page_num] = (raw, clean, mapping)
    return _clean_cache[page_num]

def invalidate_cache(page_num):
    _clean_cache.pop(page_num, None)

@app.route('/')
def index():
    try:
        page = request.args.get('page', 24, type=int)
        raw_data, clean_data, mapping = get_clean_with_map(page)
        img = load_img(page)
        if raw_data is None or img is None:
            return f"Page {page} not found", 404
        b64, boxes, scale = annotate_image(clean_data, img, 0)
        html = (HTML_TPL
                .replace('{PAGE}', str(page))
                .replace('{IMG_B64}', b64)
                .replace('{BOXES_JSON}', json.dumps(boxes, ensure_ascii=False))
                .replace('{SELECTED}', '0')
                .replace('{TOTAL}', str(len(clean_data))))
        return html
    except:
        return f"<pre>{traceback.format_exc()}</pre>", 500

@app.route('/annotate')
def get_annotate():
    page = request.args.get('page', 24, type=int)
    idx = request.args.get('idx', 0, type=int)
    raw_data, clean_data, mapping = get_clean_with_map(page)
    img = load_img(page)
    if raw_data is None or img is None:
        return jsonify({'error': 'not found'})
    if idx >= len(clean_data):
        idx = 0
    b64, boxes, scale = annotate_image(clean_data, img, idx)
    return jsonify({'img': b64, 'boxes': boxes})

@app.route('/cropped')
def get_cropped():
    page = request.args.get('page', 24, type=int)
    idx = request.args.get('idx', 0, type=int)
    raw_data, clean_data, mapping = get_clean_with_map(page)
    img = load_img(page)
    if raw_data is None or img is None:
        return jsonify({'b64': ''})
    if idx >= len(clean_data):
        return jsonify({'b64': ''})
    d = clean_data[idx]
    x, y, w, h = d['x'], d['y'], d['w'], d['h']
    pad = 20
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(img.shape[1], x + w + pad)
    y2 = min(img.shape[0], y + h + pad)
    crop = img[y1:y2, x1:x2]
    b64 = img_to_b64(crop)
    return jsonify({'b64': b64})

@app.route('/save', methods=['POST'])
def save_char():
    req = request.json
    page = req['page']
    idx = req['idx']
    raw_data, clean_data, mapping = get_clean_with_map(page)
    path = os.path.join(PAGES_DIR, f"page_{page:03d}_corrected.json")
    ocr_path = os.path.join(PAGES_DIR, f"page_{page:03d}_ocr_results.json")
    src = path if os.path.exists(path) else ocr_path
    try:
        with open(src, encoding='utf-8') as f:
            full_data = json.load(f)
        # Map from clean index to original index
        orig_idx = mapping[idx]
        d = full_data[orig_idx]
        if req['text'] != d.get('corrected_text', d.get('text', '')):
            d['corrected_text'] = req['text']
            d['manual_corrected'] = True
        d['x'], d['y'], d['w'], d['h'] = req['x'], req['y'], req['w'], req['h']
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(full_data, f, ensure_ascii=False, indent=2)
        invalidate_cache(page)
        return jsonify({'ok': True, 'msg': f'已保存字 {idx+1}'})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})

if __name__ == '__main__':
    import webbrowser
    url = 'http://127.0.0.1:5000/?page=24'
    print(url)
    webbrowser.open(url)
    app.run(host='127.0.0.1', port=5000, debug=False)
