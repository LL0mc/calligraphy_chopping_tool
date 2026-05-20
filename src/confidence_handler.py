"""置信度处理模块：根据OCR置信度做出不同处理"""
from typing import List, Dict


def classify_by_confidence(ocr_results: list,
                           high_threshold: float = 0.8,
                           low_threshold: float = 0.5) -> Dict[str, list]:
    """按置信度分类OCR结果
    
    Returns:
        {
            'high': [...],    # 高置信度，直接使用
            'medium': [...],  # 中等置信度，需要复核
            'low': [...],     # 低置信度，需要人工校正
            'unrecognized': [...]  # 未识别，需要人工输入
        }
    """
    result = {'high': [], 'medium': [], 'low': [], 'unrecognized': []}
    
    for r in ocr_results:
        text = r['ocr_text']
        score = r['ocr_score']
        
        if not text:
            result['unrecognized'].append(r)
        elif score >= high_threshold:
            result['high'].append(r)
        elif score >= low_threshold:
            result['medium'].append(r)
        else:
            result['low'].append(r)
    
    return result


def get_confidence_summary(classified: Dict[str, list]) -> str:
    """生成置信度统计摘要"""
    total = sum(len(v) for v in classified.values())
    lines = [
        f"总字符数: {total}",
        f"高置信度 (>=0.8): {len(classified['high'])} ({len(classified['high'])/total*100:.1f}%)",
        f"中等置信度 (0.5-0.8): {len(classified['medium'])} ({len(classified['medium'])/total*100:.1f}%)",
        f"低置信度 (<0.5): {len(classified['low'])} ({len(classified['low'])/total*100:.1f}%)",
        f"未识别: {len(classified['unrecognized'])} ({len(classified['unrecognized'])/total*100:.1f}%)"
    ]
    return '\n'.join(lines)


def print_review_list(classified: Dict[str, list]):
    """打印需要复核的字符列表"""
    print("\n[需要复核的字符]")
    
    if classified['medium']:
        print("\n  中等置信度 (建议复核):")
        for r in classified['medium']:
            text = r['ocr_text']
            score = r['ocr_score']
            print(f"    列{r['col_idx']+1} 行{r['row_idx']+1}: '{text}' ({score:.2f})")
    
    if classified['low']:
        print("\n  低置信度 (需要校正):")
        for r in classified['low']:
            text = r['ocr_text']
            score = r['ocr_score']
            print(f"    列{r['col_idx']+1} 行{r['row_idx']+1}: '{text}' ({score:.2f})")
    
    if classified['unrecognized']:
        print("\n  未识别 (需要人工输入):")
        for r in classified['unrecognized']:
            print(f"    列{r['col_idx']+1} 行{r['row_idx']+1}: ? (score={r['ocr_score']:.2f})")


def export_results(ocr_results: list, output_path: str):
    """导出OCR结果为JSON/CSV格式"""
    import json
    import numpy as np
    
    class NumpyEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return super().default(obj)
    
    data = []
    for r in ocr_results:
        data.append({
            'col': int(r['col_idx'] + 1),
            'row': int(r['row_idx'] + 1),
            'text': r['ocr_text'],
            'confidence': float(r['ocr_score']),
            'x': int(r['x']), 'y': int(r['y']), 'w': int(r['w']), 'h': int(r['h']),
            'expand_strategy': r['expand_strategy']
        })
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, cls=NumpyEncoder)
    
    print(f"[导出] 结果已保存到: {output_path}")
