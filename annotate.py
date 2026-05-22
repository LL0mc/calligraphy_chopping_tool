"""交互校对工具：浏览字符、修正文字、微调框位置"""
import sys, os, json, cv2, numpy as np
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import PAGES_DIR, CHARACTERS_DIR


def load_page_data(page_num):
    """加载页面的校正JSON（如果有校正则用它，否则用原始OCR JSON）"""
    corrected_path = os.path.join(PAGES_DIR, f"page_{page_num:03d}_corrected.json")
    ocr_path = os.path.join(PAGES_DIR, f"page_{page_num:03d}_ocr_results.json")

    if os.path.exists(corrected_path):
        path = corrected_path
    elif os.path.exists(ocr_path):
        path = ocr_path
    else:
        raise FileNotFoundError(f"第{page_num}页未找到OCR结果")

    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    return data, path


def show_char_image(page_num, col, row):
    """显示字符裁剪图片"""
    char_dir = os.path.join(CHARACTERS_DIR, f"page_{page_num:03d}")
    img_path = os.path.join(char_dir, f"page{page_num:03d}_col{col:02d}_row{row:02d}.png")
    if not os.path.exists(img_path):
        return None
    img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    return img


def annotate_page(page_num):
    """校对一页的字符"""
    data, data_path = load_page_data(page_num)
    total = len(data)
    idx = 0
    modified = False

    while 0 <= idx < total:
        entry = data[idx]
        col, row = entry['col'], entry['row']
        text = entry.get('corrected_text', entry['text'])
        conf = entry['confidence']
        x, y, w, h = entry['x'], entry['y'], entry['w'], entry['h']

        # Load image
        img = show_char_image(page_num, col, row)

        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"{'='*60}")
        print(f"第{page_num}页 | 列{col} 行{row} | {idx+1}/{total}")
        print(f"{'='*60}")

        if img is not None:
            # Scale up for display
            scale = 3
            disp = cv2.resize(img, (img.shape[1]*scale, img.shape[0]*scale),
                              interpolation=cv2.INTER_NEAREST)
            cv2.imshow(f"Page {page_num} Col {col} Row {row}", disp)
            cv2.waitKey(1)

        print(f"OCR文本: 「{entry['text']}」  (置信度: {conf:.2f})")
        auto = entry.get('auto_corrected', False)
        if auto:
            print(f"自动校正: 「{text}」")
        else:
            print(f"当前文字: 「{text}」")
        print(f"位置: x={x} y={y} w={w} h={h}")
        print(f"\n操作: [Enter]接受  [数字]改字  [l/r/u/d+像素]调框")
        print(f"      [p]上一字  [n]下一字  [s]保存  [q]退出")

        inp = input("> ").strip()

        # Close image window
        cv2.destroyAllWindows()

        if inp == '' or inp == 'n':
            idx += 1
        elif inp == 'p':
            idx -= 1
        elif inp == 'q':
            if modified:
                save = input("有未保存的修改，是否保存？(y/n): ").strip().lower()
                if save == 'y':
                    save_data(data, data_path)
            print("退出校对")
            break
        elif inp == 's':
            save_data(data, data_path)
            modified = False
            print("已保存。")
            input("按Enter继续...")
        elif inp.startswith('l') or inp.startswith('r') or inp.startswith('u') or inp.startswith('d'):
            # Adjust box: l20 = left expand 20px, r10 = right expand 10px
            try:
                direction = inp[0]
                pixels = int(inp[1:]) if len(inp) > 1 else 10
                if direction == 'l':
                    entry['x'] = max(0, x - pixels)
                    entry['w'] = w + pixels
                elif direction == 'r':
                    entry['w'] = w + pixels
                elif direction == 'u':
                    entry['y'] = max(0, y - pixels)
                    entry['h'] = h + pixels
                elif direction == 'd':
                    entry['h'] = h + pixels
                modified = True
                print(f"框已调整")
            except ValueError:
                print("格式: l/r/u/d+像素数，如 l20")
            input("按Enter继续...")
        else:
            # Assume it's the corrected text
            if inp:
                entry['corrected_text'] = inp
                entry['auto_corrected'] = False
                entry['manual_corrected'] = True
                modified = True
                print(f"文字已修改为: 「{inp}」")
                input("按Enter继续...")
            idx += 1

    cv2.destroyAllWindows()
    if modified:
        save = input("校对完成，是否保存？(y/n): ").strip().lower()
        if save == 'y':
            save_data(data, data_path)
    print(f"第{page_num}页校对完成")


def save_data(data, path):
    """保存校对结果"""
    # Save as corrected file if original was raw OCR
    if '_corrected' not in path and '_annotated' not in path:
        path = path.replace('.json', '_annotated.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"已保存到: {path}")


def batch_correct(pages):
    """批量校对多个页面"""
    for page in pages:
        print(f"\n准备校对第{page}页...")
        input("按Enter开始...")
        annotate_page(page)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="交互校对工具")
    parser.add_argument("pages", nargs="+", type=int, help="页码（1-based）")
    args = parser.parse_args()
    batch_correct(args.pages)
