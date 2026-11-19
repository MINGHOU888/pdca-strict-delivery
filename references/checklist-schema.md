# 验收清单 Schema

验收清单是一个 JSON 文件，约定落盘为 `qa/acceptance.json`。门禁脚本 `verify_delivery.py` 按此 schema 解析。

## 顶层结构

```json
{
  "task": "任务描述",
  "round": 1,
  "universe": { "description": "...", "total": 47, "unit": "页", "source": "..." },
  "items": [ { ... } ]
}
```

- `task`：任务一句话描述。
- `round`：当前 PDCA 迭代轮次，从 1 开始，每次回归 +1，上限 5。
- `universe`：全集边界，`total` 必须是确定数字，是覆盖度检查的依据。
- `items`：验收项数组。

## 单项结构

```json
{
  "id": "COV-01",
  "desc": "人可读的检查描述",
  "verify": { "type": "...", "...": "..." },
  "status": "pending",
  "evidence": ""
}
```

- `id`：唯一标识，建议前缀分类（COV 覆盖 / TEXT 内容 / TABLE 表格 / LIB 落库 / QA 缺陷 / HUMAN 人工）。
- `desc`：说清楚这一项到底验什么，不允许含糊。
- `verify`：机器验证器，见下。
- `status`：自报状态。**门禁会忽略它**，仅用于暴露虚报。
- `evidence`：非空证据字符串。机器验证通过但证据为空 → 仍判失败。

## 验证器类型

### `coverage` — 全集覆盖证明
两种模式，**优先用第一种**：

```json
{ "type": "coverage", "expected": 47, "derived_from": "output/p*.md", "id_regex": "p(\\d+)" }
```
`derived_from` 是真实产物的 glob，脚本从**实际文件名**提取标识（用 `id_regex` 的捕获组，无正则时取文件名去扩展名）统计去重，与 `expected` 比较。覆盖数由产物反推，模型手写的登记表无法伪造覆盖——**推荐所有批量任务用它**。

```json
{ "type": "coverage", "expected": 47, "items_file": "qa/processed_pages.txt" }
```
`items_file` 每行写一个已处理项的标识（页码/文件名/ID），属自报的降级模式。脚本统计去重行数与 `expected` 比较；若全为数字还能推断缺失页码。**这是治"挑着做"的核心验证器，任何批量任务都必须至少有一项 coverage。**

### `file_exists` — 文件存在且非空
```json
{ "type": "file_exists", "paths": ["output/p001.md", "output/p002.md"] }
```
也接受单个 `path`。`nonempty: false` 可允许空文件。

### `file_contains` — 文件内容匹配
```json
{ "type": "file_contains", "path": "output/p001.md", "pattern": "证券", "regex": false }
```
`regex: true` 时 pattern 作为正则（多行模式）。**二进制文件（xlsx/docx/pdf 等）会明确报错并提示改用 `office_cells` 或 `command`，不再静默读成乱码。**

### `office_cells` — Office 文档内容匹配（无需第三方库）
```json
{ "type": "office_cells", "path": "output/report.xlsx", "pattern": "总资产" }
```
用标准库 zip+xml 解析 xlsx/docx 的文本后匹配 `pattern`（`regex` 可选）。省去 openpyxl 依赖；你的表格、报表、Word 文档都用它验内容。`pattern` 省略时只校验能否读出内容。

### `count` — 文件数量核对
```json
{ "type": "count", "glob": "vault/Notes/*.md", "exact": 47, "files_only": true }
```
支持 `exact`（精确）、`min`（下限）、`max`（上限），可组合。`glob` 支持 `**` 递归。

### `command` — 执行命令
```json
{ "type": "command", "cmd": "python scripts/scan_defects.py output/ --strict", "timeout": 120 }
```
退出码 0 为通过。stdout/stderr 会被截断展示。复杂的自定义检查（表格数、乱码扫描、字段完整性）都用它实现。

### `manual` — 需人工确认
```json
{ "type": "manual" }
```
机器无法验证，但 `evidence` 必须非空，输出中标注"需人工确认"。尽量少用；能把主观判断转成可枚举规则的，就改成 `command`。**门禁会统计 manual 项占比，超过阈值（默认 30%，`--max-manual-ratio` 可调）即判"门禁可信度不足"并非零退出——manual 堆多了等于自检失效。**

## 路径基准

所有相对路径以 **checklist 所在目录的父目录（项目根目录）** 为基准解析——因为清单约定落盘为 `qa/acceptance.json`，其父目录就是项目根。因此模板里写 `qa/processed_pages.txt`、`output/p001.md`、`vault/...` 都是相对项目根的，一目了然。可用 `--base <目录>` 覆盖基准。绝对路径原样使用。

## 设计清单的三条经验

1. **先写 coverage 项**：它定义了"全集"，是所有工作的骨架。
2. **质量项要可判定**："表格转好了"不可判定，"表格数 = 原文表格数 且无损毁"可判定。
3. **给每类缺陷配一个 command 扫描器**：一次发现的错误，写成脚本扫遍全集，既修复又防复发。
