"""OCR Evaluator: compare pipeline output vs static GT (baseline + corrections)"""
import json, os, sys, math
from glob import glob
import numpy as np
from scipy.optimize import linear_sum_assignment

PAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output', 'pages')


def load_json(path):
    if not os.path.exists(path): return None
    with open(path, 'r', encoding='utf-8') as f: return json.load(f)


def has_reviewed(page_num):
    return os.path.exists(os.path.join(PAGE_DIR, f'page_{page_num:03d}_reviewed.json'))


def build_ground_truth(page_num):
    """Build static GT from BASELINE ocr_results + corrected.json (by orig_idx)"""
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


def load_detection(page_num):
    """Load current detection results"""
    return load_json(os.path.join(PAGE_DIR, f'page_{page_num:03d}_ocr_results.json'))


def center_dist(a, b):
    ca = (a['x'] + a['w']/2, a['y'] + a['h']/2)
    cb = (b['x'] + b['w']/2, b['y'] + b['h']/2)
    return math.hypot(ca[0]-cb[0], ca[1]-cb[1])


def box_edges(b):
    return {'l': b['x'], 't': b['y'], 'r': b['x']+b['w'], 'b': b['y']+b['h']}


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

    dl_list, dt_list, dr_list, db_list = [], [], [], []
    correct_text = 0
    for gi, di, dist in matches:
        ge, de = box_edges(gt[gi]), box_edges(det[di])
        dl_list.append(de['l'] - ge['l'])
        dt_list.append(de['t'] - ge['t'])
        dr_list.append(de['r'] - ge['r'])
        db_list.append(de['b'] - ge['b'])
        g_text = gt[gi].get('text', '').strip()
        d_text = det[di].get('text', '').strip()
        if g_text and g_text == d_text:
            correct_text += 1

    abs_dl = [abs(x) for x in dl_list]
    abs_dt = [abs(x) for x in dt_list]
    abs_dr = [abs(x) for x in dr_list]
    abs_db = [abs(x) for x in db_list]
    mean_edge_err = (np.mean(abs_dl) + np.mean(abs_dt) + np.mean(abs_dr) + np.mean(abs_db)) / 4 if dl_list else 0

    char_accuracy = correct_text / n_matched if n_matched > 0 else 0
    total_errors = n_matched - correct_text

    ref_size = np.mean([(b['w']+b['h'])/2 for b in gt]) if gt else 80
    edge_factor = max(0, 1 - min(mean_edge_err / ref_size, 0.3))
    recall = n_matched / n_gt if n_gt > 0 else 0
    precision = n_matched / n_det if n_det > 0 else 0
    detection_f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    score = 100.0 * (correct_text / max(n_gt, n_det)) * edge_factor * detection_f1 if max(n_gt, n_det) > 0 else 0

    return {
        'page': page_num,
        'n_gt': n_gt, 'n_det': n_det, 'n_matched': n_matched,
        'n_missed': len(unmatched_gt), 'n_extra': len(unmatched_det),
        'correct_text': correct_text, 'char_accuracy': round(char_accuracy, 4),
        'char_errors': total_errors,
        'dl_mean': round(np.mean(dl_list), 2) if dl_list else 0,
        'dt_mean': round(np.mean(dt_list), 2) if dt_list else 0,
        'dr_mean': round(np.mean(dr_list), 2) if dr_list else 0,
        'db_mean': round(np.mean(db_list), 2) if db_list else 0,
        'abs_dl_mean': round(np.mean(abs_dl), 2) if abs_dl else 0,
        'abs_dt_mean': round(np.mean(abs_dt), 2) if abs_dt else 0,
        'abs_dr_mean': round(np.mean(abs_dr), 2) if abs_dr else 0,
        'abs_db_mean': round(np.mean(abs_db), 2) if abs_db else 0,
        'mean_edge_err': round(mean_edge_err, 2),
        'edge_factor': round(edge_factor, 4),
        'recall': round(recall, 4), 'precision': round(precision, 4),
        'detection_f1': round(detection_f1, 4), 'score': round(score, 2),
    }


def get_submitted_pages():
    pages = set()
    for f in os.listdir(PAGE_DIR):
        if f.endswith('_reviewed.json'):
            pages.add(int(f.split('_')[1]))
    return sorted(pages)


def evaluate_all():
    pages = get_submitted_pages()
    results = []
    for p in pages:
        r = evaluate_page(p)
        if r:
            results.append(r)
            print(f"  Page {p:3d}: GT={r['n_gt']:2d} DET={r['n_det']:2d} "
                  f"Matched={r['n_matched']:2d} Missed={r['n_missed']} Extra={r['n_extra']} "
                  f"CharAcc={r['char_accuracy']:.1%} "
                  f"EdgeErr={r['mean_edge_err']:.1f}px Score={r['score']:.1f}")
    return results


def summarize(results):
    total_gt = sum(r['n_gt'] for r in results)
    total_det = sum(r['n_det'] for r in results)
    total_matched = sum(r['n_matched'] for r in results)
    total_missed = sum(r['n_missed'] for r in results)
    total_extra = sum(r['n_extra'] for r in results)
    total_correct = sum(r['correct_text'] for r in results)
    total_errors = sum(r['char_errors'] for r in results)

    weighted_score = sum(r['score'] * r['n_gt'] for r in results) / total_gt if total_gt > 0 else 0

    print("\n" + "=" * 70)
    print("BASELINE EVALUATION SUMMARY")
    print("=" * 70)
    print(f"Pages evaluated: {len(results)}")
    print(f"Ground truth boxes: {total_gt}")
    print(f"Detected boxes:     {total_det}")
    print(f"Matched pairs:      {total_matched}")
    print(f"Missed (GT not found): {total_missed}")
    print(f"Extra (false positives): {total_extra}")
    print(f"Correct text:       {total_correct}/{total_matched} "
          f"({total_correct/total_matched:.1%})" if total_matched > 0 else "N/A")
    print(f"Text errors:        {total_errors}")
    print(f"Edge error (mean abs): l={np.mean([r['abs_dl_mean'] for r in results]):.1f}px  "
          f"t={np.mean([r['abs_dt_mean'] for r in results]):.1f}px  "
          f"r={np.mean([r['abs_dr_mean'] for r in results]):.1f}px  "
          f"b={np.mean([r['abs_db_mean'] for r in results]):.1f}px")
    print(f"Edge error (signed):   l={np.mean([r['dl_mean'] for r in results]):.1f}px  "
          f"t={np.mean([r['dt_mean'] for r in results]):.1f}px  "
          f"r={np.mean([r['dr_mean'] for r in results]):.1f}px  "
          f"b={np.mean([r['db_mean'] for r in results]):.1f}px")
    print(f"Mean edge error (avg of 4 edges): {np.mean([r['mean_edge_err'] for r in results]):.1f}px")
    print(f"Detection F1: {np.mean([r['detection_f1'] for r in results]):.3f}")
    print(f"Weighted composite score: {weighted_score:.2f}/100")
    print("=" * 70)


if __name__ == '__main__':
    results = evaluate_all()
    summarize(results)
