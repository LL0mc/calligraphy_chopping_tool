# 项目进展

## 项目概述

从《吴玉生硬笔行书红楼梦诗词》PDF 字帖中提取单个书法字符，通过 OCR 识别并建立可检索的 Obsidian 知识库。

---

## 当前状态 (v12)

### 已完成

- **PDF 渲染**: `src/pdf_renderer.py` - 使用 `pypdfium2` 将 PDF 页面渲染为 2x 分辨率 PNG
- **页面预处理**: `src/page_preprocessor.py` - 灰度化、二值化、对比度增强
- **字符切割**: `src/char_segmenter.py` (v12) - OCR 定位 + 连通域精确裁剪

### 待解决

- [ ] 部分字符框不完整（如笔画较多的字）
- [ ] "枉" 字未被 OCR 识别到
- [ ] 批量处理全部 260 页
- [ ] OCR 置信度评估与人工校验流程
- [ ] 诗词元数据录入
- [ ] Obsidian 导出模块

---

## 算法迭代记录

### v1-v12: 探索阶段

| 版本 | 方案 | 问题 |
|------|------|------|
| v1-v5 | 简单连通域分析 | 网格线干扰严重，字符被分割 |
| v6-v8 | 投影法分割 | 对不规则布局适应性差 |
| v9-v10 | OCR 直接框选 + 列聚类 | 重叠框，注释被框入 |
| v11 | OCR word 框 + 按大小拆分混合列 | 框偏大，裁剪不精确 |
| v12 | OCR 定位 + 连通域精确裁剪 (当前) | 无重叠，裁剪精确 |

### v12: OCR定位 + 连通域精确裁剪 (当前)

**方案**: OCR 检测单字 → 列聚类 → 按大小拆分混合列 → 书法列过滤 → 连通域精确裁剪

**参数**:
- OCR 引擎：RapidOCR (PP-OCRv4) with `return_word_box=True`
- 列聚类阈值：x 中心间距 > 100px
- 大字尺寸阈值：宽度/高度 >= 120px
- 连通域裁剪：搜索范围 ±40px X / ±60px Y，合并半径 80px
- 标点过滤：显式标点集

**测试结果 (第24页)**:
- OCR 检测单字数：149 个（已过滤标点）
- 检测到列数：8 列 → 拆分为 8 个子列
- 书法列数：4 列（3 列正文 + 1 列"第一回"）
- 提取字符数：36 个
- 框重叠：✅ 无

**已知问题**:
1. "枉" 字未被 OCR 识别到
2. 字符框偶尔有空隙偏大或偏小

---

## 项目结构

```
handwriting/
├── config.py                    # 配置参数
├── run_test.py                  # 主测试运行器
├── PROJECT_PLAN.md              # 完整项目计划
├── PROGRESS.md                  # 本文件
├── src/
│   ├── __init__.py
│   ├── pdf_renderer.py          # PDF 渲染
│   ├── page_preprocessor.py     # 页面预处理
│   └── char_segmenter.py        # 字符切割 (核心，当前 v12)
├── output/
│   ├── pages/                   # 渲染页面
│   └── characters/              # 提取的字符
└── 吴玉生硬笔行书红楼梦诗词...pdf  # 源 PDF
```

---

## 已清理文件

以下临时/调试/分析脚本已删除:

- `try_ocr.py`, `try_cnocr.py` - OCR 引擎探索
- `debug_ocr.py`, `check_encoding.py`, `check_page53.py` - 调试脚本
- `analyze_all_chars.py`, `analyze_chars2.py`, `analyze_columns.py`, `analyze_ocr.py` - 分析脚本
- `test_clustering.py`, `test_diyihui.py`, `test_full_ocr.py`, `test_morphology.py`, `test_ocr_char.py`, `test_ocr_columns.py` - 算法实验
- `column_projection.png`, `sample_page0.png`, `sample_page1.png`, `sample_page24.png` - 临时图片
- `debug_boxes.py`, `test_three_pages.py` - 调试/验证脚本

---

## Phase 状态

| Phase | 状态 | 说明 |
|-------|------|------|
| Phase 1: 基础设施 | ✅ 完成 | PDF 渲染、页面预处理 |
| Phase 2: 单字切割 | 🔄 进行中 | v12 稳定，无重叠 |
| Phase 3: OCR 识别 | ❌ 未开始 | 待集成 |
| Phase 4: 元数据与入库 | ❌ 未开始 | 诗词元数据、Obsidian 导出 |
| Phase 5: 优化与完善 | ❌ 未开始 | 批量处理、性能优化 |
