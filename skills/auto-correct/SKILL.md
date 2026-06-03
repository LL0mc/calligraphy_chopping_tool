# Skill: Calligraphy Auto-Correct

自动校对书法字帖的 OCR 检测结果，修正文字、提醒遗漏/误检。只改 `corrected_text`，不动框坐标。

## Triggers

- `校对第 {N} 页` / `修正第 {N} 页的文字`
- `自动校对第 {N} 页`
- `纠正 page {N} 的 OCR 结果`

## Workflow

### Step 1 — 确保 OCR 结果存在

```
检查 output/pages/page_{N:03d}_ocr_results.json
  ├─ 不存在 → 运行 python pipeline.py {N} --no-correct
  │           等待完成（超时 120s）
  │           再次检查文件是否存在
  │             不存在 → 报错"Pipeline 执行失败"，中止
  │             存在   → 继续
  └─ 存在 → 继续
```

### Step 2 — 确定阅读顺序

阅读顺序影响遍历方向，不同字帖方向不同。按优先级检测：

1. 读取 `page_{N:03d}_meta.json` → 取 `layout_direction` 字段
2. 无 meta 文件 → 读取 `config.py` 中的 `LAYOUT_DIRECTION`
3. 两者均无 → 默认竖排 RTL（col 降序，row 升序）

**阅读顺序表：**

| layout_direction | 排序方式 | 说明 |
|---|---|---|
| `vertical`（默认） | `(-col, row)` | 列从右到左，行从上到下 |
| `horizontal` | `(col, row)` | 行从上到下，列从左到右（LTR） |

排序后得到一个线性序列，按此顺序遍历校对。

### Step 3 — 读取已有修正

读取 `page_{N:03d}_corrected.json`（若存在）。用 `orig_idx` 关联到 OCR 结果。已标记 `manual_corrected: true` 的条目跳过。

### Step 4 — 逐字校对（text-only）

对每一步得到的每个 OCR 条目（按阅读顺序遍历）：

**跳过条件：** 以下任一成立则直接跳过，不做任何修改：
- 该条目在 `corrected.json` 中已有 `manual_corrected: true`
- 该条目标记为 `deleted`

**校对逻辑：**

```
已知文本 → 取 text 字段（OCR 原始识别文字）
置信度   → confidence 字段（0-1）

情况 A：text 为 "?" 或 confidence < 0.6
  → 根据前后文推断正确文字
  → 仅当有把握时写入 corrected_text
  → 没把握则跳过（留给你手动处理）

情况 B：text 非空且 confidence ≥ 0.6
  → 判断 text 在上下文中是否合理
  → 不合理 → 根据上下文修正，写入 corrected_text
  → 合理   → 跳过

判断标准：
- 前后文是经典诗词/对联/名言 → 利用对经典文本的知识
- 前后文未知 → 检查 text 是否是常见字形近字
  如：己/已/巳、戊/戌/戍、未/末、土/士、天/夭
  （OCR 容易混淆这种）
- 无上下文、也无明显错误 → 跳过
```

**上下文获取：** 从 `_ocr_results.json` 的 `col`/`row` 索引取前后各 3 个字的 `text` 或 `corrected_text`。

### Step 5 — 遗漏检测（只警告）

对每组（列或行，取决于 layout_direction）的字符序列，检查 `row` 索引是否有跳跃：

- 若某相邻对的 `row` 差值 > 1 → 可能存在遗漏
- 输出警告：`⚠️ 第 {col} 组第 {row1}→{row2} 行可能遗漏字符`

注意：不创建新框，不改 corrected.json。

### Step 6 — 误检检测（只警告）

检测置信度极低的条目（`confidence < 0.3` 或 `text == "?"`），特别关注：
- 列/行末尾的孤立的低置信框
- 周围无其他低置信框的孤立条目

输出警告：`⚠️ 第 {n} 号框（col={col}, row={row}）可能为误检`

### Step 7 — 写回并报告

**写 corrected.json：**
```
读取旧的 corrected.json（若存在）
为每个修正的条目写入：
  {
    "orig_idx": <对应 OCR 索引>,
    "corrected_text": "<修正后的文字>",
    "manual_corrected": true,
    "text": "<修正后的文字>",
    "x": <原值, 不改>,
    "y": <原值, 不改>,
    "w": <原值, 不改>,
    "h": <原值, 不改>
  }
写回 corrected.json
删除缓存（review_server 的缓存）
```

**输出摘要：**
```
✅ 第 {N} 页校对完成
   - 修正了 X 个字
   - 检测到 Y 处可能遗漏（已跳过，未自动补）
   - 检测到 Z 处可能误检（已跳过，未自动删）
   - 跳过已人工修正的 W 个字
你可以打开 http://127.0.0.1:5000/?p={N} 确认
```

## 格式参考

`_ocr_results.json` 条目格式：
```json
{
  "col": 0,
  "row": 0,
  "text": "无",
  "confidence": 0.97,
  "x": 100, "y": 200, "w": 80, "h": 120
}
```

`_corrected.json` 修正条目格式：
```json
{
  "orig_idx": 5,
  "corrected_text": "枉",
  "manual_corrected": true,
  "text": "枉",
  "x": 100, "y": 200, "w": 80, "h": 120
}
```

`page_NNN_meta.json` 格式：
```json
{
  "calligrapher": "吴玉生",
  "source_text": "红楼梦",
  "layout_direction": "vertical"
}
```

## 关键文件路径

| 文件 | 路径 |
|------|------|
| Pipeline | `pipeline.py` |
| 配置 | `config.py` |
| 页面数据 | `output/pages/page_{N:03d}_ocr_results.json` |
| 修正数据 | `output/pages/page_{N:03d}_corrected.json` |
| 页面元数据 | `output/pages/page_{N:03d}_meta.json` |
| 页面状态 | `output/pages/page_{N:03d}_reviewed.json` |
| Review GUI | `review_server.py` → http://127.0.0.1:5000 |
