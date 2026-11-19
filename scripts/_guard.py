"""公共护栏：全集断言与扫描数上报。

所有检查器必须调用 assert_universe()，保证：
  1. 扫描数量与期望一致（漏扫 = FAIL）
  2. 零扫描不能蒙混过关
  3. 输出里必须带 scanned=N/expected=M，让"检查通过"可被外部核对

用法：
    from _guard import assert_universe, scanned_line
    assert_universe(found=62, expected=62, label="章节卡")

单独运行本文件 = 自检：跑三种反例（漏扫/零扫/正常），全对才 exit 0。
"""
import sys

__all__ = ["assert_universe", "scanned_line", "GuardError", "require_files", "require_no_forbidden"]


class GuardError(AssertionError):
    """护栏断言失败。"""


def scanned_line(found, expected, label):
    """生成统一的扫描数上报行。"""
    return f"[扫描] {label}: scanned={found}/expected={expected}"


def assert_universe(found, expected, label):
    """断言扫描全集数量正确。漏扫/零扫/超扫一律抛 GuardError。

    返回 scanned_line 输出，方便调用方直接打印。
    """
    if expected <= 0:
        raise GuardError(f"{label}: expected 必须为正整数，实际 {expected}")
    if found == 0:
        raise GuardError(f"{label}: 扫描到 0 个产物（零产物不得判通过）")
    if found < expected:
        raise GuardError(f"{label}: 漏扫，scanned={found}/expected={expected}")
    if found > expected:
        raise GuardError(f"{label}: 超扫，scanned={found}/expected={expected}")
    return scanned_line(found, expected, label)


def require_files(paths, label="必需文件"):
    """断言一组路径全部存在且非空。"""
    import os

    missing = [p for p in paths if not (os.path.isfile(p) and os.path.getsize(p) > 0)]
    if missing:
        raise GuardError(f"{label}: 缺失或为空 {len(missing)} 项 -> {missing[:5]}")
    return f"[OK] {label}: {len(paths)}/{len(paths)}"


def require_no_forbidden(text, forbidden, label="禁用内容"):
    """断言文本不含禁用词。用于边界扫描（禁词表由调用方给）。"""
    hits = [w for w in forbidden if w in text]
    if hits:
        raise GuardError(f"{label}: 命中 {hits[:5]}")
    return f"[OK] {label}: 未命中"


def _selfcheck():
    """反例自检：三种情况必须分别成立。"""
    cases = []
    # 正常
    try:
        assert_universe(62, 62, "章节卡")
        cases.append(("正常 62/62 应通过", True))
    except GuardError:
        cases.append(("正常 62/62 应通过", False))
    # 漏扫
    try:
        assert_universe(38, 62, "章节卡")
        cases.append(("漏扫 38/62 应报错", False))
    except GuardError:
        cases.append(("漏扫 38/62 应报错", True))
    # 零扫
    try:
        assert_universe(0, 62, "章节卡")
        cases.append(("零扫 0/62 应报错", False))
    except GuardError:
        cases.append(("零扫 0/62 应报错", True))
    # 超扫
    try:
        assert_universe(70, 62, "章节卡")
        cases.append(("超扫 70/62 应报错", False))
    except GuardError:
        cases.append(("超扫 70/62 应报错", True))

    ok = all(v for _, v in cases)
    for name, passed in cases:
        print(f"[{'OK' if passed else 'FAIL'}] {name}")
    print(f"[汇总] _guard 反例自检 {'ALL GREEN' if ok else 'HAS FAILURE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_selfcheck())
