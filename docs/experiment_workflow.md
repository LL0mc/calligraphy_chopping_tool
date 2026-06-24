# 实验工作流

## 核心原则

**实验不碰生产数据。** 所有实验产出写入 `output/exp/{实验名}/`，生产数据（`output/pages/`）保持不变。

## 目录结构

```
output/
├── pages/                          ← 生产数据（不可随意修改）
│   ├── page_{num}.png              ← PDF 渲染原图
│   ├── page_{num}_processed.png    ← 预处理后
│   ├── page_{num}_ocr_results.json ← 当前 pipeline 输出（⚠️ 可变）
│   ├── page_{num}_gt.json          ← 人工审核真值（不可变）
│   ├── page_{num}_corrected.json   ← 人工修正记录
│   ├── page_{num}_reviewed.json    ← 提交标记
│   └── page_{num}_skipped.json     ← 跳过标记
├── cropped/                        ← 裁剪字符图（review_server submit 产出）
└── exp/                            ← 实验产出（各实验独立子目录）
    └── {实验名}/
        └── page_{num}_ocr_results.json
```

## 文件生命周期

### pipeline 运行时

```
python pipeline.py N
  → 读取 PDF → 渲染 → OCR → 输出 page_N_ocr_results.json
```

**⚠️ 直接运行会覆盖 `output/pages/page_N_ocr_results.json`（生产数据）。**

### review_server 提交时

```
POST /submit {p: N}
  1. 从 corrected 数据构建 → gt.json（真值快照）
  2. 裁剪字符图 → cropped/
  3. 同步 Obsidian 字库
  4. 标记 reviewed.json
```

**审计链：**
- `ocr_results.json` — pipeline 原始输出（可被下次 pipeline 覆盖）
- `corrected.json` — 人工修正记录（增删改框+文字）
- `gt.json` — 最终真值（corrected 合并后的结果）

### evaluator 运行时

```
python src/evaluator.py [--det-dir <path>]
  → GT: output/pages/page_N_gt.json（不可变）
  → DET: <det-dir>/page_N_ocr_results.json（或默认 output/pages/）
  → Hungarian 匹配 → 成本评分
```

GT 快照与 pipeline 版本解耦。Detection 可以来自任意目录（baseline、实验产出、或当前 pipeline）。

## 实验步骤

### 1. 创建实验分支

```bash
git checkout main
git pull
git checkout -b feat/实验名
```

### 2. 运行实验（不碰生产数据）

```bash
# 实验产出写入独立目录
python pipeline.py N --output-dir output/exp/实验名/

# 或批量运行
python pipeline.py 24,25,26 --output-dir output/exp/实验名/
```

### 3. 评估实验结果

```bash
# 对比实验输出 vs GT 快照
python src/evaluator.py --det-dir output/exp/实验名/

# 指定页数
python src/evaluator.py --det-dir output/exp/实验名/ --pages 24,25,26
```

评估器自动从 `output/pages/page_N_gt.json` 加载 GT，与实验目录中的检测结果对比。

### Baseline 管理

Baseline 是旧方法的检测结果，存放在 `output/exp/{基线名}/`，不在 `output/pages/` 中。

```bash
# 已有 baseline
ls output/exp/v4_baseline/       # 70+ 页，旧方法
ls output/exp/refactor_baseline/ # 30 页，重构前

# 新建 baseline（手动将当前 ocr_results 复制为 baseline）
mkdir -p output/exp/my_baseline/
cp output/pages/page_024_ocr_results.json output/exp/my_baseline/
```

**评估旧方法：**
```bash
python src/evaluator.py --det-dir output/exp/v4_baseline/
```

**评估新方法：**
```bash
python src/evaluator.py --det-dir output/exp/实验名/
```

**改进幅度 = 新分数 - 旧分数。**

### 4. 合并到主分支

```bash
git checkout main
git merge feat/实验名
# 或 cherry-pick 单个提交
```

## 评估器逻辑详解

### 匹配算法

使用 Hungarian 算法（`scipy.optimize.linear_sum_assignment`）做 GT 与 Detection 的最优匹配：

1. 计算所有 GT 框与 Detection 框的中心距离矩阵
2. 中心距离 > 60px 的配对设为不可匹配（成本 = 61）
3. Hungarian 算法求最小总距离的最优匹配
4. 成本 > 60 的匹配对丢弃

### 成本模型

| 操作 | 成本 | 说明 |
|------|------|------|
| 边缘偏差 | 0.1 × 四边偏差之和 | 仅当偏差 > 3px 时计算 |
| 文字不同 | 2 | 匹配框的文字不一致 |
| 漏检 | 8 | GT 有但 Detection 无（需手动新增） |
| 误检 | 1 | Detection 有但 GT 无（一键删除） |

### 评分公式

```
score = max(0, 100 × (1 - total_cost / max_cost))
max_cost = n_gt × (C_MISS + C_TEXT) = n_gt × 10
```

满分 100 = 零成本（完全匹配）。每扣分都对应具体的人工修正工作量。

**平均分**：按 GT 字数加权平均（`Σ(score × n_gt) / Σ(n_gt)`），大页贡献更多权重。

### 使用方式

```bash
# 评估生产数据（默认）
python src/evaluator.py

# 评估实验数据
python src/evaluator.py --det-dir output/exp/实验名/

# 指定页数
python src/evaluator.py --pages 24,25,26

# 组合使用
python src/evaluator.py --det-dir output/exp/v5-test/ --pages 24,25,26
```

## GT 快照管理

### 自动生成

GT 快照在 review_server 提交时自动生成，无需手动操作。

### 手动重建

如果需要从 ocr_results + corrected 重建 GT（例如迁移旧数据）：

```bash
python src/migrate_gt.py                    # 迁移所有 reviewed 页面
python src/migrate_gt.py --pages 24,25      # 迁移指定页面
python src/migrate_gt.py --dry-run          # 预览不写入
```

## 常见问题

### Q: pipeline 重跑后评估分数变了？

GT 快照是不可变的，分数变化只可能是因为：
1. Detection 结果变了（pipeline 重跑）
2. GT 本身有误（需要重新 review）

### Q: corrected.json 的 orig_idx 对不上？

`orig_idx` 引用的是 `corrected.json` 产出时的 ocr_results 索引。如果 pipeline 重跑导致 ocr_results 变化，orig_idx 可能错位。

**解决方案**：GT 快照已经固化了最终真值，不再依赖 orig_idx。旧的 corrected.json 仅供参考。

### Q: 如何添加新的评测页面？

1. 用 review_server 审核新页面
2. 提交时自动生成 gt.json
3. evaluator 自动发现新页面（通过 gt.json 文件存在性）

### Q: 实验目录的检测结果如何与 GT 对比？

evaluator 的 `--det-dir` 参数指向实验目录，GT 始终从 `output/pages/page_N_gt.json` 加载。两个来源独立，互不干扰。
