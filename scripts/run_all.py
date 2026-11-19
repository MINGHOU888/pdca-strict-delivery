"""PDCA 任务注册表：声明式描述"要做什么、按什么次序、哪些要模型判断"。

分层设计（改内容不改引擎）：
  第1层 registry.json  —— 任务清单/依赖/次序/是否 requires_model   ← 按项目改
  第2层 run_all.py     —— 固定引擎：拓扑排序→分批→写 progress.json→--resume→失败不跳过
  第3层 templates/     —— 样板卡与产物模板                            ← 按项目改

registry.json 结构：
{
  "project": "示例项目",
  "base": "D:/path/to/project",
  "python": "D:/Python313/python.exe",
  "batches": [
    {
      "id": "B1",
      "title": "第一批：骨架生成",
      "tasks": [
        {"id": "gen-skeleton", "cmd": "python scripts/gen.py", "requires_model": false,
         "desc": "批量生成卡片骨架", "timeout": 300},
        {"id": "fill-content", "requires_model": true,
         "desc": "逐张填语义内容（模型做，脚本不碰）"}
      ]
    }
  ]
}

requires_model=true 的任务不执行命令，只登记为"待模型执行"节点，
引擎会把它标成 pending_model 并继续下一个可执行任务，人/模型处理完手动置 done。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def load_registry(path):
    if not os.path.isfile(path):
        raise SystemExit(f"[FAIL] 注册表不存在: {path}")
    with open(path, encoding="utf-8") as f:
        reg = json.load(f)
    for key in ("project", "base", "batches"):
        if key not in reg:
            raise SystemExit(f"[FAIL] 注册表缺字段: {key}")
    return reg


def flatten(reg):
    """批次展开成线性任务序列，保留批次信息与全局序号。"""
    tasks = []
    for b_idx, batch in enumerate(reg["batches"], 1):
        for t_idx, task in enumerate(batch.get("tasks", []), 1):
            item = dict(task)
            item["batch_id"] = batch.get("id", f"B{b_idx}")
            item["batch_title"] = batch.get("title", "")
            item["seq"] = len(tasks) + 1
            item.setdefault("requires_model", False)
            item.setdefault("timeout", 300)
            item.setdefault("desc", "")
            tasks.append(item)
    return tasks


def progress_path(reg):
    return os.path.join(reg["base"], "qa", "progress.json")


def load_progress(reg):
    p = progress_path(reg)
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"round": 0, "done": {}, "failed": {}, "pending_model": []}


def save_progress(reg, prog):
    p = progress_path(reg)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(prog, f, ensure_ascii=False, indent=2)
    return p


def resolve_cmd(reg, cmd):
    """把 {python} {base} 占位符替换成实际值。"""
    return (cmd.replace("{python}", reg.get("python", sys.executable))
                .replace("{base}", reg["base"]))


def run_task(reg, task):
    """执行一个 shell 任务，返回 (ok, 输出摘要)。

    工作目录固定为 reg['base']，让注册表里的相对路径 cmd（如 qa/check_x.py）
    在任何调用位置都能正确解析。
    """
    cmd = resolve_cmd(reg, task["cmd"])
    started = time.time()
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=task["timeout"],
                           cwd=reg["base"] if os.path.isdir(reg["base"]) else None)
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT after {task['timeout']}s"
    cost = time.time() - started
    tail = [l for l in (r.stdout or "").strip().splitlines() if l.strip()]
    key = ""
    for l in reversed(tail):
        if l.startswith("[汇总]") or l.startswith("[扫描]") or "[OK]" in l:
            key = l
            break
    summary = f"exit={r.returncode} {cost:.1f}s {key or (tail[-1] if tail else '')}"
    if r.returncode != 0 and not key:
        summary += " | " + " ".join((r.stderr or "").strip().splitlines()[-1:])[:200]
    return r.returncode == 0, summary


def main():
    ap = argparse.ArgumentParser(description="PDCA 任务编排引擎")
    ap.add_argument("registry", help="registry.json 路径")
    ap.add_argument("--resume", action="store_true", help="断点续跑，跳过已完成任务")
    ap.add_argument("--dry-run", action="store_true", help="只列任务不执行")
    ap.add_argument("--batch", default="", help="只跑指定批次 id")
    ap.add_argument("--max-rounds", type=int, default=3, help="失败重跑上限")
    args = ap.parse_args()

    reg = load_registry(args.registry)
    tasks = flatten(reg)
    prog = load_progress(reg)
    prog["round"] = prog.get("round", 0) + 1
    prog.setdefault("done", {})
    prog.setdefault("failed", {})
    prog.setdefault("pending_model", [])

    print(f"[引擎] 项目={reg['project']} 任务数={len(tasks)} 轮次={prog['round']}")
    if args.dry_run:
        for t in tasks:
            kind = "模型" if t["requires_model"] else "脚本"
            print(f"  {t['seq']:>2} [{t['batch_id']}] {kind} {t['id']} - {t['desc']}")
        return 0

    failed_any = False
    for t in tasks:
        if args.batch and t["batch_id"] != args.batch:
            continue
        if args.resume and t["id"] in prog["done"]:
            print(f"[跳过] {t['id']} 已完成")
            continue
        if t["requires_model"]:
            prog["pending_model"] = sorted(set(prog["pending_model"] + [t["id"]]))
            print(f"[待模型] {t['id']} - {t['desc']}")
            continue
        ok, summary = run_task(reg, t)
        if ok:
            prog["done"][t["id"]] = {"summary": summary, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
            prog["failed"].pop(t["id"], None)
            print(f"[通过] {t['id']} {summary}")
        else:
            prog["failed"][t["id"]] = {"summary": summary, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
            failed_any = True
            print(f"[失败] {t['id']} {summary}")
        save_progress(reg, prog)

    save_progress(reg, prog)
    done_n = len(prog["done"])
    fail_n = len(prog["failed"])
    pend_n = len(prog["pending_model"])
    print(f"[汇总] 完成={done_n} 失败={fail_n} 待模型={pend_n} "
          f"总任务={len(tasks)} {'ALL GREEN' if fail_n == 0 else 'HAS FAILURE'}")
    return 1 if failed_any else 0


if __name__ == "__main__":
    sys.exit(main())
