"""从样板产物反推规格：字段集、标题集、高频实体词。

用途：内容锚点与格式检查器不该凭想象配置，而应从真实样板抽取。
做法：先写 2-3 张样板 → 跑本脚本抽规格草稿 → 人确认 → 写入锚点配置。

用法：
    python snapshot_spec.py --sample "output/p001.md" "output/p002.md" --kind card
    python snapshot_spec.py --sample <glob 前缀>*.md --kind card --out qa/spec_draft.json
"""
import argparse
import glob
import json
import os
import re
import sys


def extract(text):
    """抽一份样板的结构特征。"""
    fm = {}
    m = re.search(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            km = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
            if km:
                fm[km.group(1)] = km.group(2).strip()
    heads = re.findall(r"^##\s+(.+)$", text, re.M)
    quotes = re.findall(r"^>\s?(.*)$", text, re.M)
    nums = re.findall(r"\d[\d,\.]*\s*[%亿万]?", text)
    entities = re.findall(r"[A-Za-z]{3,}", text)
    cn_nums = re.findall(r"\d{4}\s*年|\d+\s*万|\d+\s*亿|\d+\.\d+\s*%", text)
    return {
        "frontmatter_fields": sorted(fm.keys()),
        "h2_headings": heads,
        "quote_count": len(quotes),
        "quote_chars": sum(len(re.sub(r"\s+", "", q)) for q in quotes),
        "number_tokens": nums[:40],
        "cn_numeric_tokens": cn_nums[:40],
        "latin_entities": sorted(set(entities))[:40],
        "char_count": len(text),
    }


def merge(samples):
    """合并多份样板：字段/标题取交集与并集各存一份。"""
    if not samples:
        raise SystemExit("[FAIL] 没有样板可抽")
    all_fm = [s["frontmatter_fields"] for s in samples]
    all_h = [s["h2_headings"] for s in samples]
    inter_fm = set(all_fm[0]).intersection(*[set(x) for x in all_fm[1:]]) if len(all_fm) > 1 else set(all_fm[0])
    union_fm = set().union(*[set(x) for x in all_fm])
    inter_h = set(all_h[0]).intersection(*[set(x) for x in all_h[1:]]) if len(all_h) > 1 else set(all_h[0])
    union_h = []
    for h in all_h:
        for x in h:
            if x not in union_h:
                union_h.append(x)
    ents = {}
    for s in samples:
        for e in s["latin_entities"]:
            ents[e] = ents.get(e, 0) + 1
    cn = []
    for s in samples:
        for x in s["cn_numeric_tokens"]:
            if x not in cn:
                cn.append(x)
    return {
        "sample_count": len(samples),
        "frontmatter_required_candidates": sorted(inter_fm),
        "frontmatter_optional_candidates": sorted(union_fm - inter_fm),
        "h2_required_candidates": sorted(inter_h),
        "h2_optional_candidates": [h for h in union_h if h not in inter_h],
        "latin_entity_freq": dict(sorted(ents.items(), key=lambda kv: -kv[1])[:40]),
        "cn_numeric_candidates": cn[:40],
        "quote_chars_range": [min(s["quote_chars"] for s in samples),
                              max(s["quote_chars"] for s in samples)],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", nargs="+", required=True, help="样板文件或 glob 前缀")
    ap.add_argument("--out", default="", help="输出 json 路径")
    args = ap.parse_args()

    files = []
    for pat in args.sample:
        if os.path.isfile(pat):
            files.append(pat)
        else:
            files.extend(sorted(glob.glob(pat)))
    files = sorted(set(files))
    if not files:
        print(f"[FAIL] 样板未命中: {args.sample}")
        return 1

    samples = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            samples.append(extract(fh.read()))
    spec = merge(samples)
    spec["sample_files"] = files[:10]

    print(f"[扫描] 样板: scanned={len(files)}/expected={len(files)}")
    print(json.dumps(spec, ensure_ascii=False, indent=2))
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(spec, fh, ensure_ascii=False, indent=2)
        print(f"[OK] 规格草稿已写: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
