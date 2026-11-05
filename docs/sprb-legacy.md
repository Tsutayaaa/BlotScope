# 历史 SprB 说明（当前检出不含实现）

以下为原 README 保留的说明，命令目前不可运行。

# SprB 批量序列生成器 + WB Marker 分子量估算工具

本项目包含两个互相独立的本地工具：

- `sprb_builder`：从菌株表的自然语言 Description 生成结构化编辑计划，再由确定性代码批量构建 SprB 蛋白序列。
- `wb_marker_tool.py`：从 WB Marker lane 的灰度峰拟合表观分子量。

## SprB 批量序列生成器

### 安全设计

自然语言解析器**不直接生成序列**。它只输出以下结构化信息：parent strain、operation type、WT 坐标、named insert、置信度和人工复核标志。序列引擎只接受结构化编辑。

所有 SprB 坐标默认使用 **WT SprB 蛋白的 1-based inclusive AA 坐标**：

- 删除 `AA1232-AA2871`：保留 WT `1-1231` 与 `2872-end`。
- `between AA76 and AA77` 插入：结果为 `WT[1:76] + insert + WT[77:end]`。
- 派生菌株继续编辑时，坐标仍解释为 WT 坐标。引擎维护每个残基的 provenance map，不会因上游 deletion 导致重新编号错位。
- 如果一个待删除 WT 区间在 parent 中已经部分或完全不存在，会写入 warning；不会静默忽略。

Plasmid complementation、异位表达、非 SprB construct、没有唯一范围的 truncation 和歧义 `-sfGFP` 默认只做标记，不会被当作 genomic SprB replacement。sfGFP 或其他插入序列必须由用户以 FASTA 提供。

### 安装

需要 Python 3.9 或更高版本：

```bash
python3 -m pip install -r requirements.txt
```

可选审核界面：

```bash
python3 -m pip install -r requirements-sprb-gui.txt
streamlit run sprb_streamlit.py
```

### 输入文件

菌株表可为 CSV、TSV、XLSX 或 XLSM，至少包含以下列（列名大小写不敏感）：

| Stock # | Strain | Description |
|---|---|---|
| FJ1 | CJ1356 | WT, spreading |
| FJ76 | CJ2728 | ∆sprBR1 (AA 1232-AA 2871) in CJ1356 |
| FJ105 | CJ2819 | sfGFP inserted into SprB (between AA 76 and AA 77) in CJ1356 |

WT FASTA 必须只有一条记录：

```text
>WT_SprB
MKK...完整的 SprB 蛋白序列...
```

named inserts 使用 multi-FASTA。header 的第一个 token 必须与解析计划里的名字一致；sfGFP 示例：

```text
>sfGFP
MSK...用户提供的真实 sfGFP 蛋白序列...
>other_tag
MYP...另一个真实插入序列...
```

工具不会内置或猜测 sfGFP 序列。

### 先 dry-run 审核

dry-run 不需要 WT FASTA，不构建序列：

```bash
python3 -m sprb_builder strains.xlsx --dry-run --output review
```

终端会显示结构化计划，并保存 `review/edit_plan.json`。应优先检查：

- `requires_manual_review: true`
- 低 `confidence`
- 推断得到的 named-region range 及 `inference_source`
- 未在表中出现的 parent
- complementation/ectopic expression、non-SprB construct 和 ambiguous `-sfGFP`

### 生成序列

```bash
python3 -m sprb_builder strains.xlsx \
  --wt-fasta WT_SprB.fasta \
  --inserts-fasta named_inserts.fasta \
  --output results
```

默认已知 WT root 为 `CJ1356`。可重复添加其他已经人工确认携带 WT SprB 的 parent：

```bash
python3 -m sprb_builder strains.csv --wt-fasta WT_SprB.fasta \
  --inserts-fasta named_inserts.fasta \
  --wt-root CJ1827 --wt-root CJ1356 --output results
```

未列出的 parent 默认不会被假定成 WT。只有在你明确接受该假设时才使用 `--assume-missing-parent-wt`。

### 人工复核与 overrides

建议复制 [示例 override](examples/sprb_overrides.example.json)，把已经查证的 parent 和 edits 写入 JSON。`reviewed: true` 表示你确认该计划可以执行：

```bash
python3 -m sprb_builder strains.xlsx --wt-fasta WT_SprB.fasta \
  --inserts-fasta named_inserts.fasta \
  --overrides my_reviewed_overrides.json --output results
```

`--allow-manual-review` 会强制尝试执行所有被标记的计划，通常不建议；含有 unknown/complementation/non-SprB operation 的条目即使强制执行也会报确定性 build error，而不会生成猜测序列。

### 输出

`results/` 包含：

```text
results/
├── FJ1_CJ1356_SprB.fasta
├── FJ76_CJ2728_SprB.fasta
├── summary.csv
├── summary.xlsx
└── edit_audit.json
```

`summary.csv/xlsx` 包括 Stock #、Strain、parent、category、parsed edits、final length、expected MW、status、warnings、confidence 和 manual-review 标志。理论 MW 使用“各氨基酸平均 residue mass 求和 + 18.01528 Da 末端水”的方法，单位为 kDa；这不是 WB 的表观分子量。

`edit_audit.json` 保存每一步编辑前后长度、WT 坐标、编辑发生前的当前序列位置、删除数量、warning 和压缩后的 residue-provenance runs。

### 测试

```bash
python3 -m pytest -q
```

测试 fixture 位于 `tests/fixtures/example_strains.csv`，覆盖 FJ1、FJ55、FJ76、FJ77、FJ78、FJ80、FJ82、FJ86、FJ87、FJ88、FJ90、FJ92–FJ117 中请求的全部条目。无法唯一生成 SprB 的 complementation、歧义 sfGFP 和 GldJ 条目均断言为 manual review 或 non-SprB construct。

---

