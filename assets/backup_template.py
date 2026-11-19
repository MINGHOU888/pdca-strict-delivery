"""通用过程资产备份器（模板）。

把"跨会话有价值、换机不跟随"的本地资产打成快照包：
  - 技能（skill）目录
  - 经验库（playbook.json）
  - 验收脚本与清单
  - 两层记忆（用户级 MEMORY.md、工作区 memory/）
  - 换机说明书

三条铁律：
  1. 敏感数据不外流：隐私截图、账户凭证、密钥文件不进包；正文中的金额/账号按脱敏规则处理。
  2. 只写不删：备份只新建文件，不改动源资产。
  3. 可核验：包内带 manifest（文件清单 + sha256），restore 时逐项校验。

用法（改配置后使用）：
    python backup.py --config config.json            # 打一个包
    python backup.py --config config.json --dry-run   # 只列将打包的内容
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile

VERSION = "1.0"

# 默认脱敏规则：金额、账号、密钥形态。命中即替换。
DEFAULT_MASKS = [
    (re.compile(r"\d[\d,]*\.\d+\s*(?:万|亿)"), "[金额]"),
    (re.compile(r"\b\d{6,12}\b(?=[^0-9]|$)"), "[账号]"),
    (re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9_\-]{24,}(?![A-Za-z0-9])"), "[密钥]"),
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def mask_text(text, masks):
    for pat, repl in masks:
        text = pat.sub(repl, text)
    return text


def collect(cfg):
    """按配置收集待打包文件，返回 [(源路径, 包内相对路径, 是否脱敏)]。"""
    items = []
    exclude_names = set(cfg.get("exclude_names", []))
    exclude_suffix = tuple(cfg.get("exclude_suffix", []))
    for entry in cfg["include"]:
        src = entry["src"]
        root = entry["root"]
        name_filter = entry.get("include_names")
        mask = entry.get("mask", False)
        if not os.path.exists(root):
            continue
        if os.path.isfile(root):
            items.append((root, os.path.join(name_filter[0] if name_filter else "misc",
                                            os.path.basename(root)), mask))
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in exclude_names and d != "__pycache__"]
            for fn in filenames:
                if fn in exclude_names or fn.endswith(exclude_suffix):
                    continue
                if name_filter and not any(fn.startswith(p) for p in name_filter):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root).replace("\\", "/")
                items.append((full, os.path.join(name_filter[0] if name_filter else "misc", rel)
                              .replace("\\", "/"), mask))
    return items


def build(cfg, out_dir, dry_run=False):
    items = collect(cfg)
    if not items:
        print("[FAIL] 未收集到任何文件，配置有误")
        return 1, None
    if dry_run:
        print(f"[扫描] 待打包: scanned={len(items)}/expected={len(items)}")
        for src, rel, _ in items:
            print(f"  {src}  ->  {rel}")
        return 0, None

    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    pkg = os.path.join(out_dir, f"assets-{stamp}.zip")
    manifest = {"version": VERSION, "created": stamp, "files": []}

    masks = [(re.compile(p), r) for p, r in cfg.get("masks", DEFAULT_MASKS)]
    with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as z:
        for src, rel, need_mask in items:
            data = None
            if need_mask and src.lower().endswith((".md", ".txt", ".json", ".yaml", ".yml")):
                with open(src, encoding="utf-8", errors="replace") as f:
                    data = mask_text(f.read(), masks).encode("utf-8")
            if data is None:
                with open(src, "rb") as f:
                    data = f.read()
            z.writestr(rel, data)
            manifest["files"].append({"path": rel, "size": len(data),
                                      "sha256": hashlib.sha256(data).hexdigest(),
                                      "masked": bool(need_mask), "source": src})
        z.writestr("MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"[扫描] 已打包: scanned={len(items)}/expected={len(items)}")
    print(f"[OK] 快照包: {pkg} ({os.path.getsize(pkg)} 字节)")
    return 0, pkg


def prune(out_dir, keep):
    """保留最近 keep 个包，其余移到 _old（不删除）。"""
    if not os.path.isdir(out_dir):
        return 0
    pkgs = sorted([os.path.join(out_dir, f) for f in os.listdir(out_dir)
                   if f.startswith("assets-") and f.endswith(".zip")])
    moved = 0
    for p in pkgs[:-keep] if keep > 0 else pkgs:
        old = os.path.join(out_dir, "_old")
        os.makedirs(old, exist_ok=True)
        shutil.move(p, os.path.join(old, os.path.basename(p)))
        moved += 1
    if moved:
        print(f"[OK] 轮转: 移出 {moved} 个旧包到 _old/")
    return moved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep", type=int, default=0, help="保留最近 N 个包（0=用配置）")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    out_dir = cfg.get("out_dir") or os.path.join(os.path.dirname(os.path.abspath(args.config)), "out")
    rc, pkg = build(cfg, out_dir, args.dry_run)
    if rc:
        return rc
    if pkg:
        keep = args.keep or cfg.get("keep", 10)
        prune(out_dir, keep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
