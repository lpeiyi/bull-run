# -*- coding: utf-8 -*-
"""K 线缓存体检与清理工具。

用法（在项目根目录执行）：
  python scripts/cache_health.py report                            # 体检（只读，默认）
  python scripts/cache_health.py clean                             # 清理预演（dry-run，默认）
  python scripts/cache_health.py clean --apply                     # 真正执行删除
  python scripts/cache_health.py clean --apply --orphan-adjust     # 连带删除复权孤儿

设计见 specs/fix-stocklist-and-cache-health/：
- 删除粒度为「整文件」，不做内容裁剪 → 不会造成回测 250 日失真（AC-3.3）。
- 默认 dry-run，必须显式 --apply 才动手（AC-3.1）。
- 以「当前有效清单」为基准，仅删除清单中已不存在的标的缓存（AC-3.2）。
- 清单处于降级状态时拒绝清理，防止以残缺清单为基准误删有效缓存（AC-3.5）。
- 复权孤儿默认只检测不删，需 --orphan-adjust 显式开启（AC-4.1/4.2）。
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta

# 脚本位于 scripts/ 下：取上一级（项目根）入 sys.path，保证 `python scripts/cache_health.py` 能 import core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_KLINE_DIR = os.path.join(_BASE, "data", "screener", "klines")
_INDICATORS_FILE = os.path.join(_BASE, "indicators.json")
_DEFAULT_ADJUST = "qfq"
_BACKTEST_DAYS = 250        # 回测默认取 250 日，行数分布以此作参考阈值
_DATE_COL = "date"


# ── 基础工具 ──────────────────────────────────────────

def parse_kline_filename(fname):
    """从 `{code}_{adjust}.csv` 解析 (code, adjust)；不匹配返回 None。"""
    if not fname.endswith(".csv"):
        return None
    stem = fname[:-4]
    code, sep, adjust = stem.rpartition("_")
    if not sep or not code or not adjust:
        return None
    return code, adjust


def read_kline_summary(path):
    """读取单个缓存文件，返回 (行数, 最大日期字符串)。

    读取失败或结构异常时返回 (0, "")。只读，不修改文件。
    """
    rows = 0
    max_date = ""
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                return 0, ""
            try:
                di = header.index(_DATE_COL)
            except ValueError:
                return 0, ""
            for rec in reader:
                if len(rec) <= di:
                    continue
                rows += 1
                d = rec[di][:10]
                if d > max_date:
                    max_date = d
    except OSError:
        return 0, ""
    return rows, max_date


def collect_kline_files(klines_dir):
    """枚举 klines 目录下的缓存文件。

    返回 [{name, path, code, adjust, size, mtime}]，按文件名排序。
    仅收录符合 `{code}_{adjust}.csv` 命名的文件。
    """
    out = []
    if not os.path.isdir(klines_dir):
        return out
    for fname in sorted(os.listdir(klines_dir)):
        path = os.path.join(klines_dir, fname)
        if not os.path.isfile(path):
            continue
        parsed = parse_kline_filename(fname)
        if parsed is None:
            continue
        code, adjust = parsed
        try:
            st = os.stat(path)
        except OSError:
            continue
        out.append({
            "name": fname,
            "path": path,
            "code": code,
            "adjust": adjust,
            "size": st.st_size,
            "mtime": st.st_mtime,
        })
    return out


def load_active_adjusts(indicators_file=None):
    """当前配置在用的复权方式集合。

    取自 indicators.json 中各策略的 config.adjust，并始终并入默认值 qfq。
    """
    active = {_DEFAULT_ADJUST}
    path = indicators_file or _INDICATORS_FILE
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return active
    items = data if isinstance(data, list) else []
    for it in items:
        cfg = (it or {}).get("config") or {}
        adj = cfg.get("adjust")
        if adj:
            active.add(str(adj))
    return active


def load_manifest(force=False):
    """读取全市场清单（含降级标记）。独立成函数，便于测试替身。

    返回 (stocks, meta)，语义同 core.screener.load_stock_list_meta。
    """
    from core.screener import load_stock_list_meta
    return load_stock_list_meta(force=force)


def weekdays_between(d1, d2):
    """d1 与 d2 之间的工作日数（不含 d1、含 d2）；d2 <= d1 时返回 0。

    近似「逾期交易日数」：不含法定节假日，仅排除周末。
    """
    if d2 <= d1:
        return 0
    n = 0
    cur = d1 + timedelta(days=1)
    while cur <= d2:
        if cur.weekday() < 5:
            n += 1
        cur += timedelta(days=1)
    return n


def _human_size(n):
    """字节数 → 人类可读。"""
    if n < 1024:
        return "%d B" % n
    n = float(n)
    for unit in ("KB", "MB", "GB"):
        n /= 1024.0
        if n < 1024 or unit == "GB":
            return "%.1f %s" % (n, unit)
    return "%.1f GB" % n


# ── 体检（只读） ──────────────────────────────────────

def build_report(klines_dir, stocks, active_adjusts=None, today=None):
    """构造体检报告 dict。纯读取，不修改任何文件（AC-2.2）。"""
    active = set(active_adjusts) if active_adjusts else load_active_adjusts()
    today = today or datetime.now().date()
    files = collect_kline_files(klines_dir)

    total_bytes = sum(f["size"] for f in files)

    # 行数统计 + 数据新鲜度 + mtime 分布
    rows_list = []
    mtime_dist = {}
    latest_date = ""
    below_250 = 0
    for f in files:
        rows, max_date = read_kline_summary(f["path"])
        f["rows"] = rows
        f["max_date"] = max_date
        rows_list.append(rows)
        if rows < _BACKTEST_DAYS:
            below_250 += 1
        d = datetime.fromtimestamp(f["mtime"]).strftime("%Y-%m-%d")
        mtime_dist[d] = mtime_dist.get(d, 0) + 1
        if max_date > latest_date:
            latest_date = max_date

    rows_sorted = sorted(rows_list)
    if rows_sorted:
        n = len(rows_sorted)
        mid = n // 2
        median = (rows_sorted[mid] if n % 2 else
                  (rows_sorted[mid - 1] + rows_sorted[mid]) / 2.0)
        rows_stat = {"min": rows_sorted[0], "median": median, "max": rows_sorted[-1]}
    else:
        rows_stat = {"min": 0, "median": 0, "max": 0}

    # 与清单比对
    list_codes = {s.get("code") for s in (stocks or []) if s.get("code")}
    cache_codes = {f["code"] for f in files}
    cache_only = sorted(cache_codes - list_codes)
    list_only = sorted(list_codes - cache_codes)

    # 复权孤儿
    orphans = sorted({f["code"] for f in files if f["adjust"] not in active})

    overdue = 0
    if latest_date:
        try:
            overdue = weekdays_between(datetime.strptime(latest_date, "%Y-%m-%d").date(), today)
        except ValueError:
            overdue = 0

    return {
        "klines_dir": klines_dir,
        "file_count": len(files),
        "total_bytes": total_bytes,
        "avg_bytes": int(total_bytes / len(files)) if files else 0,
        "rows": dict(rows_stat, below_250=below_250),
        "mtime": dict(sorted(mtime_dist.items())),
        "freshness": {"latest_date": latest_date, "overdue_trade_days": overdue},
        "list": {
            "count": len(list_codes),
            "cache_count": len(cache_codes),
            "intersect": len(cache_codes & list_codes),
            "cache_only": cache_only,
            "list_only_count": len(list_only),
        },
        "orphan_adjust": {
            "active_adjusts": sorted(active),
            "count": len(orphans),
            "codes": orphans,
        },
    }


def format_report(rep, meta=None):
    """把体检报告格式化为可读文本。"""
    L = []
    L.append("=== K线缓存体检 ===")
    L.append("缓存目录      %s" % rep["klines_dir"])
    if meta is not None:
        state = "降级（可能不完整）" if meta.get("degraded") else "正常"
        L.append("清单状态      %s  %d 条%s" % (
            state, meta.get("count", 0),
            ("　原因：" + meta["reason"]) if meta.get("reason") else ""))
    L.append("文件数        %s" % format(rep["file_count"], ","))
    L.append("逻辑体积      %s   （均 %s）" % (
        _human_size(rep["total_bytes"]), _human_size(rep["avg_bytes"])))
    r = rep["rows"]
    L.append("行数分布      最少 %d / 中位 %s / 最大 %d；< %d 行的 %d 个" % (
        r["min"], r["median"], r["max"], _BACKTEST_DAYS, r["below_250"]))
    mtime_txt = "、".join("%s: %s" % (k, format(v, ",")) for k, v in rep["mtime"].items())
    L.append("mtime 分布    %s" % (mtime_txt or "（无）"))
    fr = rep["freshness"]
    if fr["latest_date"]:
        tag = "已过期" if fr["overdue_trade_days"] > 0 else "最新"
        L.append("数据新鲜度    最新交易日 %s（%s，逾期 %d 个交易日）" % (
            fr["latest_date"], tag, fr["overdue_trade_days"]))
    else:
        L.append("数据新鲜度    无有效 K 线数据")
    li = rep["list"]
    L.append("与清单比对    清单 %s / 缓存 %s / 交集 %s" % (
        format(li["count"], ","), format(li["cache_count"], ","), format(li["intersect"], ",")))
    L.append("              仅缓存有（疑似废弃）  %s" % format(len(li["cache_only"]), ","))
    L.append("              仅清单有（未缓存）    %s" % format(li["list_only_count"], ","))
    oa = rep["orphan_adjust"]
    if oa["count"]:
        L.append("复权孤儿      %s 个（在用复权：%s）" % (
            format(oa["count"], ","), "/".join(oa["active_adjusts"])))
    else:
        L.append("复权孤儿      无（在用复权：%s）" % "/".join(oa["active_adjusts"]))
    return "\n".join(L)


# ── 清理 ──────────────────────────────────────────────

def plan_clean(klines_dir, stock_codes, active_adjusts=None, orphan_adjust=False):
    """构造清理计划（不执行删除）。

    待删集合：
      - 文件名 code 不在 stock_codes 中（疑似废弃标的）
      - orphan_adjust=True 时，追加 adjust 不属于在用复权方式的「复权孤儿」

    返回 {"deletable": [...], "bytes": int, "stale_count": int, "orphan_count": int}
    """
    active = set(active_adjusts) if active_adjusts else load_active_adjusts()
    codes = set(stock_codes or [])
    files = collect_kline_files(klines_dir)

    deletable = []
    stale_count = 0
    orphan_count = 0
    for f in files:
        stale = f["code"] not in codes
        orphan = f["adjust"] not in active
        if not stale and not (orphan_adjust and orphan):
            continue
        if stale:
            stale_count += 1
        elif orphan:
            orphan_count += 1
        deletable.append(dict(f, reason="清单外标的" if stale else "复权孤儿"))

    return {
        "deletable": deletable,
        "bytes": sum(f["size"] for f in deletable),
        "stale_count": stale_count,
        "orphan_count": orphan_count,
    }


def apply_clean(items):
    """逐个删除文件；失败逐条记录且不中断其余删除（AC-3.4）。

    返回 (deleted, failed)：deleted 为成功删除的条目列表，failed 为 [{path, error}]。
    """
    deleted, failed = [], []
    for it in items:
        try:
            os.remove(it["path"])
            deleted.append(it)
        except OSError as e:
            failed.append({"path": it["path"], "error": str(e)})
    return deleted, failed


# ── 命令行 ────────────────────────────────────────────

def cmd_report(args):
    stocks, meta = load_manifest(force=args.force)
    rep = build_report(args.klines_dir, stocks, active_adjusts=load_active_adjusts())
    print(format_report(rep, meta))
    return 0


def cmd_clean(args):
    stocks, meta = load_manifest(force=args.force)
    if meta.get("degraded"):
        print("拒绝清理：当前清单处于降级状态（%d 条，%s）。" % (
            meta.get("count", 0), meta.get("reason", "")))
        print("请先获取完整清单（例如访问 /api/screen/stock_list?force=1）后重试。")
        return 2

    codes = {s.get("code") for s in stocks if s.get("code")}
    plan = plan_clean(args.klines_dir, codes,
                      active_adjusts=load_active_adjusts(),
                      orphan_adjust=args.orphan_adjust)

    print("=== K线缓存清理%s ===" % ("（预演，不删除）" if not args.apply else ""))
    print("清单标的 %s 个 / 待删 %s 个（清单外 %s + 复权孤儿 %s）/ 预计释放 %s" % (
        format(len(codes), ","), format(len(plan["deletable"]), ","),
        format(plan["stale_count"], ","), format(plan["orphan_count"], ","),
        _human_size(plan["bytes"])))

    if not plan["deletable"]:
        print("无需清理。")
        return 0

    for it in plan["deletable"][:50]:
        print("  - [%s] %s  (%s)" % (it["reason"], it["name"], _human_size(it["size"])))
    if len(plan["deletable"]) > 50:
        print("  ... 其余 %d 个略" % (len(plan["deletable"]) - 50))

    if not args.apply:
        print("\n以上为预演结果，未删除任何文件。加 --apply 才会真正删除。")
        return 0

    deleted, failed = apply_clean(plan["deletable"])
    freed = sum(it["size"] for it in deleted)
    print("\n已删除 %d 个文件，释放 %s。" % (len(deleted), _human_size(freed)))
    if failed:
        print("删除失败 %d 个：" % len(failed))
        for f in failed:
            print("  ! %s —— %s" % (f["path"], f["error"]))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="K 线缓存体检与清理（默认只读 / dry-run）")
    parser.add_argument("command", choices=["report", "clean"], nargs="?",
                        default="report", help="report=体检（默认）；clean=清理")
    parser.add_argument("--apply", action="store_true",
                        help="clean 时真正执行删除（默认仅预演）")
    parser.add_argument("--orphan-adjust", action="store_true",
                        help="clean 时连带删除复权孤儿缓存")
    parser.add_argument("--force", action="store_true",
                        help="强制重新拉取全市场清单")
    parser.add_argument("--klines-dir", default=_DEFAULT_KLINE_DIR,
                        help="K 线缓存目录（默认 data/screener/klines）")
    args = parser.parse_args(argv)

    if args.command == "clean":
        return cmd_clean(args)
    return cmd_report(args)


if __name__ == "__main__":
    sys.exit(main())
