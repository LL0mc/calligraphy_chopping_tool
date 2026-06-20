"""OCR Evaluator: cost-based scoring reflecting human review effort.

Cost model:
  - Matching a pair: edge_cost + text_cost
    edge_sum = |dl| + |dt| + |dr| + |db|
    edge_cost = 0.1 * edge_sum  (if edge_sum > 3px, else 0)
    text_cost = 2               (if text differs)
  - Missed GT box: 8 per box (need to draw new box)
  - Extra det box: 1 per box (one-click delete)
  - score = max(0, 100 * (1 - total_cost / max_cost))
    max_cost = n_gt * 10
"""
import json, os, math
import numpy as np
from scipy.optimize import linear_sum_assignment

PAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output', 'pages')

C_EDGE = 0.1
C_TEXT = 2
C_MISS = 8
C_EXTRA = 1
EDGE_THRESH = 3

PROD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output', 'pages')
PAGE_DIR = PROD_DIR
_det_dir = None  # override for experiments


def load_json(path):
    if not os.path.exists(path): return None
    with open(path, 'r', encoding='utf-8') as f: return json.load(f)


def has_reviewed(page_num):
    return os.path.exists(os.path.join(PAGE_DIR, f'page_{page_num:03d}_reviewed.json'))


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


_det_dir_override = None

def load_detection(page_num):
    det_dir = _det_dir_override or PAGE_DIR
    return load_json(os.path.join(det_dir, f'page_{page_num:03d}_ocr_results.json'))


def center_dist(a, b):
    ca = (a['x'] + a['w']/2, a['y'] + a['h']/2)
    cb = (b['x'] + b['w']/2, b['y'] + b['h']/2)
    return math.hypot(ca[0]-cb[0], ca[1]-cb[1])


def match_boxes(gt_boxes, det_boxes, max_dist=60):
    n_gt, n_det = len(gt_boxes), len(det_boxes)
    if n_gt == 0 or n_det == 0:
        return [], list(range(n_gt)), list(range(n_det))
    cost = np.full((n_gt, n_det), max_dist + 1, dtype=np.float64)
    for i, g in enumerate(gt_boxes):
        for j, d in enumerate(det_boxes):
            d_ij = center_dist(g, d)
            if d_ij <= max_dist:
                cost[i, j] = d_ij
    gt_idx, det_idx = linear_sum_assignment(cost)
    matches = []
    unmatched_gt = set(range(n_gt))
    unmatched_det = set(range(n_det))
    for gi, di in zip(gt_idx, det_idx):
        if cost[gi, di] <= max_dist:
            matches.append((gi, di, float(cost[gi, di])))
            unmatched_gt.discard(gi)
            unmatched_det.discard(di)
    return matches, sorted(unmatched_gt), sorted(unmatched_det)


def evaluate_page(page_num):
    if not has_reviewed(page_num):
        return None
    gt = build_ground_truth(page_num)
    det = load_detection(page_num)
    if gt is None or det is None:
        return None
    matches, unmatched_gt, unmatched_det = match_boxes(gt, det)

    n_gt, n_det = len(gt), len(det)
    n_matched = len(matches)
    n_missed = len(unmatched_gt)
    n_extra = len(unmatched_det)

    total_cost = 0
    correct_text = 0
    edge_costs = []
    text_costs = []
    for gi, di, dist in matches:
        ge = {'l': gt[gi]['x'], 't': gt[gi]['y'],
              'r': gt[gi]['x']+gt[gi]['w'], 'b': gt[gi]['y']+gt[gi]['h']}
        de = {'l': det[di]['x'], 't': det[di]['y'],
              'r': det[di]['x']+det[di]['w'], 'b': det[di]['y']+det[di]['h']}
        edge_sum = abs(de['l']-ge['l']) + abs(de['t']-ge['t']) + abs(de['r']-ge['r']) + abs(de['b']-ge['b'])
        ec = C_EDGE * edge_sum if edge_sum > EDGE_THRESH else 0
        g_text = gt[gi].get('text', '').strip()
        d_text = det[di].get('text', '').strip()
        tc = 0 if g_text and g_text == d_text else C_TEXT
        if tc == 0: correct_text += 1
        total_cost += ec + tc
        edge_costs.append(edge_sum)
        text_costs.append(tc)

    total_cost += n_missed * C_MISS + n_extra * C_EXTRA
    max_cost = n_gt * (C_MISS + C_TEXT)
    score = max(0, 100 * (1 - total_cost / max_cost)) if max_cost > 0 else 0

    mean_edge = np.mean(edge_costs) if edge_costs else 0
    char_accuracy = correct_text / n_matched if n_matched > 0 else 0

    return {
        'page': page_num,
        'n_gt': n_gt, 'n_det': n_det, 'n_matched': n_matched,
        'n_missed': n_missed, 'n_extra': n_extra,
        'correct_text': correct_text, 'char_accuracy': round(char_accuracy, 4),
        'mean_edge_err': round(mean_edge, 2),
        'total_cost': round(total_cost, 2), 'score': round(score, 2),
    }


def get_submitted_pages():
    pages = set()
    for f in os.listdir(PAGE_DIR):
        if f.endswith('_reviewed.json'):
            pages.add(int(f.split('_')[1]))
    return sorted(pages)


def evaluate_all(det_dir=None, pages=None):
    if det_dir:
        global _det_dir_override
        _det_dir_override = det_dir
    eval_pages = pages if pages else get_submitted_pages()
    results = []
    for p in eval_pages:
        r = evaluate_page(p)
        if r:
            results.append(r)
            print(f"  Page {p:3d}: GT={r['n_gt']:2d} DET={r['n_det']:2d} "
                  f"Matched={r['n_matched']:2d} Missed={r['n_missed']} Extra={r['n_extra']} "
                  f"CharAcc={r['char_accuracy']:.1%} "
                  f"EdgeErr={r['mean_edge_err']:.1f}px "
                  f"Cost={r['total_cost']:.1f} Score={r['score']:.1f}")
    return results


def summarize(results):
    total_gt = sum(r['n_gt'] for r in results)
    total_det = sum(r['n_det'] for r in results)
    total_matched = sum(r['n_matched'] for r in results)
    total_missed = sum(r['n_missed'] for r in results)
    total_extra = sum(r['n_extra'] for r in results)
    total_correct = sum(r['correct_text'] for r in results)
    total_cost = sum(r['total_cost'] for r in results)
    avg_score = np.mean([r['score'] for r in results])

    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY (cost-based)")
    print("=" * 70)
    print(f"Pages evaluated:    {len(results)}")
    print(f"GT boxes:           {total_gt}")
    print(f"Detected boxes:     {total_det}")
    print(f"Matched pairs:      {total_matched}")
    print(f"Missed (need add):  {total_missed}  (cost {total_missed * C_MISS})")
    print(f"Extra (need delete): {total_extra}  (cost {total_extra * C_EXTRA})")
    print(f"Correct text:       {total_correct}/{total_matched}"
          f" ({total_correct/total_matched:.1%})" if total_matched > 0 else "N/A")
    text_cost = (total_matched - total_correct) * C_TEXT
    print(f"Text errors:        {total_matched - total_correct}  (cost {text_cost:.0f})")
    print(f"Total cost:         {total_cost:.0f} / {total_gt * (C_MISS + C_TEXT)}")
    print(f"Avg score:          {avg_score:.2f}/100")
    print("=" * 70)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--det-dir', type=str, default=None,
                        help='Detection results directory (default: same as PAGE_DIR)')
    parser.add_argument('--pages', type=str, default=None,
                        help='Comma-separated page numbers to evaluate (default: all submitted)')
    args = parser.parse_args()
    pages = [int(p.strip()) for p in args.pages.split(',')] if args.pages else None
    results = evaluate_all(det_dir=args.det_dir, pages=pages)
    summarize(results)
