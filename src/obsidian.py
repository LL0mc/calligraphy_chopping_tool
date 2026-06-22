"""Obsidian character database sync utilities for review server."""
import os, shutil
from collections import defaultdict


def sync_obsidian_entries(char_entries, full_text, page_num, calligrapher, source_text, char_db_dir):
    """Sync character entries to Obsidian vault after page submission."""
    base_rel = os.path.join(calligrapher, source_text)
    note_dir = os.path.join(char_db_dir, base_rel)
    os.makedirs(note_dir, exist_ok=True)

    # Group entries by char
    char_groups = defaultdict(list)
    seen = set()
    for e in char_entries:
        ch = e['char']
        if ch == '?' or ch == 'unk':
            continue
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
            rows.append(f"| {page_num} | {e['seq']} | {img_link} | {e['confidence']:.2f} | {ctx} |")

        # Read existing content if note exists (only keep header/frontmatter)
        existing_rows = []
        if os.path.exists(note_path):
            with open(note_path, 'r', encoding='utf-8') as f:
                existing = f.read()
            in_table = False
            for line in existing.splitlines():
                if line.startswith('|') and '|---|---|' not in line and in_table:
                    existing_rows.append(line)
                elif '|---|---|' in line:
                    in_table = True
            existing_rows = [r for r in existing_rows if not r.startswith(f'| {page_num} |')]

        all_rows = existing_rows + rows
        table = "\n".join([
            f"---",
            f'char: "{ch}"',
            f'calligrapher: "{calligrapher}"',
            f'source: "{source_text}"',
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


def cleanup_page_entries(page_num, calligrapher, source_text, char_db_dir, cropped_dir):
    """Clean up Obsidian entries and cropped images for a page (used by redetect)."""
    # Clear cropped images for this page
    page_cropped_dir = os.path.join(cropped_dir, calligrapher, source_text, f"page_{page_num:03d}")
    if os.path.exists(page_cropped_dir):
        shutil.rmtree(page_cropped_dir)

    # Clean Obsidian DB entries for this page
    base_rel = os.path.join(calligrapher, source_text)
    note_dir = os.path.join(char_db_dir, base_rel)
    if os.path.exists(note_dir):
        for fname in os.listdir(note_dir):
            if not fname.endswith('.md'):
                continue
            note_path = os.path.join(note_dir, fname)
            with open(note_path, 'r', encoding='utf-8') as f:
                content = f.read()
            new_lines = []
            for line in content.splitlines():
                if line.startswith(f'| {page_num} |'):
                    continue
                new_lines.append(line)
            with open(note_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(new_lines) + '\n')
