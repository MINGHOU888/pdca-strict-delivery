#!/usr/bin/env python3
"""Self-learning playbook manager for pdca-strict-delivery.

Stores reusable lessons distilled from defects found in Check phase, so the
next task's Plan phase can inject them as preventive checklist items.

Commands:
  init   <file>                          create an empty playbook
  add    <file> --pattern ... --cause ... --method ... --when ... [--verify ...] [--source ...]
  list   <file> [--when TAG] [--status S] print lessons to inject at Plan time
  mark   <file> --id ID [--effective|--applied|--deprecated]
  check  <file>                          health check (duplicates, stale candidates)

Lesson status: candidate (new) -> proven (validated) -> deprecated (superseded).
Anti-decay: re-adding a near-identical pattern forces an UPGRADE of the old
lesson (not a new duplicate) and resets it to candidate, so repeated failure
of the same kind sharpens the method instead of bloating the library.
"""

import argparse
import difflib
import json
import os
import re
import sys
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load(path):
    if not os.path.exists(path):
        print(f"[PLAY] not found: {path}")
        sys.exit(2)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    data["updated"] = now()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def norm(s):
    return re.sub(r"\s+", "", (s or "").lower())


SIM_THRESHOLD = 0.72
MAX_LESSONS = 20


def similar_pattern(lessons, pattern, threshold=SIM_THRESHOLD):
    """Find a near-identical existing lesson; exact match wins, else fuzzy."""
    target = norm(pattern)
    for l in lessons:
        if norm(l.get("pattern")) == target:
            return l
    best, best_score = None, 0.0
    for l in lessons:
        score = difflib.SequenceMatcher(None, target, norm(l.get("pattern"))).ratio()
        if score > best_score:
            best, best_score = l, score
    return best if best_score >= threshold else None


def cmd_init(args):
    parent = os.path.dirname(os.path.abspath(args.file))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    data = {"schema": 1, "created": now(), "updated": now(), "lessons": []}
    save(args.file, data)
    print(f"[PLAY] initialized: {args.file}")


def cmd_add(args):
    data = load(args.file)
    lessons = data["lessons"]
    pattern = args.pattern.strip()
    tags = [t.strip() for t in args.when.split(",") if t.strip()] if args.when else []

    existing = similar_pattern(lessons, pattern)
    if existing:
        # Anti-decay: same problem recurring => sharpen the existing lesson.
        existing.setdefault("history", []).append({
            "at": now(),
            "event": "recurred-upgraded",
            "old_method": existing.get("method", ""),
        })
        existing["method"] = args.method.strip()
        existing["cause"] = args.cause.strip()
        existing["verify"] = args.verify.strip() if args.verify else existing.get("verify", "")
        existing["when"] = tags or existing.get("when", [])
        existing["status"] = "candidate"
        existing["version"] = existing.get("version", 1) + 1
        existing["applied"] = 0
        existing["effective"] = 0
        existing["updated"] = now()
        save(args.file, data)
        print(f"[PLAY] RECURRENCE -> upgraded {existing['id']} to v{existing['version']} "
              f"(status reset to candidate). Same defect reappearing means the previous "
              f"method was insufficient; sharpen it.")
        return

    n = len(lessons) + 1
    lid = f"L-{n:03d}"
    while any(l.get("id") == lid for l in lessons):
        n += 1
        lid = f"L-{n:03d}"
    lesson = {
        "id": lid,
        "pattern": pattern,
        "cause": args.cause.strip(),
        "method": args.method.strip(),
        "verify": args.verify.strip() if args.verify else "",
        "when": tags,
        "source": args.source.strip() if args.source else "",
        "status": "candidate",
        "version": 1,
        "applied": 0,
        "effective": 0,
        "history": [{"at": now(), "event": "created"}],
        "created": now(),
        "updated": now(),
    }
    lessons.append(lesson)
    save(args.file, data)
    print(f"[PLAY] added {lid}: {pattern}")


def cmd_list(args):
    data = load(args.file)
    rows = data["lessons"]
    if args.when:
        rows = [l for l in rows if args.when in l.get("when", [])]
    if args.status:
        rows = [l for l in rows if l.get("status") == args.status]
    if not rows:
        print("[PLAY] no lessons match.")
        return
    print(f"[PLAY] {len(rows)} lesson(s) — inject applicable ones as PREVENTIVE "
          f"checklist items in Plan phase:")
    for l in rows:
        print("-" * 60)
        print(f"{l['id']} [{l.get('status')}] v{l.get('version',1)} "
              f"applied={l.get('applied',0)} effective={l.get('effective',0)}")
        print(f"  场景(when): {', '.join(l.get('when', [])) or '(any)'}")
        print(f"  问题(pattern): {l.get('pattern')}")
        print(f"  根因(cause): {l.get('cause')}")
        print(f"  最优解(method): {l.get('method')}")
        if l.get("verify"):
            print(f"  转为检查项(verify): {l['verify']}")


def cmd_mark(args):
    data = load(args.file)
    lesson = next((l for l in data["lessons"] if l.get("id") == args.id), None)
    if not lesson:
        print(f"[PLAY] no such id: {args.id}")
        sys.exit(2)
    if args.effective:
        evidence = (args.evidence or "").strip()
        if not evidence:
            print(f"[PLAY] {args.id}: --effective requires --evidence "
                  f"(gate output or user confirmation). No effective credit, no promotion.")
            sys.exit(2)
        lesson.setdefault("evidence_log", []).append({"at": now(), "evidence": evidence})
        lesson["effective"] = lesson.get("effective", 0) + 1
        lesson["applied"] = lesson.get("applied", 0) + 1
    elif args.deprecated:
        lesson["status"] = "deprecated"
    else:
        lesson["applied"] = lesson.get("applied", 0) + 1
    if lesson.get("status") == "candidate" and lesson.get("effective", 0) >= 2:
        lesson["status"] = "proven"
        print(f"[PLAY] {args.id} promoted to PROVEN (effective >= 2).")
    lesson["updated"] = now()
    save(args.file, data)
    print(f"[PLAY] {args.id}: applied={lesson.get('applied',0)} "
          f"effective={lesson.get('effective',0)} status={lesson.get('status')}")


def cmd_check(args):
    data = load(args.file)
    lessons = data["lessons"]
    print("=" * 60)
    print(f"[PLAY] HEALTH CHECK — {len(lessons)} lesson(s)")
    problems = 0

    seen = {}
    for l in lessons:
        k = norm(l.get("pattern"))
        if k in seen:
            print(f"[PLAY][WARN] duplicate pattern: {seen[k]} & {l['id']}")
            problems += 1
        seen[k] = l["id"]

    candidates = [l for l in lessons if l.get("status") == "candidate"]
    stale = [l for l in candidates if l.get("version", 1) > 1 and l.get("effective", 0) == 0]
    for l in stale:
        print(f"[PLAY][WARN] {l['id']} upgraded v{l['version']} but never marked effective "
              f"— verify it in this task's Check phase.")
        problems += 1

    proven = [l for l in lessons if l.get("status") == "proven"]
    if proven:
        print(f"[PLAY] {len(proven)} proven lesson(s) — candidates for permanent "
              f"checklist template:")
        for l in proven:
            print(f"   {l['id']}: {l['pattern']}")

    if len(lessons) > MAX_LESSONS:
        print(f"[PLAY][WARN] {len(lessons)} lessons exceed {MAX_LESSONS} — archive "
              f"old/deprecated ones so the list stays readable and gets injected.")
        problems += 1

    if problems == 0:
        print("[PLAY] healthy. No duplicates or stale upgrades.")
        sys.exit(0)
    else:
        print(f"[PLAY] {problems} issue(s) to resolve.")
        sys.exit(1)


def main():
    p = argparse.ArgumentParser(description="Self-learning playbook manager")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init"); pi.add_argument("file"); pi.set_defaults(fn=cmd_init)
    pa = sub.add_parser("add"); pa.add_argument("file")
    for opt in ("pattern", "cause", "method", "when", "verify", "source"):
        pa.add_argument("--" + opt)
    pa.set_defaults(fn=cmd_add)
    pl = sub.add_parser("list"); pl.add_argument("file")
    pl.add_argument("--when"); pl.add_argument("--status"); pl.set_defaults(fn=cmd_list)
    pm = sub.add_parser("mark"); pm.add_argument("file"); pm.add_argument("--id", required=True)
    pm.add_argument("--evidence", help="required with --effective: gate output or user confirmation")
    g = pm.add_mutually_exclusive_group()
    g.add_argument("--effective", action="store_true")
    g.add_argument("--deprecated", action="store_true")
    g.add_argument("--applied", action="store_true")
    pm.set_defaults(fn=cmd_mark)
    pc = sub.add_parser("check"); pc.add_argument("file"); pc.set_defaults(fn=cmd_check)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
