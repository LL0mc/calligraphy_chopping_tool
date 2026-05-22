"""校对服务器 v3 - 缩放+PNG+坐标正确+新增字"""
import sys, os, json, cv2, numpy as np, base64, traceback
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flask import Flask, request, jsonify
from config import PAGES_DIR
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)
_clean_cache = {}
FONT_PATH = r'C:\Windows\Fonts\msyh.ttc'

def get_font():
    try: return ImageFont.truetype(FONT_PATH, 14)
    except: return ImageFont.load_default()

def load_data(page_num):
    """Load original OCR data, then overlay manual corrections."""
    raw_path = os.path.join(PAGES_DIR, f"page_{page_num:03d}_ocr_results.json")
    if not os.path.exists(raw_path):
        return None
    with open(raw_path, encoding='utf-8') as f:
        raw = json.load(f)
    # Apply manual corrections from corrected.json if exists
    corr_path = os.path.join(PAGES_DIR, f"page_{page_num:03d}_corrected.json")
    if os.path.exists(corr_path):
        with open(corr_path, encoding='utf-8') as f:
            corr = json.load(f)
        # Build index by (col, row)
        idx = {}
        for ci, c in enumerate(corr):
            if c.get('manual_corrected'):
                idx[(c['col'], c['row'])] = ci
        for item in raw:
            key = (item['col'], item['row'])
            if key in idx:
                mc = corr[idx[key]]
                item['corrected_text'] = mc.get('corrected_text', item['text'])
                item['manual_corrected'] = True
    return raw

def load_img(page_num):
    for name in [f"page_{page_num:03d}_processed.png", f"page_{page_num:03d}.png"]:
        p = os.path.join(PAGES_DIR, name)
        if os.path.exists(p):
            img = cv2.imread(p)
            if img is not None:
                return img
    return None

def img_to_b64(img):
    _, buf = cv2.imencode('.png', img)
    return base64.b64encode(buf).decode()

def get_clean_data(data):
    clean, mapping = [], []
    for i, d in enumerate(data):
        if d.get('x') and d.get('w') and d['w'] > 5:
            clean.append(dict(d))
            mapping.append(i)
    return clean, mapping

def load_clean(page_num):
    if page_num not in _clean_cache:
        raw = load_data(page_num)
        if raw is None: return None, None, None
        clean, mapping = get_clean_data(raw)
        _clean_cache[page_num] = (raw, clean, mapping)
    return _clean_cache[page_num]

def drop_cache(page_num):
    _clean_cache.pop(page_num, None)

def draw_text(img, text, pos, color):
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(pil)
    d.text(pos, text, font=get_font(), fill=color)
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

def annotate_image(data, page_img, selected=0, server_scale=1.0):
    """Generate box data (canvas draws boxes, not the server image)."""
    if server_scale < 1:
        img = cv2.resize(page_img, None, fx=server_scale, fy=server_scale)
    else:
        img = page_img.copy()
    boxes = []
    for i, d in enumerate(data):
        xs = int(d['x'] * server_scale)
        ys = int(d['y'] * server_scale)
        ws = max(1, int(d['w'] * server_scale))
        hs = max(1, int(d['h'] * server_scale))
        text = d.get('text', '')
        corr = d.get('corrected_text', '')
        boxes.append({
            'idx': i, 'col': d['col'], 'row': d['row'],
            'text': text, 'ocr': d.get('text', ''),
            'corrected_text': corr if corr and corr != text else '',
            'manual_corrected': d.get('manual_corrected', False),
            'confidence': d.get('confidence', 0),
            'x': xs, 'y': ys, 'w': ws, 'h': hs,
        })
    return img_to_b64(img), boxes

HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>字帖校对 - 第_PAGE_页</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Microsoft YaHei',sans-serif;background:#1a1a2e;color:#eee;padding:16px}
.toolbar{display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
.toolbar button,.toolbar input{padding:6px 12px;border-radius:4px;border:none;background:#0f3460;color:#fff;cursor:pointer}
.toolbar button:hover{background:#16213e}
.container{display:flex;gap:16px}
.left{flex:3}
.img-wrap{position:relative;display:inline-block;max-width:100%;max-height:88vh}
.img-wrap img{max-width:100%;max-height:88vh;height:auto;display:block;border-radius:8px}
#cv{position:absolute;top:0;left:0;cursor:crosshair;z-index:1}
.right{flex:2;display:flex;flex-direction:column;gap:8px}
.fi{width:100%;padding:6px;background:#1a1a2e;color:#fff;border:1px solid #333;border-radius:4px}
.tw{overflow-y:auto;max-height:50vh}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#0f3460;padding:6px;text-align:left;position:sticky;top:0}
td{padding:4px 6px;border-bottom:1px solid #333;cursor:pointer}
tr:hover{background:#16213e}
tr.sel{background:#1a5276}
.s0{color:#7dcea0}.s1{color:#85c1e9}
.ep{background:#16213e;padding:16px;border-radius:8px}
.ep input{background:#1a1a2e;color:#fff;border:1px solid #333;padding:4px 8px;border-radius:4px;margin:2px}
.w80{width:80px}
.bsv{background:#27ae60;padding:6px 16px;border-radius:4px;border:none;cursor:pointer;color:#fff}
.bsv:hover{background:#2ecc71}
.bnv{background:#2980b9;padding:6px 16px;border-radius:4px;border:none;cursor:pointer;color:#fff}
.bnv:hover{background:#3498db}
.bdr{background:#c0392b;padding:6px 16px;border-radius:4px;border:none;cursor:pointer;color:#fff}
.bdr:hover{background:#e74c3c}
.bad{background:#27ae60;padding:6px 16px;border-radius:4px;border:none;cursor:pointer;color:#fff}
.bad:hover{background:#2ecc71}
.msg{padding:4px 8px;border-radius:4px;display:inline-block}
.msg.ok{background:#1a5276;color:#7dcea0}
#crop{max-width:100px;max-height:100px;border:1px solid #555;border-radius:4px;vertical-align:middle;background:#111}
.h{color:#888;font-size:12px;margin-top:4px}
</style>
</head>
<body>
<div class="toolbar">
  <span>页码:</span><input type="number" id="pi" value="_PAGE_" min="1" style="width:60px">
  <button onclick="loadPage()">加载</button>
  <span>选中: <b id="sl">-</b> / _TOTAL_</span>
  <span id="sm" style="color:#888;font-size:13px"></span>
</div>
<div class="container">
  <div class="left">
    <div class="img-wrap">
    <img id="img" src="data:image/png;base64,_IMG_" alt="page">
    <canvas id="cv"></canvas>
    </div>
  </div>
  <div class="right">
    <input class="fi" id="fi" placeholder="筛选文字/OCR..." oninput="ft()">
    <div class="tw"><table id="tbl">
      <thead><tr><th>#</th><th>列</th><th>行</th><th>文字</th><th>置信</th><th>X</th><th>Y</th></tr></thead>
      <tbody id="tb"></tbody>
    </table></div>
    <div class="ep">
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
        <img id="crop" src="" alt="裁剪">
        <div>
          <div><span style="color:#aaa">文字:</span>
            <input id="et" class="w80">
            <span style="color:#888;margin-left:8px">OCR: <span id="eo">-</span></span>
          </div>
          <div style="margin-top:4px">
            <span style="color:#888;font-size:12px">X</span><input id="ex" class="w80" type="number">
            <span style="color:#888;font-size:12px">Y</span><input id="ey" class="w80" type="number">
            <span style="color:#888;font-size:12px">W</span><input id="ew" class="w80" type="number">
            <span style="color:#888;font-size:12px">H</span><input id="eh" class="w80" type="number">
          </div>
        </div>
      </div>
      <div style="margin-top:6px">
        <button class="bsv" onclick="sv()">保存</button>
        <button class="bnv" onclick="mv(-1)">上一</button>
        <button class="bnv" onclick="mv(1)">下一</button>
        <button class="bdr" onclick="delChar()">删除</button>
        <button class="bad" onclick="addChar()">新增</button>
        <span id="msg" class="msg"></span>
      </div>
      <div class="h">拖拽方框边缘/角调整位置 | 点击图片上的框选中</div>
<div style="font-size:11px;color:#888;margin-top:4px">
  <span style="color:#b4dcff">█ 高置信</span>
  <span style="color:#ffcc00">█ 中置信</span>
  <span style="color:#ff4444">█ 低置信</span>
  <span style="color:#555">█ 空</span>
  <span style="color:#00c8ff">█ 已修正</span>
  <span style="color:#00ff00">█ 选中</span>
</div>
    </div>
  </div>
</div>
<script>
var bx = _BX_;
var si = 0;
var dr = null;
var ds = null;
var SCALE = _SCALE_;
var PAGE = _PAGE_;

function rt() {
  var tb = document.getElementById('tb');
  var h = '';
  for (var i = 0; i < bx.length; i++) {
    var b = bx[i];
    var dt = b.corrected_text ? b.text+'\u2192'+b.corrected_text : (b.text||'');
    var pc = Math.round(b.confidence * 100);
    h += '<tr onclick="sc('+i+')" id="r'+i+'" class="'+(i===si?'sel':'')+'">'+
      '<td>'+(i+1)+'</td><td>'+b.col+'</td><td>'+b.row+'</td>'+
      '<td>'+esc(dt)+'</td><td>'+pc+'%</td><td>'+Math.round(b.x/SCALE)+'</td><td>'+Math.round(b.y/SCALE)+'</td></tr>';
  }
  tb.innerHTML = h;
}
function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function gs() {
  var img = document.getElementById('img');
  return img.naturalWidth / img.offsetWidth; // resized-image-px to CSS-px
}

function sc(idx) {
  si = idx;
  document.querySelectorAll('#tb tr').forEach(function(r){r.classList.remove('sel');});
  var r = document.getElementById('r'+idx);
  if (r) r.classList.add('sel');
  var b = bx[idx];
  document.getElementById('sl').textContent = idx+1;
  document.getElementById('sm').textContent = b.confidence ? '置信度 '+Math.round(b.confidence*100)+'%' : '';
  document.getElementById('et').value = b.corrected_text ? b.corrected_text : b.text;
  document.getElementById('eo').textContent = b.corrected_text ? b.text+'\u2192'+b.corrected_text : (b.text||'(empty)');
  document.getElementById('ex').value = Math.round(b.x / SCALE);
  document.getElementById('ey').value = Math.round(b.y / SCALE);
  document.getElementById('ew').value = Math.round(b.w / SCALE);
  document.getElementById('eh').value = Math.round(b.h / SCALE);
  document.getElementById('msg').className = 'msg';
  document.getElementById('msg').textContent = '';
  cropImg();
  dc();
}

function cropImg() {
  fetch('/crop?p='+PAGE+'&i='+si).then(function(r){return r.json();}).then(function(d){
    document.getElementById('crop').src = 'data:image/png;base64,'+d.b;
  });
}

function sv(cb) {
  var b = bx[si];
  var data = {p:PAGE, i:si, t:document.getElementById('et').value,
    x:parseInt(document.getElementById('ex').value),
    y:parseInt(document.getElementById('ey').value),
    w:parseInt(document.getElementById('ew').value),
    h:parseInt(document.getElementById('eh').value)};
  fetch('/sv', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)})
    .then(function(r){return r.json();}).then(function(d){
      document.getElementById('msg').textContent = d.m;
      document.getElementById('msg').className = d.ok ? 'msg ok' : 'msg';
      if (d.ok) {
        Object.assign(b, {text:d.t, x:d.xs*SCALE, y:d.ys*SCALE, w:d.ws*SCALE, h:d.hs*SCALE, manual_corrected:true});
        rt(); dc(); cropImg();
        if (cb) cb();
      }
    });
}

function delChar() {
  if (!confirm('Delete #'+(si+1)+'?')) return;
  fetch('/del', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({p:PAGE, i:si})})
    .then(function(r){return r.json();}).then(function(d){
      if (d.ok) location.reload();
      else document.getElementById('msg').textContent = d.m;
    });
}

function addChar() {
  // Find last box to place new char nearby
  var last = bx[bx.length-1];
  var nx = last ? last.x : 100;
  var ny = last ? Math.min(last.y + last.h + 10, 3000) : 100;
  var nw = 120, nh = 120;
  // Estimate col/row
  fetch('/add', {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({p:PAGE, x:Math.round(nx/SCALE), y:Math.round(ny/SCALE), w:Math.round(nw/SCALE), h:Math.round(nh/SCALE)})})
    .then(function(r){return r.json();}).then(function(d){
      if (d.ok) location.reload();
      else document.getElementById('msg').textContent = d.m;
    });
}

function mv(dir) {
  var i = si + dir;
  if (i >= 0 && i < bx.length) sc(i);
}

function ft() {
  var q = document.getElementById('fi').value;
  document.querySelectorAll('#tb tr').forEach(function(r){
    r.style.display = q ? (r.textContent.includes(q) ? '' : 'none') : '';
  });
}

function setupCanvas() {
  var img = document.getElementById('img');
  var cv = document.getElementById('cv');
  function resize() {
    if (img.naturalWidth > 0 && img.offsetWidth > 0) {
      var w = img.offsetWidth, h = img.offsetHeight;
      cv.style.width = w + 'px';
      cv.style.height = h + 'px';
      cv.width = w;
      cv.height = h;
      if (cv.width > 0 && cv.height > 0) dc();
    }
  }
  resize();
  if (img.complete) resize();
  img.onload = resize;
  window.addEventListener('resize', resize);
  cv.addEventListener('mousedown', md);
  cv.addEventListener('mousemove', mm);
  cv.addEventListener('mouseup', mu);
  cv.addEventListener('mouseleave', mu);
}

function dc() {
  var cv = document.getElementById('cv');
  var ctx = cv.getContext('2d');
  ctx.clearRect(0, 0, cv.width, cv.height);
  if (bx.length === 0) return;
  var s = gs();
  // Draw all boxes
  for (var i = 0; i < bx.length; i++) {
    var b = bx[i];
    var x = b.x/s, y = b.y/s, w = b.w/s, h = b.h/s;
    if (w < 3 || h < 3) continue;
    var color;
    if (i === si) {
      color = '#00ff00';
    } else if (b.manual_corrected) {
      color = '#00c8ff';
    } else if (b.confidence < 0.01 || (b.text === '' && !b.corrected_text)) {
      color = '#555';
    } else if (b.confidence < 0.6) {
      color = '#ff4444';
    } else if (b.confidence < 0.85) {
      color = '#ffcc00';
    } else {
      color = '#b4dcff';
    }
    ctx.strokeStyle = color;
    ctx.lineWidth = i === si ? 3 : 1.5;
    ctx.strokeRect(x, y, w, h);
    ctx.fillStyle = color;
    ctx.font = '10px sans-serif';
    ctx.fillText(i+1, x+2, y+10);
  }
  // Ghost during drag
  if (dr && ds) {
    var ox = ds.x/s, oy = ds.y/s, ow = ds.w/s, oh = ds.h/s;
    ctx.strokeStyle = 'rgba(255,255,255,0.4)';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.strokeRect(ox, oy, ow, oh);
    ctx.setLineDash([]);
  }
  // Handles for selected
  if (si >= 0 && si < bx.length) {
    var b = bx[si];
    var x = b.x/s, y = b.y/s, w = b.w/s, h = b.h/s;
    var hs = 5;
    ctx.fillStyle = '#00ff00';
    var hh = [[x-hs/2, y-hs/2],[x+w/2-hs/2, y-hs/2],[x+w-hs/2, y-hs/2],
      [x-hs/2, y+h/2-hs/2],[x+w-hs/2, y+h/2-hs/2],
      [x-hs/2, y+h-hs/2],[x+w/2-hs/2, y+h-hs/2],[x+w-hs/2, y+h-hs/2]];
    for (var i = 0; i < hh.length; i++) ctx.fillRect(hh[i][0], hh[i][1], hs, hs);
  }
}

function ht(cx, cy) {
  var s = gs();
  var b = bx[si];
  if (!b) return null;
  var x = b.x/s, y = b.y/s, w = b.w/s, h = b.h/s;
  if (w < 3 || h < 3) return null;
  var hs = 5;
  function hx(nx, ny) { return Math.abs(cx-(nx+hs/2))<hs+1 && Math.abs(cy-(ny+hs/2))<hs+1; }
  if (hx(x-hs/2, y-hs/2)) return 'tl';
  if (hx(x+w/2-hs/2, y-hs/2)) return 't';
  if (hx(x+w-hs/2, y-hs/2)) return 'tr';
  if (hx(x-hs/2, y+h/2-hs/2)) return 'l';
  if (hx(x+w-hs/2, y+h/2-hs/2)) return 'r';
  if (hx(x-hs/2, y+h-hs/2)) return 'bl';
  if (hx(x+w/2-hs/2, y+h-hs/2)) return 'b';
  if (hx(x+w-hs/2, y+h-hs/2)) return 'br';
  if (cx>=x && cx<=x+w && cy>=y && cy<=y+h) return 'mv';
  return null;
}

function md(e) {
  var r = document.getElementById('cv').getBoundingClientRect();
  var cx = e.clientX - r.left, cy = e.clientY - r.top;
  var h = ht(cx, cy);
  if (h) {
    dr = h;
    ds = {cx:cx, cy:cy, x:bx[si].x, y:bx[si].y, w:bx[si].w, h:bx[si].h};
    document.getElementById('cv').style.cursor = 'grabbing';
    return;
  }
  var s = gs();
  var ix = cx * s, iy = cy * s;
  for (var i = bx.length-1; i >= 0; i--) {
    var b = bx[i];
    if (ix >= b.x && ix <= b.x+b.w && iy >= b.y && iy <= b.y+b.h) { sc(i); return; }
  }
}

function mm(e) {
  var r = document.getElementById('cv').getBoundingClientRect();
  var cx = e.clientX - r.left, cy = e.clientY - r.top;
  if (dr && ds) {
    var s = gs();
    var dx = (cx - ds.cx) * s, dy = (cy - ds.cy) * s;
    var nx = ds.x, ny = ds.y, nw = ds.w, nh = ds.h;
    switch(dr) {
      case 'mv': nx=ds.x+dx; ny=ds.y+dy; break;
      case 'tl': nx=ds.x+dx; ny=ds.y+dy; nw=ds.w-dx; nh=ds.h-dy; break;
      case 'tr': ny=ds.y+dy; nw=ds.w+dx; nh=ds.h-dy; break;
      case 'bl': nx=ds.x+dx; nw=ds.w-dx; nh=ds.h+dy; break;
      case 'br': nw=ds.w+dx; nh=ds.h+dy; break;
      case 't': ny=ds.y+dy; nh=ds.h-dy; break;
      case 'b': nh=ds.h+dy; break;
      case 'l': nx=ds.x+dx; nw=ds.w-dx; break;
      case 'r': nw=ds.w+dx; break;
    }
    if (nw<10) nw=10; if (nh<10) nh=10;
    var b = bx[si];
    b.x=Math.round(nx); b.y=Math.round(ny); b.w=Math.round(nw); b.h=Math.round(nh);
    document.getElementById('ex').value=Math.round(b.x/SCALE); document.getElementById('ey').value=Math.round(b.y/SCALE);
    document.getElementById('ew').value=Math.round(b.w/SCALE); document.getElementById('eh').value=Math.round(b.h/SCALE);
    // Update table row display
    var r = document.getElementById('r'+si);
    if (r && r.cells.length >= 7) {
        r.cells[5].textContent = Math.round(b.x/SCALE);
        r.cells[6].textContent = Math.round(b.y/SCALE);
    }
    // Client-side crop preview during drag
    var img = document.getElementById('img');
    var cv = document.createElement('canvas');
    cv.width = Math.round(b.w)+2; cv.height = Math.round(b.h)+2;
    var ctx = cv.getContext('2d');
    ctx.drawImage(img, b.x-1, b.y-1, b.w+2, b.h+2, 0, 0, cv.width, cv.height);
    document.getElementById('crop').src = cv.toDataURL();
    dc(); return;
  }
  var h = ht(cx, cy);
  var cs = {tl:'nwse-resize',tr:'nesw-resize',bl:'nesw-resize',br:'nwse-resize',
    t:'ns-resize',b:'ns-resize',l:'ew-resize',r:'ew-resize',mv:'grab'};
  document.getElementById('cv').style.cursor = cs[h] || 'crosshair';
}

function mu(e) {
  if (dr) {
    fetch('/sv', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({p:PAGE, i:si,
        t:document.getElementById('et').value,
        x:parseInt(document.getElementById('ex').value),
        y:parseInt(document.getElementById('ey').value),
        w:parseInt(document.getElementById('ew').value),
        h:parseInt(document.getElementById('eh').value)})})
      .then(function(r){return r.json();}).then(function(d){
        document.getElementById('msg').textContent = d.m;
        document.getElementById('msg').className = d.ok ? 'msg ok' : 'msg';
        if (d.ok) {
          var b = bx[si];
          Object.assign(b, {text:d.t, x:d.xs*SCALE, y:d.ys*SCALE, w:d.ws*SCALE, h:d.hs*SCALE, manual:true});
          rt(); cropImg(); dc();
        }
      });
  }
  dr = null; ds = null;
  dc();
}

function loadPage() {
  window.location.href = '/?p=' + document.getElementById('pi').value;
}

document.addEventListener('DOMContentLoaded', function(){ rt(); if (bx.length>0) sc(0); setupCanvas(); });
</script>
</body></html>"""

@app.route('/')
def index():
    try:
        page = request.args.get('p', 24, type=int)
        raw, clean, mapping = load_clean(page)
        img = load_img(page)
        if raw is None or img is None:
            return f"Page {page} not found", 404
        # Compute server scale
        h, w = img.shape[:2]
        max_dim = 2000
        scale = min(max_dim/w, max_dim/h, 1.0)
        b64, boxes = annotate_image(clean, img, 0, scale)
        html = HTML.replace('_PAGE_', str(page))
        html = html.replace('_IMG_', b64)
        html = html.replace('_BX_', json.dumps(boxes, ensure_ascii=False))
        html = html.replace('_TOTAL_', str(len(clean)))
        html = html.replace('_SCALE_', str(scale))
        return html
    except:
        return f"<pre>{traceback.format_exc()}</pre>", 500

@app.route('/an')
def get_annotate():
    page = request.args.get('p', 24, type=int)
    idx = request.args.get('i', 0, type=int)
    raw, clean, mapping = load_clean(page)
    img = load_img(page)
    if raw is None or img is None:
        return jsonify({'error': 'not found'})
    if idx >= len(clean): idx = 0
    h, w = img.shape[:2]
    scale = min(1600/w, 1600/h, 1.0)
    b64, boxes = annotate_image(clean, img, idx, scale)
    return jsonify({'g': b64, 'bx': boxes})

@app.route('/crop')
def get_cropped():
    page = request.args.get('p', 24, type=int)
    idx = request.args.get('i', 0, type=int)
    raw, clean, mapping = load_clean(page)
    img = load_img(page)
    if raw is None or img is None:
        return jsonify({'b': ''})
    if idx >= len(clean):
        return jsonify({'b': ''})
    d = clean[idx]
    x, y, w, h = d['x'], d['y'], d['w'], d['h']
    x1 = max(0, x-15); y1 = max(0, y-15)
    x2 = min(img.shape[1], x+w+15); y2 = min(img.shape[0], y+h+15)
    crop = img[y1:y2, x1:x2]
    return jsonify({'b': img_to_b64(crop)})

@app.route('/sv', methods=['POST'])
def save_char():
    req = request.json
    page = req['p']; idx = req['i']
    raw, clean, mapping = load_clean(page)
    path = os.path.join(PAGES_DIR, f"page_{page:03d}_corrected.json")
    src = path if os.path.exists(path) else os.path.join(PAGES_DIR, f"page_{page:03d}_ocr_results.json")
    try:
        with open(src, encoding='utf-8') as f:
            full = json.load(f)
        orig = mapping[idx]
        d = full[orig]
        d['corrected_text'] = req['t']
        d['manual_corrected'] = True
        d['x'], d['y'], d['w'], d['h'] = req['x'], req['y'], req['w'], req['h']
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(full, f, ensure_ascii=False, indent=2)
        drop_cache(page)
        return jsonify({'ok': True, 'm': f'已保存字 {idx+1}',
                        't': req['t'], 'xs': req['x'], 'ys': req['y'],
                        'ws': req['w'], 'hs': req['h']})
    except Exception as e:
        return jsonify({'ok': False, 'm': str(e)})

@app.route('/del', methods=['POST'])
def delete_char():
    req = request.json
    page = req['p']; idx = req['i']
    path = os.path.join(PAGES_DIR, f"page_{page:03d}_corrected.json")
    if not os.path.exists(path):
        return jsonify({'ok': False, 'm': '找不到校正文件，请先保存一次'})
    try:
        with open(path, encoding='utf-8') as f:
            full = json.load(f)
        raw, clean, mapping = load_clean(page)
        orig = mapping[idx]
        full.pop(orig)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(full, f, ensure_ascii=False, indent=2)
        drop_cache(page)
        return jsonify({'ok': True, 'm': f'已删除字 {idx+1}'})
    except Exception as e:
        return jsonify({'ok': False, 'm': str(e)})

@app.route('/add', methods=['POST'])
def add_char():
    req = request.json
    page = req['p']
    path = os.path.join(PAGES_DIR, f"page_{page:03d}_corrected.json")
    src = path if os.path.exists(path) else os.path.join(PAGES_DIR, f"page_{page:03d}_ocr_results.json")
    try:
        with open(src, encoding='utf-8') as f:
            full = json.load(f)
        # Add new entry at end
        new_entry = {
            'col': 0, 'row': len(full) + 1,
            'x': req['x'], 'y': req['y'],
            'w': req['w'], 'h': req['h'],
            'text': '', 'confidence': 0,
            'corrected_text': '?',
            'manual_corrected': True,
        }
        full.append(new_entry)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(full, f, ensure_ascii=False, indent=2)
        drop_cache(page)
        return jsonify({'ok': True, 'm': '已新增字'})
    except Exception as e:
        return jsonify({'ok': False, 'm': str(e)})

if __name__ == '__main__':
    import webbrowser
    url = 'http://127.0.0.1:5000/?p=24'
    print(url)
    webbrowser.open(url)
    app.run(host='127.0.0.1', port=5000, debug=False)
