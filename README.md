# pdca-strict-delivery

把"做完"从自称变成有清单、有证据、有门禁、可复核的闭环。这是一个给 AI Agent 用的工作方法 Skill，治三个老毛病：抽样代替全量、称完成却留尾巴、被指出问题后只挑着改。

适用于写代码、改 bug、做表格、写文档、整理资料、处理数据、批量操作等一切要交出成果的活。运行期**零 token**：门禁与经验库都是纯本地 Python 脚本，不调用任何大模型。

## 它是怎么工作的

- **十三条铁律**：从"用户明确下达开工指令才算开工"到"达标才交付"，把一次交付拆成可判定的动作。
- **九维分解**：数量、内容、格式、结构、路径、边界、依赖、可复现、可回滚，动手前逐维定全集。
- **机械门禁**：清单里每一项都配机器验证器，脚本实跑取证；自己说"完成了"不算数，脚本说 pass 才算。
- **一处错=一类错**：发现系统性缺陷就全量扫描同类一起修，修完重跑整份清单。
- **双环自学习**：内环保证这次做对，外环把教训沉淀进经验库，下次开工前注入成预防项，少走同样的弯路。

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
