#!/usr/bin/env python3
"""Deterministic delivery gate for the pdca-strict-delivery skill.

Reads an acceptance checklist (JSON), executes each item's verifier, and
prints a pass/fail report. Exit 0 = every item passed; non-zero = a failure
or an untrustworthy checklist.

Key property: the agent's self-reported `status` is IGNORED for the verdict.
The verifier's actual result wins. Coverage can be derived from real artifacts
so a hand-written registration file cannot fake full coverage.
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
BINARY_EXT = (".xlsx", ".xls", ".docx", ".doc", ".pdf", ".pptx", ".png",
              ".jpg", ".jpeg", ".gif", ".zip", ".bin")


def resolve(cwd, path):
    return path if os.path.isabs(path) else os.path.join(cwd, path)


def xlsx_text(path):
    """Extract cell text from xlsx using stdlib only (no openpyxl)."""
    parts = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.iter(S + "si"):
                shared.append("".join(t.text or "" for t in si.iter(S + "t")))
        for name in names:
            if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
                root = ET.fromstring(z.read(name))
                for c in root.iter(S + "c"):
                    v = c.find(S + "v")
                    if v is None:
                        inline = c.find(S + "is")
                        val = "".join(t.text or "" for t in inline.iter(S + "t")) if inline is not None else ""
                    else:
                        val = v.text or ""
                        if c.get("t") == "s":
                            try:
                                val = shared[int(val)]
                            except (ValueError, IndexError):
                                pass
                    if val:
                        parts.append(val)
    return "\n".join(parts)


def docx_text(path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    return "\n".join(t.text or "" for t in root.iter(W + "t"))


def office_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xlsx":
        return xlsx_text(path)
    if ext == ".docx":
        return docx_text(path)
    raise ValueError(f"unsupported office format: {ext}")


def match_pattern(text, pattern, regex):
    if regex:
        return re.search(pattern, text, re.MULTILINE) is not None
    return pattern in text


def verify_file_exists(v, cwd):
    paths = v.get("paths") or ([v["path"]] if "path" in v else [])
    if not paths:
        return False, "no path specified"
    problems = []
    for p in paths:
        fp = resolve(cwd, p)
        if not os.path.exists(fp):
            problems.append(f"missing: {p}")
        elif os.path.getsize(fp) == 0 and v.get("nonempty", True):
            problems.append(f"empty: {p}")
    if problems:
        return False, "; ".join(problems)
    return True, f"{len(paths)} file(s) exist and non-empty"


def verify_file_contains(v, cwd):
    fp = resolve(cwd, v["path"])
    if not os.path.exists(fp):
        return False, f"missing file: {v['path']}"
    if fp.lower().endswith(BINARY_EXT):
        return False, (f"{v['path']} is binary — file_contains cannot read it. "
                       f"Use office_cells (xlsx/docx) or a command verifier.")
    with open(fp, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    pattern = v["pattern"]
    if not match_pattern(text, pattern, v.get("regex", False)):
        return False, f"pattern not found in {v['path']}: {pattern!r}"
    return True, f"pattern found in {v['path']}"


def verify_office_cells(v, cwd):
    """Match text inside xlsx/docx via stdlib zip+xml (no third-party deps)."""
    fp = resolve(cwd, v["path"])
    if not os.path.exists(fp):
        return False, f"missing file: {v['path']}"
    try:
        text = office_text(fp)
    except Exception as exc:
        return False, f"office parse failed: {type(exc).__name__}: {exc}"
    pattern = v.get("pattern")
    if pattern and not match_pattern(text, pattern, v.get("regex", False)):
        return False, f"pattern not found in {v['path']}: {pattern!r}"
    n = len([ln for ln in text.splitlines() if ln.strip()])
    return True, f"office cells read: {n} non-empty value(s) in {v['path']}"


def verify_count(v, cwd):
    pattern = v["glob"]
    matches = glob.glob(resolve(cwd, pattern), recursive=True)
    matches = [m for m in matches if not v.get("files_only", False) or os.path.isfile(m)]
    n = len(matches)
    if "exact" in v and n != v["exact"]:
        return False, f"count {n} != exact {v['exact']} ({pattern})"
    if "min" in v and n < v["min"]:
        return False, f"count {n} < min {v['min']} ({pattern})"
    if "max" in v and n > v["max"]:
        return False, f"count {n} > max {v['max']} ({pattern})"
    return True, f"count {n} satisfies constraint ({pattern})"


def coverage_detail(entries, expected, source):
    unique = set(entries)
    if len(unique) < expected:
        missing_note = ""
        numeric = [e for e in unique if e.isdigit()]
        if len(numeric) == len(unique):
            present = set(int(e) for e in numeric)
            missing = [i for i in range(1, expected + 1) if i not in present]
            if missing:
                missing_note = f"; missing: {missing[:20]}"
        return False, f"coverage {len(unique)}/{expected}{missing_note} ({source})"
    dup = len(entries) - len(unique)
    note = f"; {dup} duplicate line(s)" if dup else ""
    return True, f"coverage {len(unique)}/{expected}{note} ({source})"


def verify_coverage(v, cwd):
    """Prove every member of a known universe was processed.

    Two modes:
      derived_from: glob of REAL artifacts; ids extracted from filenames —
                    coverage computed from outputs, so a hand-written list
                    cannot fake it (preferred).
      items_file:   one identifier per line (fallback; self-reported).
    expected is the size of the universe (e.g. total PDF pages).
    """
    expected = v["expected"]
    if v.get("derived_from"):
        pattern = v["derived_from"]
        files = [m for m in glob.glob(resolve(cwd, pattern), recursive=True) if os.path.isfile(m)]
        id_re = v.get("id_regex")
        entries = []
        for fp in files:
            base = os.path.splitext(os.path.basename(fp))[0]
            if id_re:
                m = re.search(id_re, base)
                if not m:
                    continue
                entries.append(m.group(1) if m.groups() else m.group(0))
            else:
                entries.append(base)
        return coverage_detail(entries, expected, f"derived:{pattern}")
    fp = resolve(cwd, v["items_file"])
    if not os.path.exists(fp):
        return False, f"missing coverage proof file: {v['items_file']}"
    with open(fp, "r", encoding="utf-8", errors="replace") as f:
        entries = [ln.strip() for ln in f if ln.strip()]
    return coverage_detail(entries, expected, v["items_file"])


def verify_command(v, cwd):
    cmd = v["cmd"]
    timeout = v.get("timeout", 120)
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=cwd, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return False, f"command timed out after {timeout}s: {cmd}"
    detail = f"exit {proc.returncode}"
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if out:
        detail += f"; stdout: {out[:300]}"
    if err:
        detail += f"; stderr: {err[:300]}"
    if proc.returncode != 0:
        return False, detail
    return True, detail


VERIFIERS = {
    "file_exists": verify_file_exists,
    "file_contains": verify_file_contains,
    "office_cells": verify_office_cells,
    "count": verify_count,
    "coverage": verify_coverage,
    "command": verify_command,
}


def run_item(item, cwd):
    verify = item.get("verify", {})
    vtype = verify.get("type", "")
    evidence = str(item.get("evidence", "")).strip()

    if vtype == "manual":
        if not evidence:
            return False, "manual item has NO evidence", "manual"
        return True, "manual (evidence provided)", "manual"

    fn = VERIFIERS.get(vtype)
    if fn is None:
        return False, f"unknown verifier type: {vtype!r}", ""
    try:
        ok, detail = fn(verify, cwd)
    except Exception as exc:
        return False, f"verifier error: {type(exc).__name__}: {exc}", ""
    if ok and not evidence:
        # 机器验证通过但缺证据：归为"未记账"，与"自报pass但验证失败"的虚报分开统计
        return False, f"verifier passed but evidence is empty: {detail}", "no_evidence"
    return ok, detail, ""


def main():
    parser = argparse.ArgumentParser(description="PDCA strict delivery gate")
    parser.add_argument("checklist", help="path to acceptance.json")
    parser.add_argument("--base", help="base dir for relative paths (default: parent of checklist dir)")
    parser.add_argument("--max-manual-ratio", type=float, default=0.3,
                        help="fail gate if manual items exceed this share (default 0.3)")
    args = parser.parse_args()

    checklist_path = os.path.abspath(args.checklist)
    if not os.path.exists(checklist_path):
        print(f"[GATE] checklist not found: {checklist_path}")
        sys.exit(2)
    cwd = os.path.abspath(args.base) if args.base else os.path.dirname(os.path.dirname(checklist_path))
    print(f"[GATE] BASE (relative path root): {cwd}")
    with open(checklist_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            print(f"[GATE] invalid JSON: {exc}")
            sys.exit(2)

    items = data.get("items", [])
    if not items:
        print("[GATE] checklist has no items — nothing was defined to verify")
        sys.exit(2)

    print("=" * 64)
    print(f"[GATE] TASK: {data.get('task', '(unnamed)')}")
    print(f"[GATE] ROUND: {data.get('round', '?')}   ITEMS: {len(items)}")
    print("=" * 64)

    passed = failed = fake_pass = manual_n = no_evidence_n = 0
    for item in items:
        iid = item.get("id", "?")
        self_status = str(item.get("status", "")).lower()
        ok, detail, tag = run_item(item, cwd)
        if tag == "no_evidence":
            no_evidence_n += 1
        elif self_status in ("pass", "通过", "true", "done") and not ok:
            fake_pass += 1
        if tag == "manual":
            manual_n += 1
        mark = "PASS" if ok else "FAIL"
        if tag:
            mark += f"({tag})"
        print(f"[{mark}] {iid}: {item.get('desc', '')}")
        print(f"       -> {detail}")
        if ok:
            passed += 1
        else:
            failed += 1
            print(f"       !! self-reported status: {item.get('status', '(none)')!r} (ignored)")

    manual_ratio = manual_n / len(items) if items else 0.0
    ratio_bad = manual_ratio > args.max_manual_ratio
    print("=" * 64)
    print(f"[GATE] RESULT: {passed}/{len(items)} passed, {failed} failed; "
          f"manual {manual_n}/{len(items)} ({manual_ratio:.0%}, limit {args.max_manual_ratio:.0%})")
    if fake_pass:
        print(f"[GATE] WARNING: {fake_pass} item(s) claimed PASS but failed verification — self-report ignored.")
    if no_evidence_n:
        print(f"[GATE] WARNING: {no_evidence_n} item(s) passed verification but have NO evidence — "
              f"recorded as FAIL until evidence is filled in (missing bookkeeping, not a false claim).")
    if ratio_bad:
        print(f"[GATE] LOW CONFIDENCE: manual share {manual_ratio:.0%} exceeds "
              f"{args.max_manual_ratio:.0%}. Convert manual checks to machine verifiers "
              f"(office_cells / command) to make this gate trustworthy.")
        failed += 1
    if failed == 0:
        print("[GATE] ALL GREEN — delivery permitted.")
        sys.exit(0)
    print("[GATE] NOT CLEARED — fix all failed items, then re-run the FULL checklist.")
    sys.exit(1)


if __name__ == "__main__":
    main()
