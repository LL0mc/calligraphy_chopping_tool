"""Analyze text errors: compare OCR vs corrected text"""
import json, os
from collections import Counter

PAGE_DIR = 'output/pages'

def analyze_errors():
    pages = set()
    for f in os.listdir(PAGE_DIR):
        if f.endswith('_reviewed.json'):
            pages.add(int(f.split('_')[1]))
    pages = sorted(pages)
    
    total_errors = 0
    error_pairs = Counter()
    error_by_score = Counter()  # score ranges
    error_deleted = 0
    error_added = 0
    
    for p in pages:
        base = json.load(open(os.path.join(PAGE_DIR, f'page_{p:03d}_ocr_results_baseline.json'), 'r', encoding='utf-8'))
        corr = json.load(open(os.path.join(PAGE_DIR, f'page_{p:03d}_corrected.json'), 'r', encoding='utf-8'))
        
        for c in corr:
            if c.get('deleted'):
                error_deleted += 1
                continue
            if c.get('added'):
                error_added += 1
                continue
            
            oi = c.get('orig_idx')
            if oi is None or oi >= len(base):
                continue
            
            orig_text = base[oi].get('text', '').strip()
            corrected_text = c.get('corrected_text', c.get('text', '')).strip()
            
            if orig_text and orig_text != corrected_text:
                total_errors += 1
                error_pairs[f'{orig_text}→{corrected_text}'] += 1
                score = base[oi].get('confidence', 0)
                if score >= 0.9:
                    error_by_score['0.9-1.0'] += 1
                elif score >= 0.8:
                    error_by_score['0.8-0.9'] += 1
                elif score >= 0.6:
                    error_by_score['0.6-0.8'] += 1
                else:
                    error_by_score['<0.6'] += 1
    
    print(f"Total text corrections: {total_errors}")
    print(f"Deletions: {error_deleted}")
    print(f"Additions: {error_added}")
    print(f"\nErrors by confidence range:")
    for k, v in error_by_score.most_common():
        print(f"  {k}: {v}")
    print(f"\nTop 30 error pairs:")
    for pair, count in error_pairs.most_common(30):
        print(f"  {pair}: {count}")

analyze_errors()
