# Refactoring & Testing Plan

## Why

Pipeline 的核心数据结构是 **10 元素元组**：

```python
(x, y, w, h, char_img, area, col_idx, row_idx, text, score)
```

全靠魔数索引（`char[4]` 是图像、`char[8]` 是原文），跨模块传递时没有类型契约，加字段必须改所有消费方。加上零测试覆盖，重构风险高。

## Phase 1 — DataClass 引入

```python
# src/types.py
from dataclasses import dataclass, field
import numpy as np

@dataclass
class CharBox:
    x: int
    y: int
    w: int
    h: int
    img: np.ndarray | None = None
    area: int = 0
    col_idx: int = 0
    row_idx: int = 0
    text: str = ""
    score: float = 0.0

@dataclass
class OcrResult:
    x: int
    y: int
    w: int
    h: int
    col_idx: int
    row_idx: int
    original_text: str
    original_score: float
    ocr_text: str = ""
    ocr_score: float = 0.0
    expand_strategy: str = "none"

@dataclass
class Column:
    col_idx: int
    x_min: int
    x_max: int
    chars: list[CharBox] = field(default_factory=list)
```

迁移顺序：`char_segmenter.py`（tuple → CharBox）→ `ocr_recognizer.py`（tuple in → OcrResult out）→ `confidence_handler.py`（dict → OcrResult）→ `pipeline.py` 连接处。

## Phase 2 — 单元测试（第一梯队）

纯逻辑函数，无需图像，用坐标/数值即可测试：

| 函数 | 测试内容 |
|------|---------|
| `remove_overlapping_boxes` | IoU 去重：90% 重叠保留大的，30% 重叠都保留 |
| `expand_box` | three strategies: none/fixed/square |
| `classify_columns` | X 中心聚类：10 框分 3 列 |
| `filter_calligraphy_columns` | 列过滤：宽度 <130 丢弃，字符数 <2 丢弃 |
| `classify_by_confidence` | 置信度分桶：0.9→high, 0.6→medium, 0.2→low |

## Phase 3 — 单元测试（第二梯队）

需要合成图像（`np.zeros` 画矩形即可）：

| 函数 | 测试内容 |
|------|---------|
| `detect_main_content_bbox` | 已知内容的二值图 → 边界框正确 |
| `detect_missing_chars_in_gaps` | 已知间隙 → 检测/不检测 |
| `refine_char_bbox` | 给定连通域 → 精修框正确 |

## Phase 4 — 集成测试

对 `process_page` 做"黄金输出"回归：已知页面 → 比较 JSON 快照。
维护成本高（OCR 版本漂移），适合 CI 但不适合频繁迭代期。

## 不做的

- **Pydantic / attrs** — 杀鸡用牛刀，dataclass 足够
- **100% 覆盖率** — 不值得，重点覆盖纯逻辑 + 易错边界
- **Mock 图像 I/O** — 用合成图像而非 mock，更真实
