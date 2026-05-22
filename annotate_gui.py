"""Gradio 网页校对工具：一览式全页图+表格+编辑"""
import sys, os, json, cv2, numpy as np
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gradio as gr
from config import PAGES_DIR

os.environ['RAPIDOCR_LOG_LEVEL'] = 'CRITICAL'

def load_page_data(page_num):
    corrected = os.path.join(PAGES_DIR, f"page_{page_num:03d}_corrected.json")
    ocr = os.path.join(PAGES_DIR, f"page_{page_num:03d}_ocr_results.json")
    if os.path.exists(corrected):
        with open(corrected, encoding='utf-8') as f:
            return json.load(f)
    if os.path.exists(ocr):
        with open(ocr, encoding='utf-8') as f:
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

def make_annotated_image(data, page_img, selected=0):
    img = page_img.copy()
    h, w = img.shape[:2]
    # Scale down if too large for display
    scale = 1
    max_dim = 1600
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        img = cv2.resize(img, None, fx=scale, fy=scale)
    for i, d in enumerate(data):
        x = int(d['x'] * scale)
        y = int(d['y'] * scale)
        bw = int(d['w'] * scale)
        bh = int(d['h'] * scale)
        text = d.get('corrected_text', d.get('text', ''))
        if i == selected:
            color, thick = (0, 255, 0), 3
        elif d.get('auto_corrected'):
            color, thick = (255, 200, 0), 2
        elif d.get('manual_corrected'):
            color, thick = (0, 200, 255), 2
        else:
            color, thick = (150, 150, 150), 1
        cv2.rectangle(img, (x, y), (x+bw, y+bh), color, thick)
        # Show index + text
        label = f"{i+1}.{text}"
        cv2.putText(img, label, (x+2, y+14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

def build_table(data):
    """Build a list of [idx, col, row, text, ocr, status, x, y, w, h]"""
    rows = []
    for i, d in enumerate(data):
        text = d.get('corrected_text', d.get('text', ''))
        ocr = d.get('text', '')
        if d.get('manual_corrected'):
            status = "✅ 手动"
        elif d.get('auto_corrected'):
            status = "🤖 自动"
        elif len(ocr) > 0 and len(ocr) < 3:
            status = "⚠️ 待校"
        else:
            status = "✓"
        rows.append([i+1, d['col'], d['row'], text, ocr, status,
                     d['x'], d['y'], d['w'], d['h']])
    return rows

# === Gradio App ===
def refresh_page(page_num, selected_idx=0):
    data = load_page_data(int(page_num))
    if data is None:
        return None, None, "页面未找到", [], ""
    page_img = load_img(int(page_num))
    if page_img is None:
        return None, None, "图片未找到", [], ""
    selected_idx = max(0, min(selected_idx, len(data)-1))
    annotated = make_annotated_image(data, page_img, selected_idx)
    table = build_table(data)
    d = data[selected_idx]
    detail_text = d.get('corrected_text', d.get('text', ''))
    detail_ocr = d.get('text', '')
    detail = f"**序号 {selected_idx+1}** | 列{d['col']} 行{d['row']}\n"
    detail += f"当前文字: 「{detail_text}」  OCR原文: 「{detail_ocr}」\n"
    detail += f"坐标: x={d['x']} y={d['y']} w={d['w']} h={d['h']}"
    return annotated, table, f"第{page_num}页 · {len(data)}字", selected_idx, detail

def select_char(evt: gr.SelectData, page_num, table_data):
    """When user clicks a row in the table"""
    if evt.index is None:
        return page_num, 0, ""
    row_idx = evt.index[0]
    data = load_page_data(int(page_num))
    if data is None or row_idx >= len(data):
        return page_num, 0, ""
    d = data[row_idx]
    detail = f"**序号 {row_idx+1}** | 列{d['col']} 行{d['row']}\n"
    detail += f"当前文字: 「{d.get('corrected_text', d.get('text', ''))}」\n"
    detail += f"OCR原文: 「{d.get('text', '')}」\n"
    detail += f"坐标: x={d['x']} y={d['y']} w={d['w']} h={d['h']}"
    return row_idx, row_idx, detail

def save_and_refresh(page_num, selected_idx, new_text, new_x, new_y, new_w, new_h):
    path = os.path.join(PAGES_DIR, f"page_{page_num:03d}_corrected.json")
    ocr_path = os.path.join(PAGES_DIR, f"page_{page_num:03d}_ocr_results.json")
    if os.path.exists(path):
        src_path = path
    else:
        src_path = ocr_path
    with open(src_path, encoding='utf-8') as f:
        data = json.load(f)
    idx = int(selected_idx)
    if 0 <= idx < len(data):
        d = data[idx]
        old = d.get('corrected_text', d.get('text', ''))
        if new_text != old:
            d['corrected_text'] = new_text
            d['manual_corrected'] = True
        d['x'] = int(new_x)
        d['y'] = int(new_y)
        d['w'] = int(new_w)
        d['h'] = int(new_h)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    page_img = load_img(int(page_num))
    annotated = make_annotated_image(data, page_img, idx)
    table = build_table(data)
    d = data[idx]
    detail = f"**序号 {idx+1}** | 列{d['col']} 行{d['row']}\n"
    detail += f"当前文字: 「{d.get('corrected_text', d.get('text', ''))}」\n"
    detail += f"OCR原文: 「{d.get('text', '')}」\n"
    detail += f"坐标: x={d['x']} y={d['y']} w={d['w']} h={d['h']}"
    msg = f"✅ 字 {idx+1} 已保存"
    return annotated, table, msg, selected_idx, detail

def move_prev(page_num, selected_idx):
    return refresh_page(int(page_num), int(selected_idx)-1)

def move_next(page_num, selected_idx):
    return refresh_page(int(page_num), int(selected_idx)+1)

# === Build UI ===
with gr.Blocks(title="字帖校对工具") as demo:
    gr.Markdown("## 📜 字帖校对 · 点击表格行选中 → 下方编辑 → 保存")

    page_num_state = gr.State(24)
    selected_state = gr.State(0)

    with gr.Row():
        page_input = gr.Number(label="页码", value=24, minimum=1, maximum=300, step=1, scale=1)
        load_btn = gr.Button("📂 加载", variant="primary", scale=1)
        status_msg = gr.Textbox(label="状态", interactive=False, scale=3)

    with gr.Row():
        with gr.Column(scale=3):
            img_out = gr.Image(label="全页图（灰=未校 黄=自动校 绿=选中 蓝=手动校）", height=750)

        with gr.Column(scale=2):
            table_out = gr.Dataframe(
                headers=["#", "列", "行", "文字", "OCR原文", "状态", "X", "Y", "W", "H"],
                label="字符列表（点击行选中）",
                interactive=False,
            )

    with gr.Row():
        detail_out = gr.Markdown(label="选中详情", value="请加载页面")

    with gr.Row():
        edit_text = gr.Textbox(label="文字修改", scale=2)
        edit_x = gr.Number(label="X", precision=0, scale=1)
        edit_y = gr.Number(label="Y", precision=0, scale=1)
        edit_w = gr.Number(label="W", precision=0, scale=1)
        edit_h = gr.Number(label="H", precision=0, scale=1)

    with gr.Row():
        prev_btn = gr.Button("◀ 上一个")
        next_btn = gr.Button("下一个 ▶")
        save_btn = gr.Button("💾 保存修改", variant="primary")
        save_msg = gr.Textbox(label="保存状态", interactive=False, scale=2)

    # Events
    def on_load(page_num):
        page_num = int(page_num)
        annotated, table, msg, sel, detail = refresh_page(page_num, 0)
        return annotated, table, msg, sel, detail, page_num, 0, "", 0, 0, 0, 0

    load_btn.click(
        fn=on_load,
        inputs=[page_input],
        outputs=[img_out, table_out, status_msg, selected_state, detail_out,
                 page_num_state, selected_state,
                 edit_text, edit_x, edit_y, edit_w, edit_h]
    )

    def on_table_select(evt: gr.SelectData, page_num, _table_data):
        """Click on table row -> update selected"""
        if evt.index is None:
            return 0, "", 0, 0, 0, 0
        row_idx = evt.index[0]
        data = load_page_data(int(page_num))
        if data is None or row_idx >= len(data):
            return 0, "", 0, 0, 0, 0
        d = data[row_idx]
        text = d.get('corrected_text', d.get('text', ''))
        detail = f"**序号 {row_idx+1}** | 列{d['col']} 行{d['row']}"
        detail += f" | 文字: 「{text}」 | OCR: 「{d.get('text','')}」"
        detail += f" | 坐标: ({d['x']},{d['y']}) {d['w']}×{d['h']}"
        return row_idx, detail, text, d['x'], d['y'], d['w'], d['h']

    table_out.select(
        fn=on_table_select,
        inputs=[page_num_state, table_out],
        outputs=[selected_state, detail_out, edit_text, edit_x, edit_y, edit_w, edit_h]
    )

    def on_save(page_num, selected_idx, text, x, y, w, h):
        return save_and_refresh(int(page_num), int(selected_idx), text, x, y, w, h)

    save_btn.click(
        fn=on_save,
        inputs=[page_num_state, selected_state, edit_text, edit_x, edit_y, edit_w, edit_h],
        outputs=[img_out, table_out, save_msg, selected_state, detail_out]
    )

    def on_prev_next(page_num, selected_idx, direction):
        idx = int(selected_idx) + direction
        data = load_page_data(int(page_num))
        if data is None:
            return 0, "", 0, 0, 0, 0, "", 0
        idx = max(0, min(idx, len(data)-1))
        d = data[idx]
        text = d.get('corrected_text', d.get('text', ''))
        detail = f"**序号 {idx+1}** | 列{d['col']} 行{d['row']}"
        detail += f" | 文字: 「{text}」 | OCR: 「{d.get('text','')}」"
        detail += f" | 坐标: ({d['x']},{d['y']}) {d['w']}×{d['h']}"
        return idx, detail, text, d['x'], d['y'], d['w'], d['h'], ""

    prev_btn.click(
        fn=lambda p, s: on_prev_next(p, s, -1),
        inputs=[page_num_state, selected_state],
        outputs=[selected_state, detail_out, edit_text, edit_x, edit_y, edit_w, edit_h, save_msg]
    )
    next_btn.click(
        fn=lambda p, s: on_prev_next(p, s, 1),
        inputs=[page_num_state, selected_state],
        outputs=[selected_state, detail_out, edit_text, edit_x, edit_y, edit_w, edit_h, save_msg]
    )

    # When selected_state changes, refresh the image highlight
    def on_selected_change(page_num, selected_idx):
        data = load_page_data(int(page_num))
        if data is None:
            return None, None, "无数据"
        page_img = load_img(int(page_num))
        if page_img is None:
            return None, None, "无图片"
        idx = int(selected_idx)
        idx = max(0, min(idx, len(data)-1))
        annotated = make_annotated_image(data, page_img, idx)
        table = build_table(data)
        return annotated, table, f"已跳转到字 {idx+1}"

    selected_state.change(
        fn=on_selected_change,
        inputs=[page_num_state, selected_state],
        outputs=[img_out, table_out, status_msg]
    )

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860, share=True)
