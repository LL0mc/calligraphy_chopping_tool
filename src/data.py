"""Data loading utilities for review server."""
import os, json, cv2, base64
from config import PAGES_DIR

_clean_cache = {}
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
