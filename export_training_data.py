"""训练数据集导出：从28页GT导出检测+识别训练数据"""
import json, os, sys, shutil, random, math
from pathlib import Path
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.evaluator import build_ground_truth, has_reviewed, PAGE_DIR

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output', 'training_data')
IMG_DIR = PAGE_DIR  # original page images are here


def get_reviewed_pages():
    pages = []
    for f in os.listdir(PAGE_DIR):
        if f.endswith('_reviewed.json'):
            pages.append(int(f.split('_')[1]))
    return sorted(pages)


def export_detection(pages, split_name, output_subdir):
    """导出检测训练数据（ICDAR格式）— 所有页放在同一 imgs/gt 目录，TSV 分离"""
    imgs_dir = os.path.join(output_subdir, 'imgs')
    gt_dir = os.path.join(output_subdir, 'gt')
    os.makedirs(imgs_dir, exist_ok=True)
    os.makedirs(gt_dir, exist_ok=True)

    entries = []
    for p in pages:
        gt_list = build_ground_truth(p)
        if gt_list is None:
            continue

        src_path = os.path.join(IMG_DIR, f'page_{p:03d}.png')
        if not os.path.exists(src_path):
            print(f'  [跳过] page_{p} 无图片')
            continue

        dst_path = os.path.join(imgs_dir, f'page_{p:03d}.png')
        if not os.path.exists(dst_path):
            shutil.copy2(src_path, dst_path)

        # Write GT file (ICDAR format: x1,y1,x2,y2,x3,y3,x4,y4,label)
        gt_path = os.path.join(gt_dir, f'page_{p:03d}.txt')
        if not os.path.exists(gt_path):
            with open(gt_path, 'w', encoding='utf-8') as f:
                for item in gt_list:
                    x, y, w, h = item['x'], item['y'], item['w'], item['h']
                    label = item.get('text', '').strip()
                    if not label:
                        continue
                    # 4-corner polygon from axis-aligned box
                    f.write(f'{x},{y},{x+w},{y},{x+w},{y+h},{x},{y+h},{label}\n')

        rel_img = f'imgs/page_{p:03d}.png'
        rel_gt = f'gt/page_{p:03d}.txt'
        entries.append(f'{rel_img}\t{rel_gt}')
        print(f'  page_{p}: {len(gt_list)} chars')

    # Write TSV index
    tsv_path = os.path.join(output_subdir, f'{split_name}.tsv')
    with open(tsv_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(entries))
    print(f'  [{split_name}] {len(entries)} pages -> {tsv_path}')


def export_recognition(pages, split_name, output_subdir):
    """导出识别训练数据（单字图+标签TSV）"""
    out_dir = os.path.join(output_subdir, split_name, 'imgs')
    os.makedirs(out_dir, exist_ok=True)

    entries = []
    for p in pages:
        gt_list = build_ground_truth(p)
        if gt_list is None:
            continue

        src_path = os.path.join(IMG_DIR, f'page_{p:03d}.png')
        if not os.path.exists(src_path):
            continue

        full_img = cv2.imread(src_path, cv2.IMREAD_GRAYSCALE)
        if full_img is None:
            continue

        for idx, item in enumerate(gt_list):
            x, y, w, h = item['x'], item['y'], item['w'], item['h']
            label = item.get('text', '').strip()
            if not label:
                continue

            crop = full_img[y:y+h, x:x+w]
            if crop.size == 0:
                continue

            fname = f'{p:03d}_{idx:03d}.png'
            cv2.imwrite(os.path.join(out_dir, fname), crop)

            # cnocr rec format: relative path, then space-separated chars
            entries.append(f'{split_name}/imgs/{fname}\t{label}')

        print(f'  page_{p}: {idx+1} chars')

    tsv_path = os.path.join(output_subdir, f'{split_name}.tsv')
    with open(tsv_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(entries))
    print(f'  [{split_name}] {len(entries)} chars -> {tsv_path}')


def main():
    pages = get_reviewed_pages()
    print(f'Reviewed pages: {len(pages)} -> {pages}')

    random.seed(42)
    shuffled = list(pages)
    random.shuffle(shuffled)
    split_idx = max(1, math.floor(len(shuffled) * 0.8))
    train_pages = sorted(shuffled[:split_idx])
    dev_pages = sorted(shuffled[split_idx:])
    print(f'Train: {len(train_pages)} pages {train_pages}')
    print(f'Dev:   {len(dev_pages)} pages {dev_pages}')

    # Detection data (cnstd format)
    det_dir = os.path.join(OUTPUT_DIR, 'detection')
    print('\n=== Detection Data ===')
    export_detection(train_pages, 'train', det_dir)
    export_detection(dev_pages, 'dev', det_dir)

    # Recognition data (cnocr format)
    rec_dir = os.path.join(OUTPUT_DIR, 'recognition')
    print('\n=== Recognition Data ===')
    export_recognition(train_pages, 'train', rec_dir)
    export_recognition(dev_pages, 'dev', rec_dir)

    print(f'\nDone! Data exported to {OUTPUT_DIR}')


if __name__ == '__main__':
    main()
