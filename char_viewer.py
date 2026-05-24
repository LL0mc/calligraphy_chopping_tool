import os, re, io
import cv2
import numpy as np
from flask import Flask, render_template, jsonify, request, send_file
from config import CROPPED_DIR

app = Flask(__name__)

CALLIGRAPHER = '吴玉生'
SOURCE_TEXT = '红楼梦'

# ---------- Index ----------
_index = None

def build_index():
    global _index
    _index = {}
    base = os.path.join(CROPPED_DIR, CALLIGRAPHER, SOURCE_TEXT)
    if not os.path.exists(base):
        return _index
    for page_dir in sorted(os.listdir(base)):
        page_path = os.path.join(base, page_dir)
        if not os.path.isdir(page_path):
            continue
        m = re.match(r'page_(\d+)', page_dir)
        if not m:
            continue
        page_num = int(m.group(1))
        for fname in sorted(os.listdir(page_path)):
            if not fname.endswith('.png'):
                continue
            m2 = re.match(r'(\d+)_(.+?)\.png', fname)
            if not m2:
                continue
            seq = int(m2.group(1))
            char = m2.group(2)
            if char not in _index:
                _index[char] = []
            _index[char].append({
                'page': page_num,
                'seq': seq,
                'filename': fname,
                'page_dir': page_dir,
            })
    return _index

# ---------- Image Processing ----------
def tight_crop(img):
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = cv2.findNonZero(thresh)
    if coords is None:
        return img
    x, y, w, h = cv2.boundingRect(coords)
    pad = 1
    x = max(0, x - pad)
    y = max(0, y - pad)
    w = min(img.shape[1] - x, w + pad * 2)
    h = min(img.shape[0] - y, h + pad * 2)
    return img[y:y+h, x:x+w]

def enhance_image(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
    enhanced = clahe.apply(gray)
    blurred = cv2.GaussianBlur(enhanced, (0, 0), 1.5)
    sharpened = cv2.addWeighted(enhanced, 1.8, blurred, -0.8, 0)
    return sharpened

def binary_image(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return cv2.bitwise_not(binary)

def bilateral_image(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()
    return cv2.bilateralFilter(gray, 9, 75, 75)

# ---------- Routes ----------
@app.route('/')
def index():
    return render_template('char_viewer.html')

@app.route('/api/refresh')
def refresh():
    build_index()
    return jsonify({'count': len(_index)})

@app.route('/api/search')
def search():
    q = request.args.get('q', '').strip()
    if _index is None:
        build_index()
    if not q:
        return jsonify([{'char': c, 'count': len(v)} for c, v in sorted(_index.items())])
    results = []
    for char in sorted(_index.keys()):
        if q in char:
            results.append({'char': char, 'count': len(_index[char])})
    return jsonify(results)

@app.route('/api/char/<char>')
def get_char(char):
    if _index is None:
        build_index()
    variants = _index.get(char, [])
    return jsonify({'char': char, 'count': len(variants), 'variants': variants})

@app.route('/api/image/<path:img_path>')
def serve_image(img_path):
    mode = request.args.get('mode', 'original')
    invert = request.args.get('invert', '0') == '1'
    target_size = request.args.get('size', None)

    full_path = os.path.join(CROPPED_DIR, CALLIGRAPHER, SOURCE_TEXT, img_path)
    if not os.path.exists(full_path):
        return 'Image not found', 404

    img = cv2.imdecode(np.fromfile(full_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return 'Failed to read image', 500

    img = tight_crop(img)

    if mode == 'enhanced':
        processed = enhance_image(img)
        processed = cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)
    elif mode == 'bilateral':
        processed = bilateral_image(img)
        processed = cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)
    elif mode == 'binary':
        processed = binary_image(img)
        processed = cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)
    else:
        processed = img.copy()

    if invert:
        processed = cv2.bitwise_not(processed)

    if target_size:
        try:
            s = int(target_size)
            h, w = processed.shape[:2]
            scale = s / max(h, w)
            if scale > 1:
                new_w = int(w * scale)
                new_h = int(h * scale)
                processed = cv2.resize(processed, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
        except:
            pass

    ret, buf = cv2.imencode('.png', processed)
    if not ret:
        return 'Encoding failed', 500

    return send_file(io.BytesIO(buf.tobytes()), mimetype='image/png')

# Build index on startup
build_index()
print(f'Char index built: {len(_index)} characters')

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5001, debug=True)
