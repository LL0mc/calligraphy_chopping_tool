"""Composition layout engine: renders character grid with various paper/text effects."""
import os, re, math
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from config import CROPPED_DIR, CALLIGRAPHER, SOURCE_TEXT

# Font paths for punctuation and fallback
_FONT_PATHS = [
    r'C:\Windows\Fonts\simsun.ttc',
    r'C:\Windows\Fonts\msyh.ttc',
    r'C:\Windows\Fonts\yahei.ttf',
]
_PUNCTUATION = set('，。、；：？！,.;:?!')

# Text color presets (RGBA)
COLORS = {
    'black': (0, 0, 0, 255),
    'white': (255, 255, 255, 255),
    'ink_blue': (26, 42, 74, 255),
    'gold': (201, 168, 76, 255),
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
    ink = binary_img < 128
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

def _make_punctuation_overlay(char, size, text_color):
    font = _load_font(int(size * 0.35))
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), char, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = size - tw - 2 - bbox[0]
    y = size - th - 1 - bbox[1]
    draw.text((x, y), char, font=font, fill=text_color)
    return img

def _apply_metallic_overlay(img):
    arr = np.array(img)
    h, w = arr.shape[:2]
    overlay = np.zeros_like(arr)
    for y in range(h):
        t = y / h
        brightness = int(80 + 140 * (1 - abs(t - 0.3) * 1.8))
        brightness = max(100, min(255, brightness))
        overlay[y, :, :3] = [brightness, brightness, brightness]
        overlay[y, :, 3] = 60
    overlay_img = Image.fromarray(overlay, 'RGBA')
    return Image.alpha_composite(img, overlay_img)

def _get_char_size_and_padding(chars_len, cols, direction, cell_size, gap):
    if direction.startswith('h'):
        rows = math.ceil(chars_len / cols)
        w = cols * (cell_size + gap) + gap
        h = rows * (cell_size + gap) + gap
    else:
        effective_cols = math.ceil(chars_len / cols)
        w = effective_cols * (cell_size + gap) + gap
        h = cols * (cell_size + gap) + gap
    return w, h

def _get_cell_pos(index, cols, direction, cell_size, gap):
    if direction.startswith('h'):
        row = index // cols
        col = index % cols
        if 'rtl' in direction:
            col = cols - 1 - col
        x = gap + col * (cell_size + gap)
        y = gap + row * (cell_size + gap)
    else:
        col = index // cols
        row = index % cols
        if 'rtl' in direction:
            col = len(range)  # calculated differently
        x = gap + col * (cell_size + gap)
        y = gap + row * (cell_size + gap)
    return int(x), int(y)

def render_composition(chars, variants, params):
    """
    chars: list of str (each character)
    variants: dict of {index: {'page_dir': str, 'filename': str} or None}
    params: {
        'cols': int,                 # chars per row (horizontal) or per column (vertical)
        'direction': str,            # 'h_ltr' | 'h_rtl' | 'v_ltr' | 'v_rtl'
        'text_color': str,           # color key
        'char_size': int,            # px per cell
        'gap': int,                  # px between cells
    }
    Returns: PIL.Image (RGBA)
    """
    char_size = params.get('char_size', 100)
    gap = params.get('gap', 16)
    direction = params.get('direction', 'h_ltr')
    cols = params.get('cols', 5)
    text_color_key = params.get('text_color', 'black')
    text_color = COLORS.get(text_color_key, (0, 0, 0, 255))

    # Remove punctuation from layout; they'll be overlaid on previous char
    layout_chars = []
    punct_map = {}  # index -> punctuation char to overlay
    i = 0
    while i < len(chars):
        ch = chars[i]
        if ch == ' ':
            layout_chars.append(' ')
            i += 1
        elif _is_punctuation(ch):
            if layout_chars:
                punct_map[len(layout_chars) - 1] = ch
            i += 1
        else:
            layout_chars.append(ch)
            i += 1

    total = len(layout_chars)
    if total == 0:
        return Image.new('RGBA', (200, 200), (0, 0, 0, 0))

    # Calculate canvas size
    if direction.startswith('h'):
        rows = math.ceil(total / cols)
        canvas_w = cols * (char_size + gap) + gap
        canvas_h = rows * (char_size + gap) + gap
    else:
        effective_cols = math.ceil(total / cols)
        canvas_w = effective_cols * (char_size + gap) + gap
        canvas_h = cols * (char_size + gap) + gap

    canvas = Image.new('RGBA', (int(canvas_w), int(canvas_h)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # Pre-load all character images
    loaded = {}
    for idx, ch in enumerate(layout_chars):
        if ch == ' ':
            loaded[idx] = None
            continue
        v = variants.get(idx)
        if v and v.get('page_dir') and v.get('filename'):
            binary = _load_char_image(v['page_dir'], v['filename'])
            if binary is not None:
                loaded[idx] = _binary_to_rgba(binary, text_color)
            else:
                loaded[idx] = None
        else:
            loaded[idx] = None

    # For metallic text, apply gradient overlay
    is_metallic = text_color_key == 'metallic'
    actual_text_color = COLORS.get('gold', (201, 168, 76, 255)) if is_metallic else text_color

    # Compose layout
    for idx, ch in enumerate(layout_chars):
        if direction.startswith('h'):
            row = idx // cols
            col = idx % cols
            if 'rtl' in direction:
                col = cols - 1 - col
        else:
            col = idx // cols
            row = idx % cols
            if 'rtl' in direction:
                effective_cols = math.ceil(total / cols)
                col = effective_cols - 1 - col

        cx = int(gap + col * (char_size + gap))
        cy = int(gap + row * (char_size + gap))

        char_img = loaded.get(idx)
        if char_img is None:
            if ch == ' ':
                continue
            if is_metallic:
                char_img = _make_fallback_char(ch, char_size, actual_text_color)
            else:
                char_img = _make_fallback_char(ch, char_size, text_color)
        else:
            if is_metallic:
                char_img = _binary_to_rgba(
                    np.array(Image.fromarray(np.array(char_img)[:, :, 3])),
                    actual_text_color
                )

        # Resize to fit cell
        cw, ch_h = char_img.size
        scale = min((char_size - 4) / max(cw, ch_h, 1), 1.0)
        new_w = max(1, int(cw * scale))
        new_h = max(1, int(ch_h * scale))
        char_img = char_img.resize((new_w, new_h), Image.LANCZOS)

        if is_metallic:
            char_img = _apply_metallic_overlay(char_img)

        px = cx + (char_size - new_w) // 2
        py = cy + (char_size - new_h) // 2
        canvas.paste(char_img, (px, py), char_img)

        # Punctuation overlay
        if idx in punct_map:
            punct_char = punct_map[idx]
            overlay = _make_punctuation_overlay(punct_char, char_size, text_color)
            canvas.paste(overlay, (cx, cy), overlay)

    return canvas
