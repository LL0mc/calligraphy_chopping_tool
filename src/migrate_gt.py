"""Migrate baseline+corrected → page_N_gt.json snapshots.

Usage: python src/migrate_gt.py [--pages 24,25,...] [--dry-run]
"""
import json, os, sys, argparse

PAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output', 'pages')


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_ground_truth(page_num):
    base = load_json(os.path.join(PAGE_DIR, f'page_{page_num:03d}_ocr_results_baseline.json'))
    if base is None:
        return None
    corr = load_json(os.path.join(PAGE_DIR, f'page_{page_num:03d}_corrected.json')) or []
    gt_list = list(base)
    to_delete = set()
    for c in corr:
        oi = c.get('orig_idx')
        if c.get('deleted'):
            if oi is not None and 0 <= oi < len(gt_list):
                to_delete.add(oi)
        elif c.get('added'):
            gt_list.append({
                'col': c.get('col', 0), 'row': c.get('row', 0),
                'text': c.get('corrected_text', c.get('text', '')),
                'confidence': c.get('confidence', 0),
                'x': c['x'], 'y': c['y'], 'w': c['w'], 'h': c['h'],
            })
        else:
            if oi is not None and 0 <= oi < len(gt_list):
                if 'x' in c and 'y' in c and 'w' in c and 'h' in c:
                    gt_list[oi]['x'], gt_list[oi]['y'] = c['x'], c['y']
                    gt_list[oi]['w'], gt_list[oi]['h'] = c['w'], c['h']
                gt_list[oi]['text'] = c.get('corrected_text', c.get('text', gt_list[oi]['text']))
    for idx in sorted(to_delete, reverse=True):
        gt_list.pop(idx)
    return gt_list


def get_reviewed_pages():
    pages = []
    for f in sorted(os.listdir(PAGE_DIR)):
        if f.endswith('_reviewed.json'):
            num = int(f.split('_')[1])
            pages.append(num)
    return pages


def main():
    parser = argparse.ArgumentParser(description='Migrate baseline+corrected → GT snapshots')
    parser.add_argument('--pages', type=str, default=None,
                        help='Comma-separated page numbers (default: all reviewed)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print GT without writing files')
    args = parser.parse_args()

    pages = [int(p.strip()) for p in args.pages.split(',')] if args.pages else get_reviewed_pages()

    migrated = 0
    skipped = 0
    for p in pages:
        gt = build_ground_truth(p)
        if gt is None:
            print(f"  p{p:03d}: SKIP (no baseline)")
            skipped += 1
            continue

        gt_path = os.path.join(PAGE_DIR, f'page_{p:03d}_gt.json')
        if args.dry_run:
            print(f"  p{p:03d}: {len(gt)} GT boxes")
            for i, box in enumerate(gt):
                print(f"    [{i}] col={box['col']} row={box['row']} "
                      f"text={box['text']} conf={box.get('confidence', 0):.3f} "
                      f"pos=({box['x']},{box['y']},{box['w']},{box['h']})")
        else:
            with open(gt_path, 'w', encoding='utf-8') as f:
                json.dump(gt, f, ensure_ascii=False, indent=2)
            print(f"  p{p:03d}: {len(gt)} GT boxes → {gt_path}")
        migrated += 1

    print(f"\nDone: {migrated} migrated, {skipped} skipped")


if __name__ == '__main__':
    main()
