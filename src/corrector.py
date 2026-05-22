"""OCR文字校对模块：基于诗词原文自动校正"""
import json, os, sys
from difflib import SequenceMatcher


def load_poems(path="data/poems.json"):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def get_poem_texts_for_page(poems_data, page_num):
    """获取指定页码的所有诗词原文（去除标点）"""
    page_key = str(page_num)
    poem_ids = poems_data.get("pages", {}).get(page_key, [])
    result = []
    for pid in poem_ids:
        poem = next((p for p in poems_data["poems"] if p["id"] == pid), None)
        if poem:
            raw = poem["text"]
            clean = raw.replace("，", "").replace("。", "").replace("？", "")
            clean = clean.replace("！", "").replace("、", "").replace("；", "")
            clean = clean.replace("：", "").replace(""", "").replace(""", "")
            clean = clean.replace("（", "").replace("）", "").replace("—", "")
            clean = clean.replace("\n", "").replace(" ", "").replace("　", "")
            result.append({"poem": poem, "raw": raw, "clean": clean})
    return result


def align_ocr_to_poem(ocr_text, poem_text):
    """利用最长公共子序列(LCS)对齐OCR文本到诗词原文"""
    matcher = SequenceMatcher(None, ocr_text, poem_text)
    ops = matcher.get_opcodes()
    corrected = list(ocr_text)
    changes = []
    for tag, i1, i2, j1, j2 in ops:
        if tag == 'equal':
            # part of OCR matched exactly, keep
            pass
        elif tag == 'replace':
            ocr_part = ocr_text[i1:i2]
            poem_part = poem_text[j1:j2]
            for k in range(min(len(ocr_part), len(poem_part))):
                if ocr_part[k] != poem_part[k]:
                    changes.append((i1 + k, ocr_part[k], poem_part[k]))
                    corrected[i1 + k] = poem_part[k]
        elif tag == 'delete':
            # OCR has extra chars the poem doesn't have — flag for review
            for k in range(i1, i2):
                changes.append((k, ocr_text[k], None))
                corrected[k] = None
        elif tag == 'insert':
            pass  # poem has extra chars OCR missed — nothing to correct
    corrected = [c for c in corrected if c is not None]
    return "".join(corrected), changes


def merge_split_chars(data):
    """合并同列中水平分裂的字符框（如书法字 枉 被拆成 木+王）"""
    cols = {}
    for i, c in enumerate(data):
        cols.setdefault(c['col'], []).append(i)
    to_remove = set()
    for col, indices in cols.items():
        indices.sort(key=lambda i: (data[i]['y'], data[i]['x']))
        i = 0
        while i < len(indices):
            if indices[i] in to_remove:
                i += 1
                continue
            ci = data[indices[i]]
            j = i + 1
            while j < len(indices):
                if indices[j] in to_remove:
                    j += 1
                    continue
                cj = data[indices[j]]
                y_overlap = min(ci['y']+ci['h'], cj['y']+cj['h']) - max(ci['y'], cj['y'])
                if y_overlap <= 0:
                    j += 1
                    continue
                gap = cj['x'] - (ci['x'] + ci['w'])
                if gap > 15:
                    j += 1
                    continue
                # Merge bounding boxes
                x1 = min(ci['x'], cj['x'])
                y1 = min(ci['y'], cj['y'])
                x2 = max(ci['x']+ci['w'], cj['x']+cj['w'])
                y2 = max(ci['y']+ci['h'], cj['y']+cj['h'])
                ci['x'] = x1; ci['y'] = y1
                ci['w'] = x2 - x1; ci['h'] = y2 - y1
                to_remove.add(indices[j])
            i += 1
    return [c for i, c in enumerate(data) if i not in to_remove]


def correct_page_ocr(ocr_json_path, poems_data, page_num):
    """对单页OCR结果进行自动校对"""
    with open(ocr_json_path, encoding='utf-8') as f:
        ocr_data = json.load(f)
    
    poems_info = get_poem_texts_for_page(poems_data, page_num)
    if not poems_info:
        return ocr_data, []
    
    # Sort OCR characters by column then row (calligraphy order: right-to-left, top-to-bottom)
    # But OCR columns might be numbered differently. We'll sort by x position (right-to-left)
    ocr_sorted = sorted(ocr_data, key=lambda c: (-c['x'], c['y']))
    
    # Group by column
    columns = {}
    for c in ocr_sorted:
        col = c['col']
        if col not in columns:
            columns[col] = []
        columns[col].append(c)
    
    # For each column, get text sequence (filter out empty rows)
    col_texts = {}
    for col, chars in columns.items():
        chars_sorted = sorted(chars, key=lambda c: c['row'])
        non_empty = [c for c in chars_sorted if c['text']]
        col_texts[col] = {
            'chars': non_empty,
            'text': ''.join(c['text'] for c in non_empty)
        }
    
    # Match each column individually against available poems
    all_corrections = []
    for col in sorted(col_texts.keys()):
        ct = col_texts[col]
        col_ocr = ct['text']
        col_len = len(col_ocr)
        if col_len == 0:
            continue
        
        # Find the poem that best matches this column
        best_match = None
        best_ratio = 0
        best_seg_start = 0
        
        for pi in poems_info:
            poem_clean = pi['clean']
            if len(poem_clean) < col_len:
                continue
            for start in range(len(poem_clean) - col_len + 1):
                seg = poem_clean[start:start + col_len]
                seg_ratio = SequenceMatcher(None, col_ocr, seg).ratio()
                if seg_ratio > best_ratio:
                    best_ratio = seg_ratio
                    best_match = pi
                    best_seg_start = start
        
        # Only apply corrections if match is reasonable
        if best_ratio < 0.3 or not best_match:
            continue
        
        poem_clean = best_match['clean']
        poem_seg = poem_clean[best_seg_start:best_seg_start + col_len]
        
        # Use SequenceMatcher for proper alignment (handles split/merged chars)
        aligned_text, sm_changes = align_ocr_to_poem(col_ocr, poem_seg)
        for ocr_idx, old_char, new_char in sm_changes:
            if ocr_idx >= len(ct['chars']):
                continue
            char = ct['chars'][ocr_idx]
            if new_char is not None:
                all_corrections.append({
                    'col': char['col'],
                    'row': char['row'],
                    'original': old_char,
                    'corrected': new_char,
                    'auto': True,
                    'deleted': False
                })
    
    # Apply corrections
    corrected_data = []
    for item in ocr_data:
        entry = dict(item)
        cor = [c for c in all_corrections if c['col'] == item['col'] and c['row'] == item['row']]
        if cor:
            c = cor[0]
            if c.get('deleted'):
                entry['auto_deleted'] = True
                entry['auto_corrected'] = False
                entry['corrected_text'] = ''
            else:
                entry['corrected_text'] = c['corrected']
                entry['auto_corrected'] = True
        else:
            entry['corrected_text'] = item['text']
            entry['auto_corrected'] = False
        corrected_data.append(entry)
    
    return corrected_data, all_corrections


def main():
    if len(sys.argv) < 2:
        print("用法: python src/corrector.py <页码>")
        print("示例: python src/corrector.py 24")
        sys.exit(1)
    
    page_num = int(sys.argv[1])
    poems = load_poems()
    ocr_path = f"output/pages/page_{page_num:03d}_ocr_results.json"
    
    if not os.path.exists(ocr_path):
        print(f"未找到OCR结果: {ocr_path}")
        sys.exit(1)
    
    corrected, changes = correct_page_ocr(ocr_path, poems, page_num)
    
    if not changes:
        print(f"第{page_num}页：无自动校正（可能是OCR结果缺失或未匹配到诗词）")
    else:
        print(f"第{page_num}页：自动校正 {len(changes)} 处\n")
        for c in changes:
            print(f"  列{c['col']}行{c['row']}: '{c['original']}' → '{c['corrected']}'")
    
    # Save corrected (also save to pipeline's expected path)
    out_path = ocr_path.replace('.json', '_corrected.json')
    pipeline_path = ocr_path.replace('_ocr_results.json', '_corrected.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(corrected, f, ensure_ascii=False, indent=2)
    with open(pipeline_path, 'w', encoding='utf-8') as f:
        json.dump(corrected, f, ensure_ascii=False, indent=2)
    print(f"\n已保存到: {out_path}")
    print(f"已保存到: {pipeline_path}")


if __name__ == "__main__":
    main()
