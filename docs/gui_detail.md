# Web 应用模块详解

## 概述

Pipeline 完成字符检测后，三个 Web 应用承担人工校对、浏览检索、集字排版的功能：

- **校对服务器**（Port 5000）：review_server.py — 人工校对 OCR 结果
- **字符查看器**（Port 5001）：char_viewer.py — 浏览检索已提交字符
- **集字排版**（Port 5001 /compose）：char_viewer.py + compose_renderer.py — 拼合书法作品

---

## 一、校对服务器（review_server.py）

### 1.1 数据模型

每页数据由三部分构成：

| 文件 | 格式 | 说明 |
|------|------|------|
| `page_{num}_ocr_results.json` | JSON 数组 | Pipeline 输出的原始检测结果 |
| `page_{num}_corrected.json` | JSON 数组 | 用户手动修正叠加层 |
| `page_{num}_reviewed.json` | `{}`（空 JSON） | 提交标记，存在即表示已提交 |

**corrected.json** 的每个条目通过 `orig_idx` 关联到 OCR 结果数组的对应索引：

```json
[
  {"orig_idx": 5, "corrected_text": "此", "x": 100, "y": 200, "w": 80, "h": 120, "manual_corrected": true},
  {"orig_idx": 99, "deleted": true},
  {"orig_idx": 100, "added": true, "col": 0, "row": 5, "corrected_text": "？"}
]
```

### 1.2 页面加载流程（`load_data` → `load_clean`）

1. 读取 `_ocr_results.json`，每条赋予 `orig_idx`（数组索引）。
2. 若 `_corrected.json` 存在，按 `orig_idx` 合并修正：
   - `deleted=true` → 标记删除。
   - `added=true` → 追加新条目。
   - 其他 → 逐字段覆盖原始 OCR 结果（x, y, w, h, text, confidence 等）。
3. `load_clean` 缓存结果（以 page_num 为 key），任何写入操作（save/del/add/submit）后调用 `drop_cache` 清除缓存。

### 1.3 保存流程

**文本编辑：** 用户在输入框中修改文字 → Enter 或 Ctrl+Enter 触发 `/sv` POST → 查找或创建 corrected.json 条目 → 写回文件 → 清除缓存。

**拖拽调整：** 鼠标拖拽框的 8 个控制点 → `mouseup` 事件触发 `/sv` POST → 同上。

**自动保存：** 切换字符时，`saveBg` 比较当前文本框值与已保存值，若有更改则调用 `/sv`。

### 1.4 提交流程（`/submit`）

1. 加载 clean 数据和全分辨率原图。
2. 按阅读顺序排序：列 X 降序（右→左）、行 Y 升序（上→下）。
3. 排序后赋予 `seq` 序号（从 1 开始）。
4. 遍历每个字符：
   - 从原图裁剪，4px 外扩边距。
   - 保存为 `{CROPPED_DIR}/{calligrapher}/{source_text}/page_{num}/{seq:03d}_{char}.png`。
   - **提交前清空**该页面的旧 cropped 目录（`shutil.rmtree` + 重建）。
5. 按字符分组，构建 `char_entries` 列表，每组包含该字符所有出现（seq, char, 位置, 置信度, 图片路径, 上下文 3 字）。
6. **更新 Obsidian 字库：** 对每个不同字符，写入/更新 `{CHAR_DB_DIR}/{calligrapher}/{source_text}/{char}.md`：
   - Frontmatter：`char`, `calligrapher`, `source`
   - 正文表格：`![[image.png]]` + 置信度 + 上下文
7. 写 `page_{num}_reviewed.json`（空 JSON 作为标记）。
8. 若存在 skipped 标记文件，删除它。
9. 清除缓存，前端自动跳转到下一页。

**注意：** 提交前会清空旧 cropped 目录再重建。这意味着提交是"覆写"而非"追加"——同一页的标注修正后重新提交，旧切片会被新版本替换。

### 1.5 页面状态

通过 `/status` 端点获取，前端自动轮询/刷新：

| 状态 | 条件 |
|------|------|
| **unprocessed** | `_ocr_results.json` 不存在 |
| **ready** | `_ocr_results.json` 存在，但 `_reviewed.json` 不存在 |
| **submitted** | `_reviewed.json` 存在，且 `_corrected.json` 的 mtime ≤ `_reviewed.json` 的 mtime + 1s |
| **pending** | `_reviewed.json` 存在，但 `_corrected.json` 更新（mtime 差异 > 1s） |
| **skipped** | `_skipped.json` 存在 |

前端用不同 CSS 类区分颜色：`st1`（未处理/红）、`st2`（就绪/绿）、`st3`（已提交/黄）、`st4`（待提交/橙）、`st5`（跳过/灰）。

**Pending 自动刷新：** 每次 `/sv`、`/del`、`/add` 成功后都会调用 `checkStatus(PAGE)`，无需页面刷新即可看到状态变化。

### 1.6 添加/删除字符

- **删除**（`/del`）：在 corrected.json 中追加 `{orig_idx, deleted: true}` 条目。
- **添加**（`/add`）：在 corrected.json 中追加 `{orig_idx: max+1, added: true, x, y, w, h, corrected_text: "?"}` 条目。列/行位置根据所选字符推断。

### 1.7 自动调起 Pipeline

访问未处理页面（`unprocessed`）时前端自动调用 `/run_page` → 服务器以 `subprocess` 方式运行 `python pipeline.py {page} --no-correct` → 完成后自动刷新。

### 1.8 重检（`/redetect`）

工具栏"重检"按钮，清除当前页面的所有修改并重新运行 Pipeline：

1. 删除 `corrected.json`（修正记录）
2. 删除 `reviewed.json`（提交标记）
3. 删除 `skipped.json`（跳过标记）
4. 删除 `output/cropped/.../page_{num}/` 目录（裁剪图片）
5. **清理 Obsidian 字库**：遍历字库目录，删除该页面在所有字笔记中的行
6. 清除缓存
7. 运行 Pipeline 重新识别
8. 完成后前端刷新页面

**用途：** 当 Pipeline 参数调整后，需要重新检测已有页面时使用。

---

## 二、字符查看器（char_viewer.py）

### 2.1 索引构建（`build_index`）

扫描 `output/cropped/{calligrapher}/{source_text}/` 目录：

```
page_024/
  001_此.png
  002_书.png
  ...
page_027/
  ...
```

读取所有匹配 `(\d+)_(.+?)\.png` 的文件，构建全局字典：

```python
{
  "此": [{"page": 24, "seq": 1, "filename": "001_此.png", "page_dir": "page_024"}, ...],
  "书": [...],
  ...
}
```

**自动刷新：** 所有 API 端点（search, char, compose/search 等）在每次调用时重建索引（文件系统扫描约 <100ms 对 ~260 页），新提交的字符即刻出现，无需重启服务器。

### 2.2 搜索逻辑（`/api/search`）

- `?q=` 参数进行子串匹配（`q in char`）。
- 空 q 返回所有字符及其出现次数。
- 结果按字符 Unicode 码点排序。

### 2.3 图像处理模式

`/api/image/<path>` 支持四种处理模式和反色：

| 模式 | 操作 |
|------|------|
| `original` | 原始裁剪图 |
| `enhanced` | CLAHE + 锐化核（`[[0,-1,0],[-1,5,-1],[0,-1,0]]`） |
| `bilateral` | 双边滤波（d=9, sigmaColor=75, sigmaSpace=75） |
| `binary` | Otsu 自适应二值化 |

**背景色自适应取样：** 统计图像亮度直方图，找到峰值（背景色），在该值 ±30 范围内采样平均。自动适配黑底白字/白底黑字两种字帖类型。反色时背景色随之翻转。

**墨心居中（`ink_center_crop`）：** 计算字符的质心（moment），以质心为中心裁剪 200×200 区域，使字符居中对齐。

### 2.4 Fabric.js 前端

- 240×240 画布，200×200 有效显示区域。
- 米字格/田字格两种参考线，通过 `drawGrid()` 在 canvas 中添加（注意：Fabric.js 5.3.0 无 `sendObjectToBack`，图像需在网格之后添加）。
- 加载防抖：`fromURL` 回调中通过 `loadSeq` 计数器防止旧回调覆盖新加载。
- 键盘快捷键：←/→ 切换字符、R 重置缩放、I 反色。

---

## 三、集字排版（compose_renderer.py + char_viewer.py /compose）

### 3.1 整体流程

1. 用户在 compose 前端输入文字 → POST `/api/compose/search` → 后端为每个字符查询变体列表。
2. 用户在侧边栏为每个位置选择变体 → 点击"渲染" → POST `/api/compose/render`。
3. 后端调用 `render_composition(chars, variants, params)` → Pillow 引擎合成 → 返回 PNG。
4. 导出 PDF：同渲染流程 → fpdf2 嵌入 PNG → 下载。

### 3.2 排版引擎设计（compose_renderer.py）

**核心函数：** `render_composition(chars, variants, params)`

#### Phase 1：解析输入

`chars` 为字符串，逐字符解析为 item 列表，类型有：

| 类型 | 产生方式 |
|------|----------|
| `char` | 普通汉字 |
| `punct` | 中英文标点（集合内） |
| `space` | 空格字符 |
| `nl` | 换行符 `\n`（触发列断） |

#### Phase 2：加载字图

- 对每个 `char` 类型 item，通过 `variants` 字典找到对应图片路径。
- 使用 `cv2.imdecode` 处理 Unicode 路径（避免中文文件名问题）。
- Otsu 二值化 → 反转，使得 255 = 白底、0 = 墨黑。
- **绝不缩放**：二进制图以原始分辨率保持。
- 记录所有加载字图的 `max_char_w` 和 `max_char_h`。

#### Phase 3：格子尺寸

```
cell_size = max(max_char_w, max_char_h) × 1.15
```

- 1.15 倍率保证最大字也不会溢出格子。
- 若无任何字图加载（全为标点/空格/fallback），回退到 `params['char_size']`（默认 100）。

#### Phase 4：布局计算

**换行与自动折行：**
- 换行符 `\n` 强制分列（竖排模式）或分行（横排模式）。
- `params['cols']` 控制每段的最大行数或列数。
- `has_nl` 守卫已移除——自动折行始终生效。

**第一次遍历（模拟布局）：** 计算每列的行数和总列数。
- 竖排（v_rtl/v_ltr）：行数受 `cols` 限制。新行触发会新建列。
- 横排（h_ltr/h_rtl）：列数受 `cols` 限制。超出行限制会新建行。
- 每种方向下，RTL 模式在格子定位阶段翻转列顺序（从右向左排列）。

**画布尺寸：**
- 左边距 = `gap × 2`
- 竖排：`w = left_margin + n_cols × (cell + gap) + gap`，`h = gap + max_rows × (cell + gap) + gap`
- 横排：`w = left_margin + cols × (cell + gap) + gap`，`h = gap + n_rows × (cell + gap) + gap`

#### Phase 5：背景渲染

| 背景类型 | 实现 |
|---------|------|
| `beige` | 纯色 (252, 249, 240, 255) |
| `white` | 纯白 (255,255,255,255) |
| `black` | 纯黑 (0,0,0,255) |
| `red` | 纯红 (200,40,30,255) |
| `gold_fleck` | 米白底 + 不规则金色多边形（`_render_gold_fleck_bg`） |
| `grass` | 黄褐底 + 纤维纹理（`_render_grass_bg`） |

**洒金宣（`_render_gold_fleck_bg`）：**
- 使用固定种子（`np.random.RandomState(42)`），保证多次渲染结果可重现。
- 密度：`w × h / 6000` 个多边形（最少 8 个）。
- 每个多边形 5–10 条边，半径 5–18px，随机角度 ±0.3 rad。
- 颜色：R=200–255, G=165–205, B=20–44, alpha=100–220。
- 35% 概率生成内部更亮的小一号多边形（0.5× 半径）。

**草木纸（`_render_grass_bg`）：**
- 密度：`w × h / 3000` 条纤维（最少 40 条）。
- 4 个角度：75°, 165°, 30°, 120°。
- 长度 50–200px，宽度 3–6px，alpha 25–60。
- 颜色：R=100–150, G=60–100, B=30–55。

#### Phase 6：第二次遍历（实际渲染）

对所有 item 按位置逐个渲染：

- **空格** → 空单元格。
- **换行** → 推进到下一列/行。
- **普通字符** → 计算格子位置，将 RGBA 字符图居中粘贴到格子中。
  - 若无对应图片 → 使用 `_make_fallback_char`（60% 格子大小的字体渲染）。
- **标点** → 使用 `_make_punctuation_overlay`：
  - 覆盖层大小 = 格子 × 45%。
  - 字体大小 = 覆盖层 × 70%（缩小以避免碰撞）。
  - 定位：格子右下角，12% 内边距。

#### 图片转 RGBA（`_binary_to_rgba`）

- 判断墨色方向：统计暗像素和亮像素数量，少的那侧为墨色。
- 墨色像素设为 `text_color`，其他像素设为完全透明 `(0,0,0,0)`。
- 支持 5 种文字颜色：`black`、`white`、`ink_blue`、`gold`、`red`。

### 3.3 导出

| 格式 | 方式 |
|------|------|
| PNG | 客户端下载：服务器返回 PNG → 前端 cache blob → `saveAs` |
| PDF | POST `/api/compose/export_pdf` → 服务端渲染 PNG → fpdf2 创建 PDF（页面尺寸 = 图像像素尺寸，1pt=1px）→ 返回 PDF 文件 |

### 3.4 前端交互

**点击定位：** 预览区点击任意字符 → 通过 `X-Cell-Size` 和 `X-Total-Cols` 响应头计算点击坐标对应的 (列, 行) → 映射到 `textIdx` → 通过 newline 偏移量找到 `dataIdx` → 侧边栏自动滚动到对应变体。

**缩放：** `ZOOM_BASE=0.40`，滑块 0.1–5.0。实际缩放 = `previewWidth × 0.40 × sliderValue`。`margin: 0 auto` 水平居中。

**参数响应：** 列数/间距/尺寸等参数使用 `input` 事件 + 200ms debounce，即时预览不卡顿。

---

## 四、Obsidian 字库

### 4.1 目录结构

```
{CHAR_DB_DIR}/{calligrapher}/{source_text}/
  ├── 此.md
  ├── 书.md
  ├── 梦.md
  └── ...
```

### 4.2 文件格式

```markdown
---
char: 梦
calligrapher: 吴玉生
source: 红楼梦
---

| # | 字 | 图片 | 置信度 | 上下文 |
|---|-----|------|---------|--------|
| 1 | 梦 | ![[page_024/001_梦.png]] | 0.99 | 红楼~ |
| 2 | 梦 | ![[page_027/013_梦.png]] | 0.97 | 入~境 |
```

- 同一字符的所有出现累积到同一文件。
- 上下文 = 该字符前后各 3 字（保持阅读顺序）。
- 图片使用 Obsidian embeds（`![[...]]`）。
- Dataview 插件可利用 frontmatter 做高级筛选（如查询某书家的所有字符）。
