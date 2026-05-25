"""Composition layout engine: renders character grid with various paper/text effects."""
import os, re, math
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from config import CROPPED_DIR, CALLIGRAPHER, SOURCE_TEXT

_FONT_PATHS = [
    r'C:\Windows\Fonts\simsun.ttc',
    r'C:\Windows\Fonts\msyh.ttc',
    r'C:\Windows\Fonts\yahei.ttf',
]
_PUNCTUATION = set('，。、；：？！,.;:?!')
COLORS = {
    'black': (0, 0, 0, 255),
    'white': (255, 255, 255, 255),
    'ink_blue': (26, 42, 74, 255),
    'gold': (218, 185, 72, 255),
    'red': (204, 51, 51, 255),
}

def _load_font(size):
    for path in _FONT_PATHS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue
    return ImageFont.load_default()

def _load_char_image(page_dir, filename):
    path = os.path.join(CROPPED_DIR, CALLIGRAPHER, SOURCE_TEXT, page_dir, filename)
    if not os.path.exists(path):
        return None
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    _, binary = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    binary = cv2.bitwise_not(binary)
    return binary

def _binary_to_rgba(binary_img, text_color):
    h, w = binary_img.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    dark = (binary_img < 128).sum()
    light = (binary_img >= 128).sum()
    ink = binary_img < 128 if dark < light else binary_img >= 128
    rgba[ink] = text_color
    rgba[~ink] = (0, 0, 0, 0)
    return Image.fromarray(rgba, 'RGBA')

def _make_fallback_char(char, size, text_color):
    font = _load_font(int(size * 0.85))
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), char, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) // 2 - bbox[0]
    y = (size - th) // 2 - bbox[1]
    draw.text((x, y), char, font=font, fill=text_color)
    return img

def _is_punctuation(ch):
    return ch in _PUNCTUATION

def _make_punctuation_overlay(char, cell_size, text_color):
    overlay_sz = max(12, int(cell_size * 0.45))
    font = _load_font(int(overlay_sz * 0.70))
    img = Image.new('RGBA', (overlay_sz, overlay_sz), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), char, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = max(2, int(overlay_sz * 0.12))
    x = overlay_sz - tw - pad - bbox[0]
    y = overlay_sz - th - pad - bbox[1]
    draw.text((x, y), char, font=font, fill=text_color)
    return img, overlay_sz

def _render_gold_fleck_bg(w, h):
    base = (252, 249, 240, 255)
    bg = Image.new('RGBA', (w, h), base)
    draw = ImageDraw.Draw(bg)
    rng = np.random.RandomState(42)
    n = max(8, int(w * h / 6000))
    for _ in range(n):
        cx = rng.randint(0, max(1, w))
        cy = rng.randint(0, max(1, h))
        pts = []
        npts = rng.randint(5, 10)
        radius = rng.randint(5, 18)
        for j in range(npts):
            angle = 2 * math.pi * j / npts + rng.uniform(-0.3, 0.3)
            r = radius * rng.uniform(0.4, 1.0)
            pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
        r = min(255, 200 + rng.randint(0, 55))
        g = min(255, 165 + rng.randint(0, 40))
        b = min(255, 20 + rng.randint(0, 25))
        a = rng.randint(100, 220)
        draw.polygon(pts, fill=(r, g, b, a))
        if rng.random() > 0.35:
            sr = min(255, r + 45)
            sg = min(255, g + 40)
            sb = min(255, b + 15)
            scale = 0.5
            inner = [(cx + scale*(px-cx), cy + scale*(py-cy)) for px,py in pts]
            draw.polygon(inner, fill=(sr, sg, sb, min(255, a + 20)))
    return bg

def _render_grass_bg(w, h):
    base = (221, 208, 184, 255)
    bg = Image.new('RGBA', (w, h), base)
    draw = ImageDraw.Draw(bg)
    rng = np.random.RandomState(42)
    n = max(40, int(w * h / 3000))
    for _ in range(n):
        x1 = rng.randint(0, max(1, w))
        y1 = rng.randint(0, max(1, h))
        angle = rng.choice([75, 165, 30, 120])
        length = rng.randint(50, 200)
        x2 = x1 + int(length * math.cos(math.radians(angle)))
        y2 = y1 + int(length * math.sin(math.radians(angle)))
        a = rng.randint(25, 60)
        r = 120 + rng.randint(-20, 30)
        g = 80 + rng.randint(-20, 20)
        b = 40 + rng.randint(-10, 15)
        draw.line([(x1, y1), (x2, y2)], fill=(r, g, b, a), width=rng.randint(3, 6))
    return bg

def render_composition(chars, variants, params):
    char_size = params.get('char_size', 100)
    gap = params.get('gap', 16)
    direction = params.get('direction', 'h_ltr')
    cols_param = params.get('cols', 5)
    text_color_key = params.get('text_color', 'black')
    text_color = COLORS.get(text_color_key, (0, 0, 0, 255))
    bg_color_key = params.get('bg_color', 'beige')

    if not chars:
        return Image.new('RGBA', (int(gap * 2), int(gap * 2)), (245, 240, 232, 255)), 100, 1

    # --- Phase 1: parse chars into items (accounting for punctuation, spaces, newlines) ---
    # items: list of dicts with type: 'char'|'space'|'punct'|'nl'
    items = []
    for i, ch in enumerate(chars):
        if ch == '\n':
            items.append({'type': 'nl', 'orig_idx': i})
        elif ch == ' ':
            items.append({'type': 'space', 'orig_idx': i})
        elif _is_punctuation(ch):
            items.append({'type': 'punct', 'char': ch, 'orig_idx': i})
        else:
            items.append({'type': 'char', 'char': ch, 'orig_idx': i})

    # --- Phase 2: load binaries at original size (never scaled) ---
    loaded = {}  # orig_idx -> binary or None
    max_char_w, max_char_h = 0, 0
    for item in items:
        if item['type'] != 'char':
            continue
        oi = item['orig_idx']
        v = variants.get(oi)
        binary = None
        if v and v.get('page_dir') and v.get('filename'):
            binary = _load_char_image(v['page_dir'], v['filename'])
        loaded[oi] = binary
        if binary is not None:
            h, w = binary.shape
            max_char_w = max(max_char_w, w)
            max_char_h = max(max_char_h, h)

    # Cell = max char dim × 1.15 — always big enough, never overflow
    if max_char_w > 0 and max_char_h > 0:
        use_cell_size = int(max(max_char_w, max_char_h) * 1.15)
    else:
        use_cell_size = char_size

    # --- Phase 3: compute grid layout (with newline / auto-wrap support) ---
    is_vert = direction.startswith('v')
    is_rtl = 'rtl' in direction

    # First pass: simulate layout to determine grid dimensions
    seg_col = 0
    seg_row = 0
    col_heights = [0]  # number of rows per column
    has_nl = any(it['type'] == 'nl' for it in items)

    for item in items:
        t = item['type']
        if t == 'nl':
            col_heights.append(0)
            seg_col += 1
            seg_row = 0
        elif t == 'punct':
            continue
        else:
            if not has_nl and is_vert and seg_row >= cols_param:
                col_heights.append(0)
                seg_col += 1
                seg_row = 0
            if not has_nl and not is_vert and seg_row >= cols_param:
                col_heights.append(0)
                seg_col += 1
                seg_row = 0
            col_heights[seg_col] = max(col_heights[seg_col], seg_row + 1)
            seg_row += 1

    n_cols = len(col_heights)
    max_rows = max(col_heights) if col_heights else 1

    left_margin = gap * 2
    if is_vert:
        canvas_w = left_margin + n_cols * (use_cell_size + gap) + gap
        canvas_h = gap + max_rows * (use_cell_size + gap) + gap
    else:
        canvas_w = left_margin + cols_param * (use_cell_size + gap) + gap
        canvas_h = gap + n_cols * (use_cell_size + gap) + gap

    # Create canvas with proper background
    if bg_color_key == 'gold_fleck':
        canvas = _render_gold_fleck_bg(int(canvas_w), int(canvas_h))
    elif bg_color_key == 'grass':
        canvas = _render_grass_bg(int(canvas_w), int(canvas_h))
    else:
        BG_COLORS = {
            'white': (255, 255, 255, 255),
            'black': (0, 0, 0, 255),
            'beige': (245, 240, 232, 255),
            'red': (200, 48, 48, 255),
        }
        bg_rgba = BG_COLORS.get(bg_color_key, (245, 240, 232, 255))
        canvas = Image.new('RGBA', (int(canvas_w), int(canvas_h)), bg_rgba)

    # Second pass: compute positions and compose (at full resolution)
    seg_col = 0
    seg_row = 0

    for item in items:
        t = item['type']
        if t == 'nl':
            seg_col += 1
            seg_row = 0
            continue
        elif t == 'punct':
            target_row = seg_row - 1
            target_col = seg_col
            if target_row < 0 and target_col > 0:
                target_col = seg_col - 1
                target_row = col_heights[target_col] - 1
            if target_row >= 0:
                if is_vert:
                    col_idx = n_cols - 1 - target_col if is_rtl else target_col
                    cx = int(left_margin + col_idx * (use_cell_size + gap))
                    cy = int(gap + target_row * (use_cell_size + gap))
                else:
                    trow = target_row // cols_param
                    tcol = target_row % cols_param
                    if is_rtl:
                        tcol = cols_param - 1 - tcol
                    cx = int(left_margin + tcol * (use_cell_size + gap))
                    cy = int(gap + target_col * (use_cell_size + gap))
                overlay, o_sz = _make_punctuation_overlay(item['char'], use_cell_size, text_color)
                ox = int(cx + use_cell_size - o_sz)
                oy = int(cy + use_cell_size - o_sz)
                canvas.paste(overlay, (ox, oy), overlay)
            continue

        # Compute cell position
        if is_vert:
            col_idx = n_cols - 1 - seg_col if is_rtl else seg_col
            cx = int(left_margin + col_idx * (use_cell_size + gap))
            cy = int(gap + seg_row * (use_cell_size + gap))
        else:
            row_idx = seg_row // cols_param
            col_idx = seg_row % cols_param
            if is_rtl:
                col_idx = cols_param - 1 - col_idx
            row_idx = seg_col
            cx = int(left_margin + col_idx * (use_cell_size + gap))
            cy = int(gap + row_idx * (use_cell_size + gap))

        if t == 'space':
            seg_row += 1
            continue

        # Render char at original pixel size, centered in full-res cell
        oi = item['orig_idx']
        binary = loaded.get(oi)
        if binary is not None:
            char_img = _binary_to_rgba(binary, text_color)
        else:
            char_img = _make_fallback_char(item['char'], int(use_cell_size), text_color)

        px = cx + int((use_cell_size - char_img.width) / 2)
        py = cy + int((use_cell_size - char_img.height) / 2)
        canvas.paste(char_img, (px, py), char_img)

        seg_row += 1

    return canvas, use_cell_size, n_cols
