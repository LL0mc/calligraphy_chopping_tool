# 项目注意事项

## 文件修改规范
- **禁止使用 `write` 工具直接覆盖现有文件**，必须先用 `read` 读取，再用 `edit` 进行增量修改
- 每次修改保留足够上下文，方便用户对比差异
- 如需创建新文件，先确认目标路径不存在

## 本项目核心原则
- OCR 裁剪优于原图：`detect_main_content_bbox` 裁剪后跑 OCR 效果更好
- refine 使用 v13-v15 增强版逻辑：标点排除 + seed 优先 + 距离合并 + 过大框收缩
- `dilate_kernel` 膨胀参数（config中设置或传参）：辅助飞白（feibai）断裂笔画的裁剪，仅做辅助定位，最终在原图裁剪
- 小字标注需合并到主列，不单独丢弃
- 去重 IoU 阈值 0.3，保留面积较大的框

## 当前 Pipeline 技术路线（v16）

### 流程
1. **渲染**：汉字→灰度图，2496×3720（A4等比例）
2. **内容裁剪**：`detect_main_content_bbox` — 滑动窗口检测主要内容区域
3. **OCR原始检测**：`get_ocr_char_boxes` — RapidOCR 单字级检测（含原文、置信度）
4. **标点过滤**：排除标点符号和空文本框，记录为 `punctuation_boxes` 供 refine 阶段排除
5. **分列**：按 x 中心坐标聚类，拆分子列，合并行内小字到主列，按列宽过滤书法列
6. **遗漏字符检测**：`detect_missing_chars_in_gaps` — 间隙+列尾检测遗漏字符
   - 间隙合并距离阈值：80px（从 40 提升，修复 枉 分裂）
   - 列尾搜索限制：≤ 2×avg_height，防止远距离墨迹误检
   - 列尾 ink-tail 检查：候选距上方字符 < 25% avg_height 跳过
   - 列尾重叠检查：候选项与上方字符重叠 > 50% 跳过
7. **连通域精炼切割**：`refine_char_bbox` — 以 OCR 框为中心，连通域分析精确裁剪
   - 标点排除：component center 落入 punctuation_boxes 且不 overlap OCR 框的跳过
   - claimed_regions：同列从上到下处理，防止后字符窃取前字符连通分量
   - 过大框回退：面积 > 2×OCR面积时，排除与 ROI 边界接触的组件
8. **OCR识别**：`recognize_characters` — 优先使用 `original_text`（步骤3检测的原文），仅在原文为空时重新OCR
9. **去重**：`remove_overlapping_boxes` — IoU 阈值 0.3，保留面积较大的框
10. **后处理**：按列检测异常大框，中位面积 3× 阈值缩小

### 三个关键修复（2026-05-23 应用）
1. **`ocr_recognizer.py`**: `recognize_characters()` 优先使用 `original_text`/`original_score`，仅在原文为空时重新OCR
2. **`char_segmenter.py`**: `detect_missing_chars_in_gaps` 间隙组件合并距离 40→80（修 枉 分裂）
3. **`char_segmenter.py`**: 列尾检测三项限制——搜索范围 ≤2×avg_height、ink-tail 跳过、重叠 >50% 跳过

### 效果（7页测试）
| 页面 | 原版 | 修复后 | 差值 |
|------|------|--------|------|
| P24  | 42框 | 39框 | -3 |
| P27  | 104框 | 101框 | -3 |
| P30  | 71框 | 66框 | -5 |
| P91  | 40框 | 39框 | -1 |
| P184 | 63框 | 58框 | -5 |
| P187 | 53框 | 49框 | -4 |
| P210 | 56框 | 49框 | -7 |

## 已知问题（已记录，暂未修复）
- **巷**（第30页，左边界）：左边撇超出 refine 框约39px，因为上左"共"部的纸间空隙距 OCR 中心125px超过 merge_radius 被排除。纸间方案固有限制，暂未修复。
- **飞白**（broken strokes）：笔画断裂处纸间空隙与外纸连通，导致外围候选组件被排除。目前膨胀方案效果过宽，暂不启用。
- **小圈/注释标记干扰**：部分页面上有红笔小圈标记（如标注的句读符号），被 OCR 检测为字符后混入主列，影响 refine 和排版。需单独识别并排除。
- **标点符号与字符粘连**：句号等小标点与字符笔画在二值图中有时粘连，导致 refine 时被当作字符组件合并进框，或反过来污染相邻字符的纸间空隙。当前排除逻辑（component center + overlap_ocr）已有改善，但极端情况仍有残留。

## 已修复问题记录
- **光**（第78页，右半部被切）：右捺笔成细小连通分量（6×14px），距OCR中心115px > merge_radius=100 被过滤。修复：`overlap_ocr`组件始终保留，不依赖距离。
- **P24/P184/P210 列尾墨迹假阳性**: 列尾搜索限制在 2×avg_height，P210 减少 7 个假阳性框
- **枉**（P24 分裂）：间隙组件合并距离 40→80，中心距 69.6px 的两个半框正确合并
- **口述偏移**（P184 间隙误检）：间隙候选 ink-tail + 重叠检查，排除 53×23 小墨点

## 文件命名规范
- **调试脚本输出的图片文件名禁止使用中文字符**（PowerShell 编码问题会导致乱码）
- 使用英文/数字/下划线命名，如 `page_024_step3_raw_ocr.png`

## 常用命令
- 调试标注图：`python debug_184_boxes.py`
- OCR 对比：`python debug_ocr_comparison.py`
- 批量跑图：`python run_all_7.py`
- 启动GUI：`python review_server.py` → http://127.0.0.1:5000/?p=24
