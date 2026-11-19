# pdca-strict-delivery

把"做完"从自称变成有清单、有证据、有门禁、可复核的闭环。这是一个给 AI Agent 用的工作方法 Skill，治三个老毛病：抽样代替全量、称完成却留尾巴、被指出问题后只挑着改。

而且它**会越用越聪明**：每次踩的坑都沉淀进经验库，下次开工前自动变成预防项——同一个坑不用踩第二遍。

适用于写代码、改 bug、做表格、写文档、整理资料、处理数据、批量操作等一切要交出成果的活。运行期**零 token**：门禁与经验库都是纯本地 Python 脚本，不调用任何大模型。

## 它是怎么工作的

- **十三条铁律**：从"用户明确下达开工指令才算开工"到"达标才交付"，把一次交付拆成可判定的动作。
- **九维分解**：数量、内容、格式、结构、路径、边界、依赖、可复现、可回滚，动手前逐维定全集。
- **机械门禁**：清单里每一项都配机器验证器，脚本实跑取证；自己说"完成了"不算数，脚本说 pass 才算。
- **一处错=一类错**：发现系统性缺陷就全量扫描同类一起修，修完重跑整份清单。
- **双环自学习**：内环保证这次做对，外环把教训沉淀进经验库，下次开工前注入成预防项，少走同样的弯路。→ 详见下一节

## 它会越用越聪明（自学习机制）

大多数 Agent 每次都在犯同一个错，因为没有"记住"的地方。这个 skill 有两个环：

- **内环**（单次任务）：P 计划 → D 执行 → C 自检 → A 复盘，保证这一件事做对、做完、可复核。
- **外环**（跨任务）：A 复盘把这次的教训写进**经验库**；下一次开工的 P 阶段先读经验库，把每条教训变成清单里的**预防项**——同样的坑在计划阶段就被挡住，而不是做完再返工。

经验库就是一个纯本地 JSON 文件 `qa/playbook.json`，每条教训记五样东西：

| 字段 | 记什么 |
|------|--------|
| `pattern` | 什么样的坑（"表格转 Markdown 时合并单元格丢内容"） |
| `cause` | 根因（"按行逐格读取，没处理 rowspan"） |
| `method` | 最优解（"改用 openpyxl 读取合并区域后重建"） |
| `verify` | 怎么变成检查项（"扫产物合并单元格数 = 原文"） |
| `when` | 适用场景标签（`表格` / `OCR` / `编码`），开工时按标签筛 |

### 三个让"自学习"不变成空话的设计

**① 同一个坑再犯，强制升级原条目，不新增重复。**
第一次踩坑的方法不够好，就得 sharpen，而不是让经验库堆满近义条目。`playbook.py add` 用相似度匹配（difflib）识别重复 pattern，自动把 `method` 换成新解法、`version+1`、状态打回 `candidate`、统计清零——**升级了却从未验证有效**的条目会被 `playbook.py check` 揪出来。

**② 没证据不许记功。**
经验从 `candidate` 晋升 `proven` 靠的是真挡下过问题，不是自我声明。`mark --effective` 强制带 `--evidence`（门禁实跑输出或用户确认），没有证据就没有有效次数，晋升无从谈起。

**③ 反复修不好，本身就是最高价值的经验。**
内环 5 轮仍不过时，不只是如实报告就结束——把"为什么反复修不好"深度提炼成一条新经验写入库。**失败被转化成知识**，所以系统不会在同一类任务上反复卡死。

### 真实运行记录

以下是从实际项目里跑出来的经验库条目，未经修饰：

```json
{
  "id": "L-003",
  "pattern": "PDCA验收清单的 command 项内嵌多行 Python（JSON里写 \\n）会被当字面字符致语法错",
  "cause": "JSON 字符串里的 \\n 传给 python -c 时是字面反斜杠n不是真换行，for 循环体首行报 SyntaxError；门禁把这种 command 判 FAIL，产物其实没错（本轮 LINK-01/QA-01 实测）",
  "method": "凡需要多行逻辑的验证，一律写成独立 .py 脚本落 qa/，command 只写『python 脚本路径 参数』；脚本内用真换行、输出 scanned=N/expected=M，既免转义又复现",
  "when": ["PDCA清单command验证/含for或多行python/JSON内嵌脚本"],
  "status": "candidate",
  "applied": 1,
  "effective": 1
}
```

这条经验是这么产生的：门禁把一项**其实没问题的产物**判成 FAIL。根因查清后写进经验库；下一次再写多行 `command` 验证器时，P 阶段就把这条注入成预防项，直接要求写成独立脚本——**这个坑从此不用再踩第二遍**。

### 三条命令跑起来

```bash
# 开工前：按本任务标签取回适用经验，转成清单里的预防项
python scripts/playbook.py list qa/playbook.json --when 表格

# 做完复盘：把可复用的坑写进经验库（pattern/cause/method/verify/when 填全）
python scripts/playbook.py add qa/playbook.json --pattern "..." --cause "..." --method "..." --verify "..." --when 表格

# 交付前：检查经验库健康度（揪出"升级过却没验证有效"的条目、超过 20 条告警归档）
python scripts/playbook.py check qa/playbook.json
```

**零 token**：经验库的读写、相似度匹配、状态机晋升全部由本地 Python 脚本完成，运行期不调用任何大模型。

**新用户从空开始**：仓库里的 `qa/playbook.json` 初始是空的（`lessons: []`），你的经验库由你自己的实战长出来。想先看看一条经验长什么样，`assets/playbook.demo.json` 里有 4 条真实记录可以直接参考格式。

## 安装

### 方式一：作为 WorkBuddy Skill 使用

把本仓库整个目录复制到你的 skills 目录，改名为 `pdca-strict-delivery`：

```bash
# Windows
git clone <你的仓库地址> pdca-strict-delivery
copy /Y pdca-strict-delivery "%USERPROFILE%\.workbuddy\skills\"
# macOS / Linux
git clone <你的仓库地址> ~/.workbuddy/skills/pdca-strict-delivery
```

复制后确认目录结构是 `skills/pdca-strict-delivery/SKILL.md`，重启客户端即可识别。

### 方式二：当作通用提示词使用（不依赖任何工具）

直接把仓库根目录的 `全量交付PDCA.md` 里 `---` 之间的整段，复制到你常用 AI 的每次任务开头。没有脚本环境也能用，靠文字约定达成同样的闭环。

## 使用

1. **下达任务**：给出明确的工作指令，并把边界说清楚（例如"一共几项你先数出来"）。
2. **AI 建清单**：它会先落一份 `qa/acceptance.json`，逐项列清验收标准和证据要求。
3. **AI 执行 + 自检**：按清单全量做，完成后跑门禁 `python scripts/verify_delivery.py qa/acceptance.json`，exit 0 且全项 pass 才交付。
4. **你按报告复核**：只认带数字和逐项结果的自检报告，表述清晰、数字对得上才算通过。

开工授权：AI 只有在你明确下达开工指令后才动手，其余表述视为讨论。这条门槛是为了避免理解偏差导致返工、白烧成本。你可按自己的习惯定义这个开工指令，并在 SKILL.md 和提示词里写明它是什么。

## 快速上手示例

仓库 `references/domain-pdf-obsidian.md` 和 `assets/acceptance_checklist.template.json` 给了一个完整示例：把一批资料全量整理成结构化笔记并落库到 Obsidian（一个用户量很大的笔记工具）。它示范了怎么锁定全集、怎么建 coverage 项、怎么让"全量"由脚本保证、怎么写门禁。照着改就能用到自己的任务上。

## 目录结构

```
pdca-strict-delivery/
├── SKILL.md                  # 核心规则（WorkBuddy Skill 入口）
├── 全量交付PDCA.md           # 无工具依赖的通用提示词版
├── README.md                 # 本文件
├── LICENSE                   # MIT 协议（英文原文，具法律效力）
├── LICENSE-zh.md             # MIT 协议中文版（大白话 + 中文译本，方便看懂）
├── scripts/
│   ├── verify_delivery.py    # 确定性门禁，交付前必跑
│   ├── playbook.py           # 经验库管理（init/add/list/mark/check）
│   ├── _guard.py             # 覆盖度断言、矛盾行检查
│   ├── run_all.py            # 批量任务引擎
│   ├── snapshot_spec.py      # 过程快照
│   └── pycompile_all.py      # 全量语法编译检查
├── references/
│   ├── checklist-schema.md   # 清单 schema、验证器详解
│   ├── pdca-loop.md          # PDCA 详解、失败模式与对策
│   ├── self-learning.md      # 双环自学习与防衰减
│   └── domain-pdf-obsidian.md# 场景示例（资料整理→Obsidian 落库）
├── assets/
│   ├── acceptance_checklist.template.json
│   ├── playbook.template.json
│   ├── playbook.demo.json     # 真实经验条目示例（4 条，可参考格式）
│   ├── self_check_report.template.md
│   ├── registry.template.json
│   ├── handover.template.md
│   ├── backup_template.py
│   └── 全量交付PDCA.md       # 提示词副本（与根目录同源）
└── qa/
    └── playbook.json         # 空经验库，随用随沉淀
```

## 许可与出处

本项目以 **MIT 协议**发布：你可以自由使用、复制、修改、合并、发布、分发、再许可，甚至**商用售卖**，唯一要求是在副本或实质性部分中**保留版权声明和许可声明**（即标明出处）。详见 [LICENSE](LICENSE)（英文原文）；看不懂英文？看 [LICENSE-zh.md](LICENSE-zh.md) 中文版（含大白话说明与中文译本）。

> 说明：英文 `LICENSE` 是唯一具法律效力的版本，也必须保留以便 GitHub 自动识别协议；中文版仅作理解用，如有出入以英文原文为准。

出处：pdca-strict-delivery contributors。如果你基于它做了衍生作品，保留上述声明即满足 MIT 要求。
