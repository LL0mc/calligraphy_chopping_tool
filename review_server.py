"""校对服务器 v4 - orig_idx 跟踪 + 提交功能"""
import sys, os, json, cv2, numpy as np, base64, traceback, subprocess, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flask import Flask, request, jsonify
from config import PAGES_DIR, CALLIGRAPHER, SOURCE_TEXT, CROPPED_DIR, CHAR_DB_DIR, PDF_PATH
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)
_clean_cache = {}
FONT_PATH = r'C:\Windows\Fonts\msyh.ttc'
_LAST_PAGE_FILE = os.path.join(PAGES_DIR, '.last_page')

def get_last_page():
    try:
        if os.path.exists(_LAST_PAGE_FILE):
            with open(_LAST_PAGE_FILE, 'r') as f:
                return int(f.read().strip())
    except: pass
    return 24

def save_last_page(num):
    try:
        with open(_LAST_PAGE_FILE, 'w') as f:
            f.write(str(num))
    except: pass

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
:root {
  --bg-deep: #0e1420;
  --bg-surface: #141a28;
  --glass-bg: rgba(255,255,255,0.04);
  --glass-border: rgba(255,255,255,0.08);
  --glass-hover: rgba(255,255,255,0.12);
  --text-primary: #e8e0d4;
  --text-muted: #908078;
  --text-faint: #605850;
  --accent-red: #e8453c;
  --accent-red-glow: rgba(232,69,60,0.25);
  --accent-blue: #4a7cf7;
  --accent-blue-glow: rgba(74,124,247,0.2);
  --accent-gold: #c09860;
  --accent-green: #34d399;
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 16px;
  --font-ui: 'Noto Sans SC', 'Microsoft YaHei', sans-serif;
  --font-display: 'ZCOOL QingKe HuangYou', 'KaiTi', serif;
  --font-mono: 'JetBrains Mono', 'Consolas', monospace;
  --transition: 0.2s cubic-bezier(0.4,0,0.2,1);
}
body.light{
  --bg-deep: #f2e8c8;
  --bg-surface: #faf4e0;
  --glass-bg: rgba(255,252,240,0.8);
  --glass-border: rgba(0,0,0,0.07);
  --glass-hover: rgba(0,0,0,0.12);
  --text-primary: #2c2416;
  --text-muted: #6b6050;
  --text-faint: #9a9080;
  --accent-red: #d13b30;
  --accent-red-glow: rgba(209,59,48,0.2);
  --accent-blue: #3b6fe0;
  --accent-blue-glow: rgba(59,111,224,0.18);
  --input-bg: rgba(0,0,0,0.04);
  --input-border: rgba(0,0,0,0.12);
}
body.light .fi, body.light input[type=number], body.light select, body.light textarea {
  background: var(--input-bg);
  border: 1px solid var(--input-border) !important;
}
body.light .fi:focus, body.light input[type=number]:focus, body.light select:focus, body.light textarea:focus {
  border-color: var(--accent-blue) !important;
  box-shadow: 0 0 8px var(--accent-blue-glow);
}
body.light select option { background: var(--bg-surface); color: var(--text-primary); }
body.light .btn { background: rgba(0,0,0,0.06); }
body.light .btn:hover { background: rgba(0,0,0,0.1); }
body.light .btn-primary { background: rgba(59,111,224,0.1); }
body.light .btn-danger { background: rgba(209,59,48,0.1); }
body.light .btn-success { background: rgba(52,211,153,0.1); }
*{margin:0;padding:0;box-sizing:border-box}
body{
  font-family:var(--font-ui);
  background:var(--bg-deep);
  color:var(--text-primary);
  padding:16px;
  min-height:100vh;
}
.toolbar{
  display:flex;gap:6px;align-items:center;margin-bottom:12px;flex-wrap:wrap;
  background:var(--glass-bg);border:1px solid var(--glass-border);
  border-radius:var(--radius-lg);padding:8px 14px;
  backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
  animation:fadeIn 0.4s ease;
}
.toolbar span{color:var(--text-muted);font-size:13px}
.btn{
  padding:6px 14px;border-radius:var(--radius-sm);border:none;
  background:rgba(255,255,255,0.08);
  color:var(--text-primary);cursor:pointer;
  font-family:var(--font-ui);font-size:13px;
  transition:var(--transition);
}
.btn:hover{
  background:rgba(255,255,255,0.13);
  box-shadow:0 0 10px rgba(255,255,255,0.06);
  transform:translateY(-1px);
}
.btn-primary{background:rgba(74,124,247,0.15);color:var(--accent-blue)}
.btn-primary:hover{background:rgba(74,124,247,0.25);box-shadow:0 0 14px var(--accent-blue-glow)}
.btn-danger{background:rgba(232,69,60,0.12);color:var(--accent-red)}
.btn-danger:hover{background:rgba(232,69,60,0.2);box-shadow:0 0 14px var(--accent-red-glow)}
.btn-success{background:rgba(52,211,153,0.12);color:var(--accent-green)}
.btn-success:hover{background:rgba(52,211,153,0.2);box-shadow:0 0 14px rgba(52,211,153,0.2)}
.toolbar input[type=number]{
  padding:5px 8px;border-radius:var(--radius-sm);border:1px solid var(--glass-border);
  background:rgba(255,255,255,0.06);color:var(--text-primary);
  font-family:var(--font-mono);font-size:13px;width:60px;
  transition:var(--transition);
}
.toolbar input[type=number]:focus{outline:none;border-color:var(--accent-blue);box-shadow:0 0 10px var(--accent-blue-glow)}
.container{display:flex;gap:14px;animation:fadeIn 0.5s ease 0.1s both}
.left{flex:1;text-align:center}
.glass{
  background:var(--glass-bg);border:1px solid var(--glass-border);
  border-radius:var(--radius-md);padding:12px;
  backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
  transition:var(--transition);
}
.glass:hover{border-color:var(--glass-hover)}
.img-wrap{position:relative;display:inline-block;max-width:100%;max-height:88vh}
.img-wrap img{max-width:100%;max-height:88vh;height:auto;display:block;border-radius:calc(var(--radius-md) - 2px)}
#cv{position:absolute;top:0;left:0;cursor:crosshair;z-index:1}
.right{
  width:520px;display:flex;flex-direction:column;gap:10px;
  animation:fadeIn 0.5s ease 0.2s both;
}
.fi{
  width:100%;padding:8px 12px;border-radius:var(--radius-sm);
  border:1px solid var(--glass-border);
  background:rgba(255,255,255,0.06);color:var(--text-primary);
  font-family:var(--font-ui);font-size:13px;
  transition:var(--transition);
}
.fi:focus{outline:none;border-color:var(--accent-blue);box-shadow:0 0 10px var(--accent-blue-glow)}
.tw{overflow-y:auto;max-height:35vh;padding:0}
table{width:100%;border-collapse:collapse;font-size:13px;font-family:var(--font-ui)}
th{
  background:var(--bg-surface);padding:6px 8px;text-align:left;
  position:sticky;top:0;z-index:2;color:var(--text-muted);font-weight:500;font-size:12px;
  border-bottom:1px solid var(--glass-border);
}
td{padding:4px 8px;border-bottom:1px solid rgba(255,255,255,0.04);cursor:pointer;transition:var(--transition)}
tr{transition:var(--transition)}
tr:hover td{background:rgba(255,255,255,0.04)}
tr td:first-child{position:relative}
tr:hover td:first-child::before{
  content:'';position:absolute;left:0;top:3px;bottom:3px;width:2px;
  background:var(--accent-blue);border-radius:1px;
  box-shadow:0 0 8px var(--accent-blue-glow);
}
tr.sel td{background:rgba(74,124,247,0.12)}
tr.sel td:first-child::before{
  content:'';position:absolute;left:0;top:3px;bottom:3px;width:2px;
  background:var(--accent-blue);border-radius:1px;
  box-shadow:0 0 8px var(--accent-blue-glow);
}
.ep{display:flex;align-items:flex-start;gap:14px;min-height:100px;margin-bottom:8px}
.ep #crop{width:90px;height:90px;object-fit:contain;border:1px solid var(--glass-border);border-radius:var(--radius-sm);background:var(--bg-deep)}
.ep .fields{flex:1}
.ep .fields .row{display:flex;align-items:center;gap:6px;margin-top:8px}
.ep .fields .row label{color:var(--text-faint);font-size:12px;width:16px;text-align:right;font-family:var(--font-mono)}
.ep .fields .row input{
  flex:1;padding:5px 8px;border-radius:var(--radius-sm);border:1px solid var(--glass-border);
  background:rgba(255,255,255,0.06);color:var(--text-primary);
  font-family:var(--font-mono);font-size:13px;transition:var(--transition);
}
.ep .fields .row input:focus{outline:none;border-color:var(--accent-blue);box-shadow:0 0 10px var(--accent-blue-glow)}
.ep .fields .label-row{display:flex;align-items:center;gap:8px;margin-bottom:4px}
.ep .fields .label-text{color:var(--text-muted);font-size:13px}
.ep .fields .label-row .ocr-info{color:var(--text-faint);font-size:12px;margin-left:8px}
.ep .fields .label-row input{
  padding:5px 10px 5px 14px;border-radius:var(--radius-sm);
  border:1px solid var(--glass-border);border-left:3px solid var(--accent-blue);
  background:rgba(255,255,255,0.07);color:var(--text-primary);
  font-family:var(--font-mono);font-size:14px;font-weight:500;
  transition:var(--transition);outline:none;
  box-shadow:0 0 12px rgba(0,0,0,0.15);
}
.ep .fields .label-row input:focus{
  border-color:var(--accent-blue);border-left-color:var(--accent-blue);
  box-shadow:0 0 14px var(--accent-blue-glow),inset 0 0 6px rgba(74,124,247,0.06);
}
.ep .fields .label-row input::selection{background:var(--accent-blue);color:#fff}
.w140{width:120px!important}
.actions{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:8px}
.actions .hint{color:var(--text-faint);font-size:11px;margin-left:4px}
.legend{display:flex;gap:14px;margin-top:8px;flex-wrap:wrap}
.legend .dot{display:inline-flex;align-items:center;gap:5px;font-size:11px;color:var(--text-muted)}
.legend .dot::before{content:'';display:inline-block;width:7px;height:7px;border-radius:50%}
.legend .dot.normal::before{background:#b4dcff;box-shadow:0 0 5px rgba(180,220,255,0.3)}
.legend .dot.shape::before{background:#ffcc00;box-shadow:0 0 5px rgba(255,204,0,0.3)}
.legend .dot.low::before{background:var(--accent-red);box-shadow:0 0 5px var(--accent-red-glow)}
.legend .dot.fixed::before{background:var(--accent-blue);box-shadow:0 0 5px var(--accent-blue-glow)}
.legend .dot.selected::before{background:var(--accent-green);box-shadow:0 0 5px rgba(52,211,153,0.3)}
.para-glass{
  background:var(--glass-bg);border:1px solid var(--glass-border);
  border-radius:var(--radius-md);padding:12px 14px;
  backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
}
.para-glass .sep{height:1px;background:var(--glass-border);margin:8px 0 10px}
.para{font-size:14px;line-height:1.6;word-break:break-all;max-height:18vh;overflow-y:auto;color:var(--text-primary)}
.para .label{color:var(--text-muted);font-size:11px;display:block}
.msg{padding:3px 10px;border-radius:var(--radius-sm);display:inline-block;font-size:12px;color:var(--text-faint)}
.msg.ok{background:rgba(52,211,153,0.12);color:var(--accent-green)}
.overlay{
  position:fixed;top:0;left:0;width:100%;height:100%;
  background:rgba(0,0,0,0.6);
  backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);
  display:flex;justify-content:center;align-items:center;z-index:999;
}
.overlay>div{
  background:var(--glass-bg);border:1px solid var(--glass-border);
  padding:36px 56px;border-radius:var(--radius-lg);text-align:center;color:var(--text-primary);
  backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
}
.spinner{
  border:3px solid rgba(255,255,255,0.08);
  border-top:3px solid var(--accent-blue);
  border-radius:50%;width:36px;height:36px;
  animation:spin 0.8s linear infinite;margin:0 auto 16px;
}
@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
.st{font-size:11px;padding:3px 12px;border-radius:20px;font-weight:500;display:inline-flex;align-items:center;gap:5px}
.st::before{content:'';display:inline-block;width:6px;height:6px;border-radius:50%}
.st0{background:rgba(232,69,60,0.12);color:var(--accent-red)}
.st0::before{background:var(--accent-red);box-shadow:0 0 6px var(--accent-red-glow);animation:breathe 2s ease-in-out infinite}
.st1{background:rgba(52,211,153,0.12);color:var(--accent-green)}
.st1::before{background:var(--accent-green);box-shadow:0 0 6px rgba(52,211,153,0.25)}
.st2{background:rgba(192,152,96,0.12);color:var(--accent-gold)}
.st2::before{background:var(--accent-gold);box-shadow:0 0 6px rgba(192,152,96,0.25)}
.st3{background:rgba(255,255,255,0.05);color:var(--text-muted)}
.st3::before{background:var(--text-muted)}
.st4{background:rgba(232,69,60,0.1);color:#ff9944}
.st4::before{background:#ff9944;box-shadow:0 0 6px rgba(255,153,68,0.25);animation:breathe 2s ease-in-out infinite}
@keyframes breathe{0%,100%{opacity:1}50%{opacity:0.4}}
@keyframes fadeIn{0%{opacity:0;transform:translateY(8px)}100%{opacity:1;transform:translateY(0)}}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.08);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:rgba(255,255,255,0.15)}
body.light ::-webkit-scrollbar-thumb{background:rgba(0,0,0,0.12)}
body.light ::-webkit-scrollbar-thumb:hover{background:rgba(0,0,0,0.2)}
</style>
</head>
<body>
<div class="toolbar">
  <span>页码:</span>
  <input type="number" id="pi" value="_PAGE_" min="1">
  <button class="btn" onclick="loadPage()">加载</button>
  <button class="btn" onclick="redetectPage()">重检</button>
  <button class="btn" onclick="goPrev()">◀ 上一页</button>
  <button class="btn" onclick="goNext()">下一页 ▶</button>
  <span id="statusLabel" class="st st0">-</span>
  <button class="btn" onclick="skipPage()" style="font-size:12px">⏭ 跳过</button>
  <span>选中: <b id="sl">-</b> / _TOTAL_</span>
  <span id="sm" style="color:var(--text-faint);font-size:13px"></span>
  <button class="btn" id="themeBtn" onclick="toggleTheme()" title="切换浅色/深色模式" style="font-size:16px;line-height:1">🌙</button>
  <button class="btn btn-success" onclick="submitPage()">提交</button>
  <button class="btn btn-danger" onclick="if(confirm('退出校对服务器？')){fetch('/shutdown',{method:'POST'});document.body.innerHTML='<div style=\'display:flex;justify-content:center;align-items:center;height:100vh;font-family:var(--font-ui);color:var(--text-primary)\'><div style=\'text-align:center\'><div style=\'font-size:48px;margin-bottom:16px\'>⏻</div><div style=\'font-size:18px\'>服务器已停止</div><div style=\'font-size:13px;color:var(--text-muted);margin-top:8px\'>可以关闭此页面</div></div></div>'}" title="退出服务器" style="font-size:12px;margin-left:auto">⏻ 退出</button>
</div>
<div id="loadingOverlay" class="overlay" style="display:none">
  <div><div class="spinner"></div><div id="loadingMsg">处理中...</div></div>
</div>
<div class="container">
  <div class="left">
    <div class="glass" style="display:inline-block;padding:4px">
      <div class="img-wrap">
        <img id="img" src="data:image/png;base64,_IMG_" alt="page">
        <canvas id="cv"></canvas>
      </div>
    </div>
  </div>
  <div class="right">
    <div class="glass">
      <div class="ep">
        <img id="crop" src="" alt="裁剪">
        <div class="fields">
          <div class="label-row">
            <span class="label-text">文字:</span>
            <input id="et" class="w140" onkeydown="if(event.key==='Enter'){event.preventDefault();saveWait(function(){document.getElementById('msg').className='msg ok';document.getElementById('msg').textContent='已保存';});}">
            <span class="ocr-info">OCR: <span id="eo">-</span></span>
          </div>
          <div class="row">
            <label>X</label><input id="ex" class="w140" type="number">
            <label>Y</label><input id="ey" class="w140" type="number">
          </div>
          <div class="row">
            <label>W</label><input id="ew" class="w140" type="number">
            <label>H</label><input id="eh" class="w140" type="number">
          </div>
        </div>
      </div>
      <div class="actions">
        <button class="btn" onclick="mv(-1)">上一</button>
        <button class="btn" onclick="mv(1)">下一</button>
        <button class="btn btn-danger" onclick="delChar()">删除</button>
        <button class="btn btn-primary" onclick="addChar()">新增</button>
        <span id="msg" class="msg"></span>
        <span class="hint">拖拽调整 · 回车保存 · 点击框切换 · 列号右→左</span>
      </div>
      <div class="legend">
        <span class="dot normal">正常</span>
        <span class="dot shape">形状异常</span>
        <span class="dot low">低置信/?</span>
        <span class="dot fixed">已修正</span>
        <span class="dot selected">选中</span>
      </div>
    </div>
    <div class="para-glass">
      <span class="label">段落预览</span>
      <div class="sep"></div>
      <div id="para" class="para"></div>
    </div>
    <input class="fi" id="fi" placeholder="筛选文字/OCR..." oninput="ft()">
    <div class="glass tw" style="padding:0">
      <table id="tbl">
        <thead><tr><th>#</th><th>列</th><th>行</th><th>文字</th><th>置信</th><th>X</th><th>Y</th></tr></thead>
        <tbody id="tb"></tbody>
      </table>
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
  var el = document.getElementById('crop');
  if (si < 0 || si >= bx.length) {
    var cv = document.createElement('canvas');
    cv.width = 90; cv.height = 90;
    var ctx = cv.getContext('2d');
    ctx.fillStyle = '#f5f0e8';
    ctx.fillRect(0, 0, 90, 90);
    ctx.fillStyle = '#bbb';
    ctx.font = '12px "Noto Sans SC", sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('无选中', 45, 45);
    el.src = cv.toDataURL();
    return;
  }
  var b = bx[si];
  var img = document.getElementById('img');
  try {
    var cv = document.createElement('canvas');
    cv.width = Math.max(1, Math.round(b.w) + 2);
    cv.height = Math.max(1, Math.round(b.h) + 2);
    var ctx = cv.getContext('2d');
    ctx.drawImage(img, b.x - 1, b.y - 1, b.w + 2, b.h + 2, 0, 0, cv.width, cv.height);
    el.src = cv.toDataURL();
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
        rt(); dc();
      }
      checkStatus(PAGE);
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
        rt(); cropImg(); dc();
      }
      checkStatus(PAGE);
      if (cb) cb();
    }).catch(function(e){ document.getElementById('msg').textContent = '请求失败: '+e; });
}

function sv(cb) { saveWait(cb); }

function delChar() {
  var delSi = si;
  fetch('/del', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({p:PAGE, i:delSi})})
    .then(function(r){return r.json();}).then(function(d){
      if (d.ok) {
        bx.splice(delSi, 1);
        var newSi = delSi;
        if (newSi >= bx.length) newSi = bx.length - 1;
        if (newSi < 0) newSi = 0;
        si = newSi;
        rt(); dc();
        // Show the newly selected box info without triggering saveBg
        if (bx.length > 0) {
          var b = bx[si];
          if (b) {
            var si2 = getSortedIndices();
            var pos = -1;
            for (var k = 0; k < si2.length; k++) { if (si2[k] === si) { pos = k + 1; break; } }
            document.getElementById('sl').textContent = pos + ' (' + (si+1) + ')';
            document.getElementById('sm').textContent = b.confidence ? '置信度 '+Math.round(b.confidence*100)+'%' : '';
            var label = b.corrected_text || b.text || '';
            document.getElementById('et').value = label;
            document.getElementById('eo').textContent = label || '(empty)';
            document.getElementById('ex').value = Math.round(b.x / SCALE);
            document.getElementById('ey').value = Math.round(b.y / SCALE);
            document.getElementById('ew').value = Math.round(b.w / SCALE);
            document.getElementById('eh').value = Math.round(b.h / SCALE);
            cropImg(); dc(); updatePara();
          }
        }
        document.getElementById('msg').textContent = d.m;
        document.getElementById('msg').className = 'msg ok';
      } else {
        document.getElementById('msg').textContent = d.m;
      }
      checkStatus(PAGE);
    }).catch(function(e){ document.getElementById('msg').textContent = '请求失败: '+e; });
}

function addChar() {
  var refIdx = si;
  var nx, ny;
  if (si < 0 || si >= bx.length) {
    var si2 = getSortedIndices();
    var first = si2.length > 0 ? bx[si2[0]] : null;
    nx = first ? first.x : 100;
    ny = first ? first.y - 150 : 100;
    refIdx = -1;
  } else {
    var b = bx[si];
    nx = b.x + b.w + 10;
    ny = b.y;
  }
  var nw = 120, nh = 120;
  fetch('/add', {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({p:PAGE, i:refIdx, x:Math.round(nx/SCALE), y:Math.round(ny/SCALE), w:Math.round(nw/SCALE), h:Math.round(nh/SCALE)})})
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
      checkStatus(PAGE);
    }).catch(function(e){ document.getElementById('msg').textContent = '请求失败: '+e; });
}

function submitPage() {
  saveWait(function(){
    if (!confirm('提交第'+PAGE+'页审查结果，进入下一页？')) return;
    showLoading('正在提交第'+PAGE+'页...');
    fetch('/submit', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({p:PAGE})})
      .then(function(r){return r.json();}).then(function(d){
        if (d.ok) { hideLoading(); gotoPage(PAGE + 1); }
        else { hideLoading(); document.getElementById('msg').textContent = d.m || '提交失败'; }
      }).catch(function(e){ hideLoading(); alert('提交请求失败: '+e); });
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
    } else if (b.text === '?' || b.confidence < 0.8) {
      color = '#ff4444';
    } else if (Math.max(w/h, h/w) > 2.5) {
      color = '#ffcc00';
    } else {
      color = '#b4dcff';
    }
    ctx.strokeStyle = color;
    ctx.lineWidth = i === si ? 3 : 1.5;
    ctx.strokeRect(x, y, w, h);
    var lbl = b.corrected_text || b.text || '?';
    ctx.font = '16px "Noto Sans SC", "Microsoft YaHei", sans-serif';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'top';
    var tx = x - 3, ty = y;
    if (tx < 20) { tx = x + w + 3; ctx.textAlign = 'left'; }
    ctx.fillStyle = 'rgba(255,255,255,0.85)';
    ctx.fillText(lbl, tx, ty);
    ctx.textAlign = 'start';
    ctx.textBaseline = 'alphabetic';
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
  if (si < 0 || si >= bx.length) return null;
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
  si = -1; cropImg(); dc();
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
          checkStatus(PAGE);
        });
    }
  }
  dr = null; ds = null;
  dc();
}

function loadPage() {
  var p = parseInt(document.getElementById('pi').value);
  gotoPage(p);
}

function redetectPage() {
  if (!confirm('重检第' + PAGE + '页？当前修改和裁剪将被清除。')) return;
  showLoading('正在重检第' + PAGE + '页...');
  fetch('/redetect', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({p:PAGE})})
    .then(function(r){return r.json();}).then(function(d){
      if (d.ok) { window.location.href = '/?p=' + PAGE; }
      else { hideLoading(); document.getElementById('msg').textContent = d.m || '重检失败'; document.getElementById('msg').className = 'msg err'; }
    }).catch(function(e){ hideLoading(); document.getElementById('msg').textContent = '请求失败: ' + e; });
}

function showLoading(msg) {
  document.getElementById('loadingMsg').textContent = msg || '处理中...';
  document.getElementById('loadingOverlay').style.display = 'flex';
}
function hideLoading() {
  document.getElementById('loadingOverlay').style.display = 'none';
}

function checkStatus(p, cb) {
  fetch('/status?p=' + p).then(function(r){return r.json();}).then(function(d){
    var label = document.getElementById('statusLabel');
    var m = {unprocessed:'未检测', ready:'未提交', submitted:'已提交', pending:'待提交', skipped:'已跳过'};
    var cls = {unprocessed:'st0', ready:'st1', submitted:'st2', pending:'st4', skipped:'st3'};
    label.textContent = m[d.status] || d.status;
    label.className = 'st ' + (cls[d.status] || 'st0');
    if (cb) cb(d);
  });
}

function gotoPage(p) {
  if (p < 1) return;
  document.getElementById('pi').value = p;
  showLoading('检查页面状态...');
  fetch('/status?p=' + p).then(function(r){return r.json();}).then(function(d){
    if (d.status === 'unprocessed') {
      showLoading('正在检测第' + p + '页...');
      fetch('/run_page', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({p:p})})
        .then(function(r){return r.json();}).then(function(d2){
          if (d2.ok) { window.location.href = '/?p=' + p; }
          else { hideLoading(); alert(d2.m); }
        }).catch(function(e){ hideLoading(); alert('检测请求失败: '+e); });
    } else if (d.status === 'skipped') {
      if (confirm('第' + p + '页已跳过，是否取消跳过并重新检测？')) {
        showLoading('正在检测第' + p + '页...');
        fetch('/run_page', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({p:p})})
          .then(function(r){return r.json();}).then(function(d2){
            if (d2.ok) { window.location.href = '/?p=' + p; }
            else { hideLoading(); alert(d2.m); }
          }).catch(function(e){ hideLoading(); alert('检测请求失败: '+e); });
      } else { hideLoading(); }
    } else {
      window.location.href = '/?p=' + p;
    }
  }).catch(function(e){ hideLoading(); alert('状态检查失败: '+e); });
}

function goPrev() { gotoPage(PAGE - 1); }
function goNext() { gotoPage(PAGE + 1); }

function skipPage() {
  if (!confirm('跳过第' + PAGE + '页？')) return;
  showLoading('正在跳过...');
  fetch('/skip', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({p:PAGE})})
    .then(function(r){return r.json();}).then(function(d){
      hideLoading();
      if (d.ok) { checkStatus(PAGE); }
      else { alert(d.m); }
    }).catch(function(e){ hideLoading(); alert('跳过请求失败: '+e); });
}

function toggleTheme() {
  var b = document.body;
  var isLight = b.classList.toggle('light');
  document.getElementById('themeBtn').textContent = isLight ? '☀️' : '🌙';
  try { localStorage.setItem('review_theme', isLight ? 'light' : 'dark'); } catch(e) {}
}
(function(){ var t = 'dark'; try { t = localStorage.getItem('review_theme') || 'dark'; } catch(e) {}
  if (t === 'light') { document.body.classList.add('light'); document.getElementById('themeBtn').textContent = '☀️'; }
})();
function initFirst() {
  if (bx.length === 0) { cropImg(); return; }
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
document.addEventListener('DOMContentLoaded', function(){ rt(); checkStatus(PAGE); });

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
        page = request.args.get('p', get_last_page(), type=int)
        save_last_page(page)
        raw, clean, mapping = load_clean(page)
        img = load_img(page)
        if img is None:
            return f"Page {page} not found", 404
        if raw is None:
            raw, clean, mapping = [], [], []
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
    if img is None:
        return jsonify({'error': 'not found'})
    if raw is None:
        raw, clean, mapping = [], [], []
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
    if img is None:
        return jsonify({'b': ''})
    if raw is None:
        raw, clean, mapping = [], [], []
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
            if c.get('orig_idx') == orig_idx and not c.get('deleted'):
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

        # Determine insertion position based on selected item
        after_idx = req.get('i', -1)
        if after_idx >= 0 and after_idx < len(clean):
            target = clean[after_idx]
            new_col = target.get('col', 0)
            new_row = target.get('row', 0) + 0.5
        elif clean:
            # No selection: insert at beginning of reading order
            sorted_clean = sorted(clean, key=lambda d: (-d.get('col', 0), d.get('row', 0)))
            first = sorted_clean[0]
            new_col = first.get('col', 0)
            new_row = first.get('row', 0) - 0.5
        else:
            new_col = 0
            new_row = 0

        max_oi = max([c.get('orig_idx', -1) for c in corr] + [len(raw) - 1])
        new_entry = {
            'orig_idx': max_oi + 1, 'added': True,
            'col': new_col, 'row': new_row,
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
    try:
        req = request.json
        page = req['p']
        raw, clean, mapping = load_clean(page)
        if raw is None:
            return jsonify({'ok': False, 'm': '页面数据不存在'})

        # Load full-res image
        img = load_img(page)
        if img is None:
            return jsonify({'ok': False, 'm': '图片加载失败'})

        # Sort by reading order: col DESC, row ASC
        clean_sorted = sorted(clean, key=lambda d: (-d['col'], d['row']))

        # Crop and save each character
        page_dir = os.path.join(CROPPED_DIR, CALLIGRAPHER, SOURCE_TEXT, f"page_{page:03d}")
        # Clean old cropped directory
        if os.path.exists(page_dir):
            import shutil
            shutil.rmtree(page_dir)
        os.makedirs(page_dir, exist_ok=True)

        char_entries = []
        skip_count = 0
        for seq, d in enumerate(clean_sorted, 1):
            ch = d.get('corrected_text') or d.get('text') or '?'
            safe_char = ch.strip()
            if not safe_char: safe_char = 'unk'
            try:
                x, y, w, h = d['x'], d['y'], d['w'], d['h']
                if w <= 0 or h <= 0:
                    skip_count += 1; continue
                x1 = max(0, x - 4); y1 = max(0, y - 4)
                x2 = min(img.shape[1], x + w + 4); y2 = min(img.shape[0], y + h + 4)
                if x1 >= x2 or y1 >= y2:
                    skip_count += 1; continue
                crop = img[y1:y2, x1:x2]

                fname = f"{seq:03d}_{safe_char}.png"
                fpath = os.path.join(page_dir, fname)
                # Use PIL to handle Unicode file paths on Windows
                img_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                Image.fromarray(img_rgb).save(fpath)
            except Exception as e:
                print(f"  skip char {seq} '{safe_char}': {e}")
                skip_count += 1
                continue

            char_entries.append({
                'seq': seq, 'char': safe_char,
                'col': d['col'], 'row': d['row'],
                'confidence': d.get('confidence', 0),
                'x': x, 'y': y, 'w': w, 'h': h,
                'rel_path': os.path.join("cropped", CALLIGRAPHER, SOURCE_TEXT, f"page_{page:03d}", fname),
            })

        # Build full text in reading order for context
        full_text = [e['char'] for e in char_entries]

        # Update Obsidian character database — collect per char then write once
        base_rel = os.path.join(CALLIGRAPHER, SOURCE_TEXT)
        note_dir = os.path.join(CHAR_DB_DIR, base_rel)
        os.makedirs(note_dir, exist_ok=True)

        # Group entries by char
        from collections import defaultdict
        char_groups = defaultdict(list)
        seen = set()
        for e in char_entries:
            ch = e['char']
            if ch == '?' or ch == 'unk':
                continue
            # Deduplicate same img link per char per page
            key = (ch, e['seq'])
            if key not in seen:
                seen.add(key)
                char_groups[ch].append(e)

        for ch, entries in char_groups.items():
            note_path = os.path.join(note_dir, f"{ch}.md")
            rows = []
            for e in entries:
                img_link = f"![[{e['rel_path'].replace(os.sep, '/')}]]"
                idx = e['seq'] - 1
                before = ''.join(full_text[max(0, idx-3):idx])
                after = ''.join(full_text[idx+1:idx+4])
                ctx = ''
                if before: ctx += before + ' '
                ctx += '[' + ch + ']'
                if after: ctx += ' ' + after
                rows.append(f"| {page} | {e['seq']} | {img_link} | {e['confidence']:.2f} | {ctx} |")

            # Read existing content if note exists (only keep header/frontmatter)
            existing_rows = []
            if os.path.exists(note_path):
                with open(note_path, 'r', encoding='utf-8') as f:
                    existing = f.read()
                # Extract existing rows (skip header and separator)
                in_table = False
                for line in existing.splitlines():
                    if line.startswith('|') and '|---|---|' not in line and in_table:
                        existing_rows.append(line)
                    elif '|---|---|' in line:
                        in_table = True
                # Remove rows from this page to avoid dupes on re-submit
                existing_rows = [r for r in existing_rows if not r.startswith(f'| {page} |')]

            all_rows = existing_rows + rows
            table = "\n".join([
                f"---",
                f'char: "{ch}"',
                f'calligrapher: "{CALLIGRAPHER}"',
                f'source: "{SOURCE_TEXT}"',
                f"---",
                f"",
                f"# {ch}",
                f"",
                f"| 页面 | 序号 | 图片 | 置信度 | 上下文 |",
                f"|------|------|------|--------|--------|",
            ])
            if all_rows:
                table += "\n" + "\n".join(all_rows) + "\n"

            with open(note_path, 'w', encoding='utf-8') as f:
                f.write(table)

        # Mark as reviewed
        marker = os.path.join(PAGES_DIR, f"page_{page:03d}_reviewed.json")
        data = {'pages': [{'page': page, 'count': len(clean)}]}
        with open(marker, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Remove skipped marker if present (re-detect override)
        skipped_marker = os.path.join(PAGES_DIR, f"page_{page:03d}_skipped.json")
        if os.path.exists(skipped_marker):
            os.remove(skipped_marker)

        msg = f'已提交第{page}页，裁剪{len(char_entries)}字，录入字库{len(set(e["char"] for e in char_entries))}字'
        if skip_count:
            msg += f'，跳过{skip_count}个异常框'
        return jsonify({'ok': True, 'm': msg})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'ok': False, 'm': f'提交失败: {e}'})

def get_page_status(page):
    """Check page status: unprocessed / ready / submitted / pending / skipped"""
    skipped = os.path.exists(os.path.join(PAGES_DIR, f"page_{page:03d}_skipped.json"))
    if skipped:
        return "skipped"
    ocr = os.path.exists(os.path.join(PAGES_DIR, f"page_{page:03d}_ocr_results.json"))
    if not ocr:
        return "unprocessed"
    reviewed_path = os.path.join(PAGES_DIR, f"page_{page:03d}_reviewed.json")
    reviewed = os.path.exists(reviewed_path)
    if not reviewed:
        return "ready"
    # Check if corrected.json was modified after reviewed.json → pending
    corrected_path = os.path.join(PAGES_DIR, f"page_{page:03d}_corrected.json")
    if os.path.exists(corrected_path):
        corr_mtime = os.path.getmtime(corrected_path)
        rev_mtime = os.path.getmtime(reviewed_path)
        if corr_mtime > rev_mtime + 1:  # 1s tolerance for filesystem precision
            return "pending"
    return "submitted"

@app.route('/status')
def page_status():
    page = request.args.get('p', 24, type=int)
    status = get_page_status(page)
    count = 0
    if status in ("ready", "submitted"):
        raw, clean, mapping = load_clean(page)
        if clean:
            count = len(clean)
    return jsonify({'status': status, 'count': count, 'page': page})

@app.route('/run_page', methods=['POST'])
def run_page():
    try:
        req = request.json
        page = req['p']
        status = get_page_status(page)
        if status == "submitted":
            return jsonify({'ok': False, 'm': f'第{page}页已提交且无修改，不可重新检测'})

        # Remove skipped marker if present
        skipped_path = os.path.join(PAGES_DIR, f"page_{page:03d}_skipped.json")
        if os.path.exists(skipped_path):
            os.remove(skipped_path)

        # Run pipeline for this page via subprocess
        pipe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pipeline.py')
        result = subprocess.run(
            [sys.executable, pipe_path, str(page), '--no-correct'],
            capture_output=True, text=True, timeout=120,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        stdout = result.stdout[-500:] if result.stdout else ''
        stderr = result.stderr[-500:] if result.stderr else ''
        print(f"pipeline page {page} stdout: {stdout[:200]}")
        if stderr:
            print(f"pipeline page {page} stderr: {stderr[:200]}")

        # If pipeline returned non-zero → real failure
        if result.returncode != 0:
            return jsonify({'ok': False, 'm': f'检测失败: {stderr or stdout}'})
        # Pipeline succeeded; if no OCR file (0 chars), create empty one
        new_status = get_page_status(page)
        if new_status == "unprocessed":
            empty_path = os.path.join(PAGES_DIR, f"page_{page:03d}_ocr_results.json")
            with open(empty_path, 'w', encoding='utf-8') as f:
                json.dump([], f)

        return jsonify({'ok': True, 'm': f'第{page}页检测完成'})
    except subprocess.TimeoutExpired:
        return jsonify({'ok': False, 'm': '检测超时（>120s）'})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'ok': False, 'm': f'检测失败: {e}'})

@app.route('/redetect', methods=['POST'])
def redetect_page():
    try:
        req = request.json
        page = req['p']

        # Clear corrected.json (modifications)
        corr_path = os.path.join(PAGES_DIR, f"page_{page:03d}_corrected.json")
        if os.path.exists(corr_path):
            os.remove(corr_path)

        # Clear reviewed.json (submission marker)
        reviewed_path = os.path.join(PAGES_DIR, f"page_{page:03d}_reviewed.json")
        if os.path.exists(reviewed_path):
            os.remove(reviewed_path)

        # Clear skipped marker if present
        skipped_path = os.path.join(PAGES_DIR, f"page_{page:03d}_skipped.json")
        if os.path.exists(skipped_path):
            os.remove(skipped_path)

        # Clear cropped images for this page
        page_cropped_dir = os.path.join(CROPPED_DIR, CALLIGRAPHER, SOURCE_TEXT, f"page_{page:03d}")
        if os.path.exists(page_cropped_dir):
            import shutil
            shutil.rmtree(page_cropped_dir)

        # Clean Obsidian DB entries for this page
        base_rel = os.path.join(CALLIGRAPHER, SOURCE_TEXT)
        note_dir = os.path.join(CHAR_DB_DIR, base_rel)
        if os.path.exists(note_dir):
            for fname in os.listdir(note_dir):
                if not fname.endswith('.md'):
                    continue
                note_path = os.path.join(note_dir, fname)
                with open(note_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                # Remove rows for this page
                new_lines = []
                for line in content.splitlines():
                    if line.startswith(f'| {page} |'):
                        continue
                    new_lines.append(line)
                with open(note_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(new_lines) + '\n')

        # Drop cache
        drop_cache(page)

        # Run pipeline
        pipe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pipeline.py')
        result = subprocess.run(
            [sys.executable, pipe_path, str(page), '--no-correct'],
            capture_output=True, text=True, timeout=120,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        if result.returncode != 0:
            return jsonify({'ok': False, 'm': f'重检失败: {result.stderr[:200]}'})

        return jsonify({'ok': True, 'm': f'第{page}页重检完成'})
    except subprocess.TimeoutExpired:
        return jsonify({'ok': False, 'm': '重检超时（>120s）'})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'ok': False, 'm': f'重检失败: {e}'})

@app.route('/skip', methods=['POST'])
def skip_page():
    try:
        req = request.json
        page = req['p']
        marker = os.path.join(PAGES_DIR, f"page_{page:03d}_skipped.json")
        with open(marker, 'w', encoding='utf-8') as f:
            json.dump({'page': page, 'skipped': True}, f)
        return jsonify({'ok': True, 'm': f'已跳过第{page}页'})
    except Exception as e:
        return jsonify({'ok': False, 'm': f'跳过失败: {e}'})

@app.route('/shutdown', methods=['POST'])
def shutdown():
    import threading
    def _exit():
        import time
        time.sleep(0.3)
        os._exit(0)
    threading.Thread(target=_exit, daemon=True).start()
    return jsonify({'ok': True, 'm': '服务器即将退出'})

if __name__ == '__main__':
    url = f'http://127.0.0.1:5000/?p={get_last_page()}'
    print(url)
    app.run(host='127.0.0.1', port=5000, debug=False)
