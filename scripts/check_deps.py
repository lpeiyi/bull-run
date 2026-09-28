# -*- coding: utf-8 -*-
"""依赖核查：比对 requirements.txt 与实际安装版本。

用法（项目根目录）：
  python scripts/check_deps.py             # 逐包报告版本是否一致
  python scripts/check_deps.py --missing   # 只判断是否有包未安装（供 start.bat 使用）
                                           # 有缺失则退出码 1，否则 0

退出码：0 = 满足；1 = 有不满足项。

背景见 ROADMAP 第 4 项：requirements.txt 改为精确锁定后，需要一个可重复执行的核查手段，
避免"文件改了但环境没变"这种假安全。
"""
import argparse
import importlib.metadata as md
import os
import re
import sys

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REQ_FILE = os.path.join(_BASE, "requirements.txt")

# 只认精确锁定：<包> == <版本>
_PIN_RE = re.compile(r"^([A-Za-z0-9._-]+)\s*==\s*([^\s;#]+)\s*$")


def parse_requirements(path):
    """解析依赖文件中的精确锁定行。

    忽略：空行、`#` 注释、`-r/-c/-e/--xxx` 指令行。

    返回 (pins, skipped)：
      pins    —— [(包名, 版本)]，来自 `<包>==<版本>` 行，保持文件顺序
      skipped —— [原始行]，像依赖声明但未精确锁定（如 `requests>=2.28`、`flask`）
    """
    pins, skipped = [], []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return pins, skipped

    for line in lines:
        raw = line.strip()
        if not raw or raw.startswith("#") or raw.startswith("-"):
            continue
        # 去掉行尾注释与环境标记后再判断
        core = raw.split(";")[0].split("#")[0].strip()
        if not core:
            continue
        m = _PIN_RE.match(core)
        if m:
            pins.append((m.group(1), m.group(2)))
        else:
            skipped.append(raw)
    return pins, skipped


def check(pins):
    """比对 [(name, expected)] 与实装版本。

    返回 [{"name","expected","installed","status"}]，status ∈ ok / missing / mismatch。
    """
    results = []
    for name, expected in pins:
        try:
            installed = md.version(name)
        except md.PackageNotFoundError:
            installed = None
        if installed is None:
            status = "missing"
        elif installed == expected:
            status = "ok"
        else:
            status = "mismatch"
        results.append({"name": name, "expected": expected,
                        "installed": installed, "status": status})
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="核查 requirements.txt 与实际安装版本是否一致")
    parser.add_argument("--requirements", default=_REQ_FILE,
                        help="依赖文件路径（默认项目根 requirements.txt）")
    parser.add_argument("--missing", action="store_true",
                        help="只判断是否有包未安装；有缺失则退出码 1")
    args = parser.parse_args(argv)

    pins, skipped = parse_requirements(args.requirements)
    results = check(pins)

    if args.missing:
        missing = [r["name"] for r in results if r["status"] == "missing"]
        if missing:
            print("缺少依赖：" + "、".join(missing))
            return 1
        return 0

    if not pins:
        print("未从 %s 解析到任何 `<包>==<版本>` 锁定行。" % args.requirements)
        return 1

    width = max(len(r["name"]) for r in results)
    bad = 0
    for r in results:
        if r["status"] == "ok":
            print("  %-*s  OK         %s" % (width, r["name"], r["expected"]))
        elif r["status"] == "missing":
            bad += 1
            print("  %-*s  缺失       期望 %s" % (width, r["name"], r["expected"]))
        else:
            bad += 1
            print("  %-*s  版本不符   期望 %s，实装 %s"
                  % (width, r["name"], r["expected"], r["installed"]))

    if skipped:
        print()
        print("注意：以下行不是精确版本锁定（`==`），未纳入核查：")
        for s in skipped:
            print("  " + s)

    print()
    if bad:
        print("有 %d 项不满足。修复：pip install -r requirements.txt" % bad)
        return 1
    print("依赖全部满足（%d 项）。" % len(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
