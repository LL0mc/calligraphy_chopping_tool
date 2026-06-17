"""Analyze page-level GT vs detection differences after iteration 1"""
import json, os

PAGE_DIR = 'output/pages'

def build_gt_position_based(page_num):
    path = os.path.join(PAGE_DIR, f'page_{page_num:03d}_ocr_results.json')
    with open(path, 'r', encoding='utf-8') as f: det = json.load(f)
    
    corr_path = os.path.join(PAGE_DIR, f'page_{page_num:03d}_corrected.json')
    corr = []
    if os.path.exists(corr_path):
        with open(corr_path, 'r', encoding='utf-8') as f: corr = json.load(f)
    
    gt_list = list(det)
    for c in corr:
        oi = c.get('orig_idx')
        if c.get('deleted'):
            if oi is not None and oi < len(gt_list):
                gt_list[oi] = None
        elif c.get('added'):
            gt_list.append({
                'col': c.get('col', 0), 'row': c.get('row', 0),
                'text': c.get('corrected_text', c.get('text', '')),
                'confidence': c.get('confidence', 0),
                'x': c['x'], 'y': c['y'], 'w': c['w'], 'h': c['h'],
            })
        else:
            if oi is not None and oi < len(gt_list):
                if 'x' in c and 'y' in c and 'w' in c and 'h' in c:
                    gt_list[oi]['x'] = c['x']
                    gt_list[oi]['y'] = c['y']
                    gt_list[oi]['w'] = c['w']
                    gt_list[oi]['h'] = c['h']
                gt_list[oi]['text'] = c.get('corrected_text', c.get('text', gt_list[oi]['text']))
    
    gt_list = [b for b in gt_list if b is not None]
    return gt_list, det

def analyze_page(p):
    gt, det = build_gt_position_based(p)
    print(f'Page {p:3d}: GT={len(gt):2d} DET={len(det):2d}')
    
    # Count changes from original
    corr_path = os.path.join(PAGE_DIR, f'page_{p:03d}_corrected.json')
    if os.path.exists(corr_path):
        with open(corr_path, 'r', encoding='utf-8') as f: corr = json.load(f)
        pos_corr = sum(1 for c in corr if 'x' in c and not c.get('added') and not c.get('deleted'))
        n_deleted = sum(1 for c in corr if c.get('deleted'))
        n_added = sum(1 for c in corr if c.get('added'))
        text_only = sum(1 for c in corr if 'x' not in c and not c.get('deleted') and not c.get('added'))
        print(f'       Corrections: pos={pos_corr} text={text_only} del={n_deleted} add={n_added}')
    
    # Compare each GT box to detection by reading order
    for i, (g, d) in enumerate(zip(gt, det)):
        if g['x'] != d['x'] or g['y'] != d['y']:
            print(f'       [{i}] GT pos ({g["x"]},{g["y"]},{g["w"]},{g["h"]}) vs DET ({d["x"]},{d["y"]},{d["w"]},{d["h"]})')
            if i < 5: break  # stop after 5 for brevity

for p in [24, 26, 27, 30, 43]:
    analyze_page(p)
