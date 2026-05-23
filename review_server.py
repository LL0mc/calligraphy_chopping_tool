"""校对服务器 v4 - orig_idx 跟踪 + 提交功能"""
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
    """Load OCR data, then overlay corrections by orig_idx."""
    raw_path = os.path.join(PAGES_DIR, f"page_{page_num:03d}_ocr_results.json")
    if not os.path.exists(raw_path):
        return None
    with open(raw_path, encoding='utf-8') as f:
        raw = json.load(f)
    for i, item in enumerate(raw):
        item['orig_idx'] = i

    corr_path = os.path.join(PAGES_DIR, f"page_{page_num:03d}_corrected.json")
    if os.path.exists(corr_path):
        with open(corr_path, encoding='utf-8') as f:
            corr = json.load(f)
        for c in corr:
            oi = c.get('orig_idx', -1)
            if c.get('deleted'):
                if 0 <= oi < len(raw):
                    raw[oi]['deleted'] = True
            elif c.get('added'):
                raw.append(c)
            elif 0 <= oi < len(raw):
                for key, val in c.items():
                    raw[oi][key] = val
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
        if d.get('deleted'):
            continue
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

def annotate_image(data, page_img, selected=0, server_scale=1.0):
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
            'orig_idx': d.get('orig_idx', i),
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
body{font-family:'Microsoft YaHei',sans-serif;background:#1a1612;color:#d4c9b8;padding:12px}
.toolbar{display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap}
.toolbar span{color:#b0a08e}
.toolbar button,.toolbar input{padding:5px 12px;border-radius:4px;border:none;background:#3a3028;color:#d4c9b8;cursor:pointer}
.toolbar button:hover{background:#4a3f35}
.container{display:flex;gap:12px}
.left{flex:1;text-align:center}
.img-wrap{position:relative;display:inline-block;max-width:100%;max-height:88vh}
.img-wrap img{max-width:100%;max-height:88vh;height:auto;display:block;border-radius:6px}
#cv{position:absolute;top:0;left:0;cursor:crosshair;z-index:1}
.right{width:520px;display:flex;flex-direction:column;gap:8px}
.fi{width:100%;padding:6px 10px;background:#2a2520;color:#d4c9b8;border:1px solid #4a3f35;border-radius:4px}
.fi:focus{outline:none;border-color:#8b7355}
.tw{overflow-y:auto;max-height:35vh}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#3a3028;padding:5px 6px;text-align:left;position:sticky;top:0;color:#b0a08e}
td{padding:3px 6px;border-bottom:1px solid #2a2520;cursor:pointer}
tr:hover{background:#2a2520}
tr.sel{background:#3a3028}
.ep{background:#2a2520;padding:12px;border-radius:6px}
.ep input{background:#1a1612;color:#d4c9b8;border:1px solid #4a3f35;padding:5px 8px;border-radius:4px;margin:2px}
.ep input:focus{outline:none;border-color:#8b7355}
.w140{width:140px}
.bnv{background:#4a3f35;padding:5px 14px;border-radius:4px;border:none;cursor:pointer;color:#d4c9b8}
.bnv:hover{background:#5c4f43}
.bdr{background:#5c2e2e;padding:5px 14px;border-radius:4px;border:none;cursor:pointer;color:#d4c9b8}
.bdr:hover{background:#7a3e3e}
.bad{background:#2d4a3e;padding:5px 14px;border-radius:4px;border:none;cursor:pointer;color:#d4c9b8}
.bad:hover{background:#3d5c4e}
.msg{padding:3px 8px;border-radius:4px;display:inline-block;color:#b0a08e}
.msg.ok{background:#2d4a3e;color:#a8c9b8}
.para{background:#2a2520;padding:10px;border-radius:6px;font-size:14px;line-height:1.5;word-break:break-all;max-height:18vh;overflow-y:auto}
.h{color:#8a7a68;font-size:12px;margin-top:4px}
</style>
</head>
<body>
<div class="toolbar">
  <span>页码:</span><input type="number" id="pi" value="_PAGE_" min="1" style="width:60px">
  <button onclick="loadPage()">加载</button>
  <span>选中: <b id="sl">-</b> / _TOTAL_</span>
  <span id="sm" style="color:#888;font-size:13px"></span>
  <button onclick="submitPage()" style="background:#6b5b4a;padding:5px 14px;border-radius:4px;border:none;cursor:pointer;color:#d4c9b8">提交</button>
</div>
<div class="container">
  <div class="left">
    <div class="img-wrap">
    <img id="img" src="data:image/png;base64,_IMG_" alt="page">
    <canvas id="cv"></canvas>
    </div>
  </div>
  <div class="right">
    <div class="ep">
      <div style="display:flex;align-items:flex-start;gap:12px;min-height:100px">
        <img id="crop" src="" alt="裁剪" style="width:90px;height:90px;object-fit:contain;border:1px solid #555;border-radius:4px;background:#111">
        <div style="flex:1">
          <div><span style="color:#aaa">文字:</span>
            <input id="et" class="w140" onkeydown="if(event.key==='Enter'){event.preventDefault();saveWait(function(){document.getElementById('msg').className='msg ok';document.getElementById('msg').textContent='已保存';});}">
            <span style="color:#888;margin-left:8px">OCR: <span id="eo">-</span></span>
          </div>
          <div style="margin-top:4px">
            <span style="color:#888;font-size:12px">X</span><input id="ex" class="w140" type="number">
            <span style="color:#888;font-size:12px">Y</span><input id="ey" class="w140" type="number">
            <span style="color:#888;font-size:12px">W</span><input id="ew" class="w140" type="number">
            <span style="color:#888;font-size:12px">H</span><input id="eh" class="w140" type="number">
          </div>
        </div>
      </div>
      <div style="margin-top:6px">
        <button class="bnv" onclick="mv(-1)">上一</button>
        <button class="bnv" onclick="mv(1)">下一</button>
        <button class="bdr" onclick="delChar()">删除</button>
        <button class="bad" onclick="addChar()">新增</button>
        <span id="msg" class="msg"></span>
      </div>
      <div class="h">拖拽调整位置 | 回车保存 | 点击框切换 | 列号从右到左</div>
<div style="font-size:11px;color:#888;margin-top:4px">
  <span style="color:#b4dcff">█ 正常</span>
  <span style="color:#ffcc00">█ 形状异常</span>
  <span style="color:#ff4444">█ 低置信/?</span>
  <span style="color:#555">█ 空</span>
  <span style="color:#00c8ff">█ 已修正</span>
  <span style="color:#00ff00">█ 选中</span>
</div>
    </div>
    <div id="para" class="para"></div>
    <input class="fi" id="fi" placeholder="筛选文字/OCR..." oninput="ft()">
    <div class="tw"><table id="tbl">
      <thead><tr><th>#</th><th>列</th><th>行</th><th>文字</th><th>置信</th><th>X</th><th>Y</th></tr></thead>
      <tbody id="tb"></tbody>
    </table></div>
  </div>
</div>
<script>
var bx = _BX_;
var si = 0;
var dr = null;
var ds = null;
var SCALE = _SCALE_;
var PAGE = _PAGE_;

function getSortedIndices() {
  var si2 = [];
  for (var i = 0; i < bx.length; i++) si2.push(i);
  si2.sort(function(a,b){
    if (bx[a].col !== bx[b].col) return bx[b].col - bx[a].col;
    return bx[a].row - bx[b].row;
  });
  return si2;
}

function rt() {
  var tb = document.getElementById('tb');
  var h = '';
  var mc = 1;
  for (var i = 0; i < bx.length; i++) { if (bx[i].col > mc) mc = bx[i].col; }
  var si2 = getSortedIndices();
  for (var k = 0; k < si2.length; k++) {
    var i = si2[k];
    var b = bx[i];
    var dt = b.corrected_text || b.text || '';
    var pc = Math.round(b.confidence * 100);
    var dc = mc - b.col + 1;
    h += '<tr onclick="sc('+i+')" id="r'+i+'" class="'+(i===si?'sel':'')+'">'+
      '<td>'+(k+1)+'</td><td>'+dc+'</td><td>'+b.row+'</td>'+
      '<td>'+esc(dt)+'</td><td>'+pc+'%</td><td>'+Math.round(b.x/SCALE)+'</td><td>'+Math.round(b.y/SCALE)+'</td></tr>';
  }
  tb.innerHTML = h;
  updatePara();
}
function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function updatePara() {
  var mc = 1;
  for (var i = 0; i < bx.length; i++) { if (bx[i].col > mc) mc = bx[i].col; }
  var lines = [];
  for (var c = 1; c <= mc; c++) {
    var items = [];
    for (var i = 0; i < bx.length; i++) {
      var b = bx[i];
      if (mc - b.col + 1 !== c) continue;
      items.push({row: b.row, text: b.corrected_text || b.text || ''});
    }
    items.sort(function(a,b){return a.row-b.row;});
    var colText = items.map(function(x){return x.text;}).join('');
    if (colText) lines.push(colText);
  }
  document.getElementById('para').textContent = lines.join(' | ');
}

function gs() {
  var img = document.getElementById('img');
  return img.naturalWidth / img.offsetWidth; // resized-image-px to CSS-px
}

function sc(idx) {
  var os = si;
  saveBg(os);
  si = idx;
  document.querySelectorAll('#tb tr').forEach(function(r){r.classList.remove('sel');});
  var r = document.getElementById('r'+idx);
  if (r) r.classList.add('sel');
  var si2 = getSortedIndices();
  var pos = -1;
  for (var k = 0; k < si2.length; k++) { if (si2[k] === idx) { pos = k+1; break; } }
  var b = bx[idx];
  var label = b.corrected_text || b.text || '';
  document.getElementById('sl').textContent = pos + ' (' + (idx+1) + ')';
  document.getElementById('sm').textContent = b.confidence ? '置信度 '+Math.round(b.confidence*100)+'%' : '';
  document.getElementById('et').value = label;
  document.getElementById('eo').textContent = label || '(empty)';
  document.getElementById('ex').value = Math.round(b.x / SCALE);
  document.getElementById('ey').value = Math.round(b.y / SCALE);
  document.getElementById('ew').value = Math.round(b.w / SCALE);
  document.getElementById('eh').value = Math.round(b.h / SCALE);
  document.getElementById('msg').className = 'msg';
  document.getElementById('msg').textContent = '';
  cropImg(); dc(); updatePara();
}

function cropImg() {
  if (si < 0 || si >= bx.length) return;
  var b = bx[si];
  var img = document.getElementById('img');
  try {
    var cv = document.createElement('canvas');
    cv.width = Math.max(1, Math.round(b.w) + 2);
    cv.height = Math.max(1, Math.round(b.h) + 2);
    var ctx = cv.getContext('2d');
    ctx.drawImage(img, b.x - 1, b.y - 1, b.w + 2, b.h + 2, 0, 0, cv.width, cv.height);
    document.getElementById('crop').src = cv.toDataURL();
  } catch(e) {}
}

function mv(dir) {
  var si2 = getSortedIndices();
  var pos = -1;
  for (var k = 0; k < si2.length; k++) { if (si2[k] === si) { pos = k; break; } }
  var np = pos + dir;
  if (np >= 0 && np < si2.length) sc(si2[np]);
}

function saveBg(os) {
  var val = document.getElementById('et').value;
  var b = bx[os];
  if (!b) return;
  var cur = b.corrected_text || b.text || '';
  if (val === cur) return;
  var xi = parseInt(document.getElementById('ex').value);
  var yi = parseInt(document.getElementById('ey').value);
  var wi = parseInt(document.getElementById('ew').value);
  var hi = parseInt(document.getElementById('eh').value);
  if (isNaN(xi) || isNaN(yi) || isNaN(wi) || isNaN(hi)) return;
  fetch('/sv', {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({p:PAGE, i:os, t:val, x:xi, y:yi, w:wi, h:hi})})
    .then(function(r){return r.json();}).then(function(d){
      if (d.ok) {
        var bi = bx[os];
        bi.text = d.t; bi.corrected_text = ''; bi.manual_corrected = true;
        bi.x = d.xs*SCALE; bi.y = d.ys*SCALE; bi.w = d.ws*SCALE; bi.h = d.hs*SCALE;
        rt();
      }
    }).catch(function(e){});
}

function saveWait(cb) {
  var b = bx[si];
  if (!b) { if(cb) cb(); return; }
  var val = document.getElementById('et').value;
  var cur = b.corrected_text || b.text || '';
  if (val === cur) { if(cb) cb(); return; }
  var xi = parseInt(document.getElementById('ex').value);
  var yi = parseInt(document.getElementById('ey').value);
  var wi = parseInt(document.getElementById('ew').value);
  var hi = parseInt(document.getElementById('eh').value);
  if (isNaN(xi) || isNaN(yi) || isNaN(wi) || isNaN(hi)) { if(cb) cb(); return; }
  fetch('/sv', {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({p:PAGE, i:si, t:val, x:xi, y:yi, w:wi, h:hi})})
    .then(function(r){return r.json();}).then(function(d){
      document.getElementById('msg').className = d.ok ? 'msg ok' : 'msg';
      document.getElementById('msg').textContent = d.m;
      if (d.ok) {
        var bi = bx[si];
        bi.text = d.t; bi.corrected_text = ''; bi.manual_corrected = true;
        bi.x = d.xs*SCALE; bi.y = d.ys*SCALE; bi.w = d.ws*SCALE; bi.h = d.hs*SCALE;
        rt(); cropImg();
      }
      if (cb) cb();
    }).catch(function(e){ document.getElementById('msg').textContent = '请求失败: '+e; });
}

function sv(cb) { saveWait(cb); }

function delChar() {
  fetch('/del', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({p:PAGE, i:si})})
    .then(function(r){return r.json();}).then(function(d){
      if (d.ok) {
        bx.splice(si, 1);
        if (si >= bx.length) si = bx.length - 1;
        if (si < 0) si = 0;
        rt(); dc();
        if (bx.length > 0) sc(si);
        document.getElementById('msg').textContent = d.m;
        document.getElementById('msg').className = 'msg ok';
      } else {
        document.getElementById('msg').textContent = d.m;
      }
    }).catch(function(e){ document.getElementById('msg').textContent = '请求失败: '+e; });
}

function addChar() {
  var last = bx[bx.length-1];
  var nx = last ? last.x : 100;
  var ny = last ? Math.min(last.y + last.h + 10, 3000) : 100;
  var nw = 120, nh = 120;
  fetch('/add', {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({p:PAGE, x:Math.round(nx/SCALE), y:Math.round(ny/SCALE), w:Math.round(nw/SCALE), h:Math.round(nh/SCALE)})})
    .then(function(r){return r.json();}).then(function(d){
      if (d.ok) {
        var c = d.entry;
        var nb = {
          idx: bx.length, col: c.col, row: c.row,
          orig_idx: c.orig_idx,
          text: '', corrected_text: c.corrected_text || '?',
          manual_corrected: true, confidence: 0,
          x: c.x * SCALE, y: c.y * SCALE, w: c.w * SCALE, h: c.h * SCALE
        };
        bx.push(nb);
        sc(bx.length - 1);
        document.getElementById('msg').textContent = d.m;
        document.getElementById('msg').className = 'msg ok';
      } else {
        document.getElementById('msg').textContent = d.m;
      }
    }).catch(function(e){ document.getElementById('msg').textContent = '请求失败: '+e; });
}

function submitPage() {
  saveWait(function(){
    if (!confirm('提交第'+PAGE+'页审查结果，进入下一页？')) return;
    fetch('/submit', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({p:PAGE})})
      .then(function(r){return r.json();}).then(function(d){
        if (d.ok) { window.location.href = '/?p=' + (PAGE + 1); }
        else { document.getElementById('msg').textContent = '提交失败'; }
      });
  });
}

function ft() {
  var q = document.getElementById('fi').value;
  document.querySelectorAll('#tb tr').forEach(function(r){
    r.style.display = q ? (r.textContent.includes(q) ? '' : 'none') : '';
  });
}
function dc() {
  var cv = document.getElementById('cv');
  var ctx = cv.getContext('2d');
  ctx.clearRect(0, 0, cv.width, cv.height);
  if (bx.length === 0) return;
  var s = gs();
  var si2 = getSortedIndices();
  var dn = {}; for (var k = 0; k < si2.length; k++) dn[si2[k]] = k + 1;
  for (var i = 0; i < bx.length; i++) {
    var b = bx[i];
    var x = b.x/s, y = b.y/s, w = b.w/s, h = b.h/s;
    if (w < 3 || h < 3) continue;
    var color;
    if (i === si) {
      color = '#00ff00';
    } else if (b.manual_corrected) {
      color = '#00c8ff';
    } else if (b.confidence < 0.01 && (b.text === '' || b.text === '?')) {
      color = '#555';
    } else if (b.text === '?' || b.confidence < 0.6) {
      color = '#ff4444';
    } else if (Math.max(w/h, h/w) > 2.5) {
      color = '#ffcc00';
    } else {
      color = '#b4dcff';
    }
    ctx.strokeStyle = color;
    ctx.lineWidth = i === si ? 3 : 1.5;
    ctx.strokeRect(x, y, w, h);
    ctx.fillStyle = color;
    ctx.font = '10px sans-serif';
    ctx.fillText(dn[i], x+2, y+10);
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
    var xi = parseInt(document.getElementById('ex').value);
    var yi = parseInt(document.getElementById('ey').value);
    var wi = parseInt(document.getElementById('ew').value);
    var hi = parseInt(document.getElementById('eh').value);
    if (!isNaN(xi) && !isNaN(yi) && !isNaN(wi) && !isNaN(hi)) {
      fetch('/sv', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({p:PAGE, i:si,
          t:document.getElementById('et').value, x:xi, y:yi, w:wi, h:hi})})
        .then(function(r){return r.json();}).then(function(d){
          document.getElementById('msg').className = d.ok ? 'msg ok' : 'msg';
          document.getElementById('msg').textContent = d.m;
          if (d.ok) {
            var b = bx[si];
            b.text = d.t; b.corrected_text = ''; b.manual_corrected = true;
            b.x = d.xs*SCALE; b.y = d.ys*SCALE; b.w = d.ws*SCALE; b.h = d.hs*SCALE;
            rt(); cropImg(); dc();
          }
        });
    }
  }
  dr = null; ds = null;
  dc();
}

function loadPage() {
  window.location.href = '/?p=' + document.getElementById('pi').value;
}

function initFirst() {
  if (bx.length === 0) return;
  var si2 = getSortedIndices();
  si = si2[0]; var b = bx[si]; var label = b.corrected_text || b.text || '';
  document.getElementById('sl').textContent = '1 (' + (si+1) + ')';
  document.getElementById('sm').textContent = b.confidence ? '置信度 '+Math.round(b.confidence*100)+'%' : '';
  document.getElementById('et').value = label;
  document.getElementById('eo').textContent = label || '(empty)';
  document.getElementById('ex').value = Math.round(b.x / SCALE);
  document.getElementById('ey').value = Math.round(b.y / SCALE);
  document.getElementById('ew').value = Math.round(b.w / SCALE);
  document.getElementById('eh').value = Math.round(b.h / SCALE);
  cropImg(); dc(); updatePara();
}
document.addEventListener('DOMContentLoaded', function(){ rt(); });

function setupCanvas() {
  var img = document.getElementById('img');
  var cv = document.getElementById('cv');
  function resize() {
    if (img.offsetWidth > 0) {
      var w = img.offsetWidth, h = img.offsetHeight;
      cv.style.width = w + 'px';
      cv.style.height = h + 'px';
      cv.width = w;
      cv.height = h;
      if (cv.width > 0 && cv.height > 0) dc();
    }
  }
  resize();
  img.onload = function(){ resize(); };
  window.addEventListener('resize', resize);
  cv.addEventListener('mousedown', md);
  cv.addEventListener('mousemove', mm);
  cv.addEventListener('mouseup', mu);
  cv.addEventListener('mouseleave', mu);
}
window.addEventListener('load', function(){ setupCanvas(); initFirst(); });
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
    try:
        req = request.json
        page = req['p']; idx = req['i']
        raw, clean, mapping = load_clean(page)
        if raw is None or idx >= len(clean):
            return jsonify({'ok': False, 'm': f'索引越界 {idx}'})
        corr_path = os.path.join(PAGES_DIR, f"page_{page:03d}_corrected.json")

        corr = []
        if os.path.exists(corr_path):
            with open(corr_path, encoding='utf-8') as f:
                corr = json.load(f)

        orig_idx = clean[idx].get('orig_idx', idx)
        entry = None
        for c in corr:
            if c.get('orig_idx') == orig_idx and not c.get('deleted') and not c.get('added'):
                entry = c
                break
        if entry is None:
            entry = {'orig_idx': orig_idx}
            corr.append(entry)

        entry['corrected_text'] = req['t']
        entry['manual_corrected'] = True
        entry['x'] = req['x']
        entry['y'] = req['y']
        entry['w'] = req['w']
        entry['h'] = req['h']
        entry['text'] = req['t']

        with open(corr_path, 'w', encoding='utf-8') as f:
            json.dump(corr, f, ensure_ascii=False, indent=2)
        drop_cache(page)
        return jsonify({'ok': True, 'm': f'已保存字 {idx+1}',
                        't': req['t'], 'xs': req['x'], 'ys': req['y'],
                        'ws': req['w'], 'hs': req['h']})
    except Exception as e:
        return jsonify({'ok': False, 'm': f'保存失败: {e}'})

@app.route('/del', methods=['POST'])
def delete_char():
    try:
        req = request.json
        page = req['p']; idx = req['i']
        raw, clean, mapping = load_clean(page)
        if raw is None or idx >= len(clean):
            return jsonify({'ok': False, 'm': f'索引越界 {idx}'})
        corr_path = os.path.join(PAGES_DIR, f"page_{page:03d}_corrected.json")

        corr = []
        if os.path.exists(corr_path):
            with open(corr_path, encoding='utf-8') as f:
                corr = json.load(f)

        orig_idx = clean[idx].get('orig_idx', idx)
        corr = [c for c in corr if not (c.get('orig_idx') == orig_idx and not c.get('deleted'))]
        corr.append({'orig_idx': orig_idx, 'deleted': True})

        with open(corr_path, 'w', encoding='utf-8') as f:
            json.dump(corr, f, ensure_ascii=False, indent=2)
        drop_cache(page)
        return jsonify({'ok': True, 'm': f'已删除字 {idx+1}'})
    except Exception as e:
        return jsonify({'ok': False, 'm': f'删除失败: {e}'})

@app.route('/add', methods=['POST'])
def add_char():
    try:
        req = request.json
        page = req['p']
        raw, clean, mapping = load_clean(page)
        if raw is None:
            return jsonify({'ok': False, 'm': '页面数据不存在'})
        corr_path = os.path.join(PAGES_DIR, f"page_{page:03d}_corrected.json")

        corr = []
        if os.path.exists(corr_path):
            with open(corr_path, encoding='utf-8') as f:
                corr = json.load(f)

        max_oi = max([c.get('orig_idx', -1) for c in corr] + [len(raw) - 1])
        new_entry = {
            'orig_idx': max_oi + 1, 'added': True,
            'col': 0, 'row': max_oi + 1,
            'x': req['x'], 'y': req['y'],
            'w': req['w'], 'h': req['h'],
            'text': '', 'confidence': 0,
            'corrected_text': '?', 'manual_corrected': True,
        }
        corr.append(new_entry)

        with open(corr_path, 'w', encoding='utf-8') as f:
            json.dump(corr, f, ensure_ascii=False, indent=2)
        drop_cache(page)
        return jsonify({'ok': True, 'm': '已新增字', 'entry': new_entry})
    except Exception as e:
        return jsonify({'ok': False, 'm': f'新增失败: {e}'})

@app.route('/submit', methods=['POST'])
def submit_page():
    req = request.json
    page = req['p']
    # Mark as reviewed by creating a marker file
    marker = os.path.join(PAGES_DIR, f"page_{page:03d}_reviewed.json")
    raw, clean, mapping = load_clean(page)
    data = {'pages': [{'page': page, 'count': len(clean)}]}
    with open(marker, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return jsonify({'ok': True})

if __name__ == '__main__':
    import webbrowser
    url = 'http://127.0.0.1:5000/?p=24'
    print(url)
    webbrowser.open(url)
    app.run(host='127.0.0.1', port=5000, debug=False)
