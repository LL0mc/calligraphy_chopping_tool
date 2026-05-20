# 项目注意事项

## 文件修改规范
- **禁止使用 `write` 工具直接覆盖现有文件**，必须先用 `read` 读取，再用 `edit` 进行增量修改
- 每次修改保留足够上下文，方便用户对比差异
- 如需创建新文件，先确认目标路径不存在

## 本项目核心原则
- OCR 裁剪优于原图：`detect_main_content_bbox` 裁剪后跑 OCR 效果更好
- refine 使用 v13-v15 增强版逻辑：标点排除 + seed 优先 + 距离合并 + 过大框收缩
- 小字标注需合并到主列，不单独丢弃
- 去重 IoU 阈值 0.3，保留面积较大的框

## 常用命令
- 调试标注图：`python debug_184_boxes.py`
- OCR 对比：`python debug_ocr_comparison.py`
