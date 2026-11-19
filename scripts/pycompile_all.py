"""全量 python 语法编译自检。

含正则、含中文、含路径的脚本一律用 Write 落盘再跑（Git Bash heredoc 会把 \\s 转成 /s，
这是已知环境坑）。本脚本负责在交付前把所有 .py 编译一遍，把语法错挡在交付之前。

用法：
    python pycompile_all.py                      # 编译默认范围
    python pycompile_all.py --root D:/x --root D:/y
    python pycompile_all.py --root ... --exclude tests
"""
import argparse
import compileall
import os
import py_compile
import shutil
import sys
import tempfile


def iter_py(root, exclude_dirs):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in exclude_dirs and not d.startswith(".") and d != "__pycache__"]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", action="append", default=[], help="待扫描目录，可多次")
    ap.add_argument("--exclude", action="append", default=["__pycache__", "node_modules", ".git"],
                    help="排除目录名")
    args = ap.parse_args()

    roots = args.root or [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets"),
    ]
    total, bad = 0, []
    # Windows 上 os.devnull('nul') 不是常规文件，py_compile 会报错，改用临时目录
    tmpdir = tempfile.mkdtemp(prefix="pycompile_")
    try:
        for root in roots:
            root = os.path.abspath(root)
            if not os.path.isdir(root):
                print(f"[跳过] 目录不存在: {root}")
                continue
            for py in iter_py(root, set(args.exclude)):
                total += 1
                cfile = os.path.join(tmpdir, "out.pyc")
                try:
                    py_compile.compile(py, doraise=True, cfile=cfile)
                except py_compile.PyCompileError as e:
                    bad.append((py, str(e).splitlines()[-1] if str(e) else "compile error"))
                except Exception as e:
                    bad.append((py, f"{type(e).__name__}: {e}"))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    print(f"[扫描] python 文件: scanned={total}/expected={total}")
    if bad:
        for p, e in bad:
            print(f"[FAIL] {p} :: {e}")
        print(f"[汇总] 编译失败 {len(bad)}/{total}")
        return 1
    print(f"[汇总] 全部通过 {total}/{total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
