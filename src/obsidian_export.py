"""Obsidian导出模块：生成Markdown笔记 + 图片链接"""
import os, sys, json, shutil, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import PAGES_DIR, CHARACTERS_DIR

VAULT_PATH = r"D:\notebooks\Lmc\brew"
EXPORT_DIR = os.path.join(VAULT_PATH, "字帖")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def create_symlink(target, link_name):
    """创建符号链接（Windows需要管理员权限，fallback到复制）"""
    if os.path.exists(link_name):
        return
    try:
        os.symlink(target, link_name)
    except (OSError, NotImplementedError):
        try:
            subprocess.run(['mklink', '/J', link_name, target],
                           shell=True, capture_output=True)
        except Exception:
            shutil.copytree(target, link_name, dirs_exist_ok=True)


def load_corrected_json(page_num):
    """加载已校对的JSON数据"""
    paths = [
        os.path.join(PAGES_DIR, f"page_{page_num:03d}_corrected.json"),
        os.path.join(PAGES_DIR, f"page_{page_num:03d}_annotated.json"),
        os.path.join(PAGES_DIR, f"page_{page_num:03d}_ocr_results.json"),
    ]
    for p in paths:
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                return json.load(f)
    return None


def get_character_image_rel(page_num, col, row):
    """获取字符图片在vault中的相对路径"""
    return f"图片/page_{page_num:03d}/page{page_num:03d}_col{col:02d}_row{row:02d}.png"


def export_char_notes(page_num, data, poems_on_page):
    """导出单字Markdown笔记"""
    char_dir = os.path.join(EXPORT_DIR, "单字")
    ensure_dir(char_dir)

    # Symlink character images
    img_src = os.path.join(CHARACTERS_DIR, f"page_{page_num:03d}")
    img_dst = os.path.join(EXPORT_DIR, "图片", f"page_{page_num:03d}")
    if os.path.exists(img_src):
        ensure_dir(os.path.dirname(img_dst))
        create_symlink(img_src, img_dst)

    for entry in data:
        text = entry.get('corrected_text', entry.get('text', ''))
        if not text:
            continue
        col, row = entry['col'], entry['row']
        conf = entry['confidence']

        img_rel = get_character_image_rel(page_num, col, row)

        # Use character as filename
        safe_name = text
        note_path = os.path.join(char_dir, f"{safe_name}.md")

        existing = ""
        if os.path.exists(note_path):
            with open(note_path, encoding='utf-8') as f:
                existing = f.read()

        poem_names = ', '.join(p['name'] for p in poems_on_page) if poems_on_page else ''

        new_entry = f"""---
character: "{text}"
page: {page_num}
col: {col}
row: {row}
confidence: {conf:.4f}
poem: "{poem_names}"
tags:
  - character
  - 红楼梦
  - 吴玉生
  - 行书
---

![[{img_rel}]]

| 属性 | 值 |
|------|-----|
| 字 | {text} |
| 页码 | 第{page_num}页 |
| 列 | 第{col}列 |
| 行 | 第{row}行 |
| 置信度 | {conf:.1%} |

"""
        with open(note_path, 'w', encoding='utf-8') as f:
            f.write(new_entry)


def export_poem_notes(page_data_map):
    """导出诗词索引笔记"""
    poems_data = {}
    poem_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'poems.json')
    if os.path.exists(poem_path):
        with open(poem_path, encoding='utf-8') as f:
            poems_all = json.load(f)
        for poem in poems_all.get('poems', []):
            poems_data[poem['id']] = poem

    poem_dir = os.path.join(EXPORT_DIR, "诗词")
    ensure_dir(poem_dir)

    # Collect characters per poem
    poem_chars = {}
    seen_chars = set()

    for page_num, page_poems in page_data_map.items():
        data = load_corrected_json(page_num)
        if not data:
            continue
        for poem_id in page_poems:
            if poem_id not in poems_data:
                continue
            poem = poems_data[poem_id]
            if poem_id not in poem_chars:
                poem_chars[poem_id] = []
            for entry in data:
                text = entry.get('corrected_text', entry.get('text', ''))
                if not text:
                    continue
                col, row = entry['col'], entry['row']
                img_rel = get_character_image_rel(page_num, col, row)
                key = (text, page_num)
                if key not in seen_chars:
                    seen_chars.add(key)
                    poem_chars[poem_id].append((text, page_num, col, row, img_rel, entry['confidence']))

    for poem_id, chars in poem_chars.items():
        if poem_id not in poems_data:
            continue
        poem = poems_data[poem_id]
        note_path = os.path.join(poem_dir, f"{poem['name']}.md")

        lines = []
        lines.append(f"""---
poem: "{poem['name']}"
author: "{poem['author']}"
chapter: {poem['chapter']}
tags:
  - poem
  - 红楼梦
---

# {poem['name']}

> {poem['text']}

## 字帖单字

| 序号 | 字 | 图片 | 页码 | 置信度 |
|------|-----|------|------|--------|
""")
        for i, (text, pn, col, row, img_rel, conf) in enumerate(chars, 1):
            lines.append(f"| {i} | {text} | ![[{img_rel}]] | 第{pn}页 | {conf:.1%} |\n")

        with open(note_path, 'w', encoding='utf-8') as f:
            f.write(''.join(lines))


def export_index():
    """导出总索引"""
    index_dir = os.path.join(EXPORT_DIR, "索引")
    ensure_dir(index_dir)

    # 总索引
    index_path = os.path.join(index_dir, "总索引.md")
    content = """---
tags:
  - index
---

# 字帖总索引

## 全部单字

```dataview
TABLE character, page, col, row, confidence, poem
FROM "../单字"
SORT character ASC
```

## 按诗词分组

```dataview
TABLE rows.character AS "单字", rows.page AS "页码"
FROM "../单字"
GROUP BY poem
```

## 按置信度筛选

### 高置信度 (>0.9)
```dataview
TABLE character, page, confidence
FROM "../单字"
WHERE confidence > 0.9
SORT confidence DESC
```

### 需复核 (0.5-0.9)
```dataview
TABLE character, page, confidence
FROM "../单字"
WHERE confidence <= 0.9 AND confidence > 0.5
SORT confidence DESC
```

### 低置信度/未识别 (<=0.5)
```dataview
TABLE character, page, confidence
FROM "../单字"
WHERE confidence <= 0.5
SORT confidence DESC
```

## 字频统计

```dataview
TABLE length(rows) AS "出现次数"
FROM "../单字"
GROUP BY character
SORT length(rows) DESC
```
"""
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(content)


def export_page(page_num, poems_data):
    """导出单页到Obsidian"""
    data = load_corrected_json(page_num)
    if not data:
        print(f"  第{page_num}页：无OCR数据，跳过")
        return

    page_poems = poems_data.get("pages", {}).get(str(page_num), [])
    poems_on_page = [p for p in poems_data.get("poems", []) if p["id"] in page_poems]

    export_char_notes(page_num, data, poems_on_page)
    print(f"  第{page_num}页: {len(data)}字 → Obsidian")


def main():
    poems_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'poems.json')
    with open(poems_path, encoding='utf-8') as f:
        poems_data = json.load(f)

    ensure_dir(EXPORT_DIR)

    import argparse
    parser = argparse.ArgumentParser(description="导出到Obsidian")
    parser.add_argument("pages", nargs="*", type=int, default=None,
                        help="页码列表（默认导出所有有数据的页面）")
    parser.add_argument("--index", action="store_true", help="强制重新生成索引")
    args = parser.parse_args()

    if args.pages:
        for pn in args.pages:
            export_page(pn, poems_data)
    else:
        # Auto-detect pages with OCR results
        for fname in os.listdir(PAGES_DIR):
            if fname.endswith('_corrected.json') or fname.endswith('_annotated.json'):
                pn = int(fname.split('_')[1])
                export_page(pn, poems_data)

    # Export poem notes
    page_data_map = {}
    for pn_str, poem_ids in poems_data.get("pages", {}).items():
        pn = int(pn_str)
        if load_corrected_json(pn):
            page_data_map[pn] = poem_ids
    export_poem_notes(page_data_map)
    print(f"  {len(page_data_map)}页诗词索引已生成")

    export_index()
    print("  总索引已生成")

    print(f"\n完成！导出目录: {EXPORT_DIR}")


if __name__ == "__main__":
    main()
