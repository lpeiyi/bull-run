# -*- coding: utf-8 -*-
"""缓存体检与清理回归测试（AC-2.x / AC-3.x / AC-4.x）。

全部使用 tmp_path 构造的临时目录与清单桩，**不触碰真实 data/**。
需求见 specs/fix-stocklist-and-cache-health/。
"""
import json
import os
import sys
from datetime import date, datetime

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_ROOT, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "scripts"))

import cache_health as ch  # noqa: E402


# ── 构造助手 ──────────────────────────────────────────

def _write_kline(klines_dir, name, dates):
    """写一个最小可读的 K 线缓存文件，返回其路径。"""
    path = os.path.join(klines_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write("date,open,high,low,close,volume\n")
        for d in dates:
            f.write("%s,10.0,11.0,9.0,10.5,1000\n" % d)
    return path


def _mk_klines(klines_dir, names, d="2026-08-28"):
    return [_write_kline(klines_dir, n, [d]) for n in names]


def _mtime_snapshot(klines_dir):
    out = {}
    for n in sorted(os.listdir(klines_dir)):
        p = os.path.join(klines_dir, n)
        out[n] = os.stat(p).st_mtime_ns
    return out


@pytest.fixture
def kdir(tmp_path):
    d = tmp_path / "klines"
    d.mkdir()
    return str(d)


@pytest.fixture
def stub_manifest(monkeypatch):
    """把清单读取替换为内存桩。"""
    def _install(stocks, degraded=False, reason=""):
        meta = {"degraded": degraded, "count": len(stocks),
                "fetched_at": 0.0, "reason": reason}
        monkeypatch.setattr(ch, "load_manifest", lambda force=False: (stocks, meta))
        return meta
    return _install


# ── 文件名解析 ────────────────────────────────────────

def test_parse_kline_filename_ok():
    assert ch.parse_kline_filename("sh600000_qfq.csv") == ("sh600000", "qfq")
    assert ch.parse_kline_filename("bj920000_hfq.csv") == ("bj920000", "hfq")


def test_parse_kline_filename_invalid():
    assert ch.parse_kline_filename("readme.txt") is None
    assert ch.parse_kline_filename("noadjust.csv") is None
    assert ch.parse_kline_filename("_qfq.csv") is None


# ── AC-2.1 / AC-2.2 体检只读且统计正确 ────────────────

def test_report_is_read_only(kdir):
    _mk_klines(kdir, ["sh600000_qfq.csv", "sz000001_qfq.csv"])
    before = _mtime_snapshot(kdir)

    ch.build_report(kdir, [{"code": "sh600000"}], active_adjusts={"qfq"})

    assert _mtime_snapshot(kdir) == before     # 文件集合与 mtime 均未变


def test_report_stats_are_correct(kdir):
    _write_kline(kdir, "sh600000_qfq.csv", ["2026-08-26", "2026-08-27", "2026-08-28"])
    _write_kline(kdir, "sz000001_qfq.csv", ["2026-08-28"])

    rep = ch.build_report(kdir, [{"code": "sh600000"}, {"code": "sz000001"}],
                          active_adjusts={"qfq"})

    assert rep["file_count"] == 2
    assert rep["rows"]["min"] == 1
    assert rep["rows"]["max"] == 3
    assert rep["rows"]["below_250"] == 2       # 两个文件行数均远不足 250
    assert rep["freshness"]["latest_date"] == "2026-08-28"
    assert rep["list"]["intersect"] == 2
    assert rep["list"]["cache_only"] == []
    assert rep["orphan_adjust"]["count"] == 0


def test_report_size_is_logical_not_disk(kdir):
    """逻辑体积应为各文件 st_size 之和（不受 NTFS 簇对齐影响）。"""
    _mk_klines(kdir, ["sh600000_qfq.csv", "sz000001_qfq.csv"])
    expected = sum(os.path.getsize(os.path.join(kdir, n))
                   for n in os.listdir(kdir))

    rep = ch.build_report(kdir, [], active_adjusts={"qfq"})

    assert rep["total_bytes"] == expected


# ── AC-2.3 过期判定 ───────────────────────────────────

def test_report_overdue_detection(kdir):
    _write_kline(kdir, "sh600000_qfq.csv", ["2026-08-28"])

    # 今天是 2026-08-31（周一）→ 逾期 1 个工作日
    rep = ch.build_report(kdir, [], active_adjusts={"qfq"}, today=date(2026, 8, 31))
    assert rep["freshness"]["latest_date"] == "2026-08-28"
    assert rep["freshness"]["overdue_trade_days"] == 1


def test_report_not_overdue_when_current(kdir):
    _write_kline(kdir, "sh600000_qfq.csv", ["2026-08-28"])

    rep = ch.build_report(kdir, [], active_adjusts={"qfq"}, today=date(2026, 8, 28))
    assert rep["freshness"]["overdue_trade_days"] == 0


# ── AC-2.1 与清单差集 ─────────────────────────────────

def test_report_manifest_diff(kdir):
    _mk_klines(kdir, ["sh600000_qfq.csv", "sz000001_qfq.csv", "bj920000_qfq.csv"])

    rep = ch.build_report(kdir, [{"code": "sh600000"}, {"code": "sh600001"}],
                          active_adjusts={"qfq"})

    assert rep["list"]["count"] == 2
    assert rep["list"]["cache_count"] == 3
    assert rep["list"]["intersect"] == 1
    assert rep["list"]["cache_only"] == ["bj920000", "sz000001"]
    assert rep["list"]["list_only_count"] == 1


# ── AC-4.1 复权孤儿识别 ───────────────────────────────

def test_report_detects_orphan_adjust(kdir):
    _mk_klines(kdir, ["sh600000_qfq.csv", "sh600000_hfq.csv"])

    rep = ch.build_report(kdir, [{"code": "sh600000"}], active_adjusts={"qfq"})

    assert rep["orphan_adjust"]["count"] == 1
    assert rep["orphan_adjust"]["codes"] == ["sh600000"]
    assert "qfq" in rep["orphan_adjust"]["active_adjusts"]


def test_load_active_adjusts_reads_indicators(tmp_path):
    f = tmp_path / "indicators.json"
    f.write_text(json.dumps([
        {"config": {"adjust": "qfq"}},
        {"config": {"adjust": "hfq"}},
        {"config": {}},
    ], ensure_ascii=False), encoding="utf-8")

    active = ch.load_active_adjusts(str(f))

    assert active == {"qfq", "hfq"}     # 默认 qfq 始终并入


# ── AC-3.1 / AC-3.2 计划与删除 ────────────────────────

def test_plan_clean_targets_only_manifest_missing(kdir):
    _mk_klines(kdir, ["sh600000_qfq.csv", "sz000001_qfq.csv", "bj920000_qfq.csv"])

    plan = ch.plan_clean(kdir, {"sh600000", "sz000001"}, active_adjusts={"qfq"})

    assert [x["name"] for x in plan["deletable"]] == ["bj920000_qfq.csv"]
    assert plan["stale_count"] == 1
    assert plan["bytes"] > 0


def test_plan_clean_is_non_destructive(kdir):
    _mk_klines(kdir, ["bj920000_qfq.csv"])

    ch.plan_clean(kdir, set(), active_adjusts={"qfq"})

    assert os.listdir(kdir) == ["bj920000_qfq.csv"]


# ── AC-4.2 复权孤儿默认不删 / 显式才删 ────────────────

def test_orphan_not_deleted_by_default(kdir):
    """标的仍在清单中，仅复权方式不同 → 默认不删。"""
    _mk_klines(kdir, ["sh600000_hfq.csv"])

    plan = ch.plan_clean(kdir, {"sh600000"}, active_adjusts={"qfq"}, orphan_adjust=False)

    assert plan["deletable"] == []


def test_orphan_deleted_with_flag(kdir):
    _mk_klines(kdir, ["sh600000_hfq.csv"])
    before = _mtime_snapshot(kdir)

    plan = ch.plan_clean(kdir, {"sh600000"}, active_adjusts={"qfq"}, orphan_adjust=True)

    assert [x["name"] for x in plan["deletable"]] == ["sh600000_hfq.csv"]
    assert plan["orphan_count"] == 1
    assert _mtime_snapshot(kdir) == before      # 仅计划，不动文件


# ── AC-3.4 删除失败逐条报告不中断 ─────────────────────

def test_apply_clean_reports_failure_and_continues(kdir, monkeypatch):
    _mk_klines(kdir, ["a_qfq.csv", "b_qfq.csv", "c_qfq.csv"])
    plan = ch.plan_clean(kdir, set(), active_adjusts={"qfq"}, orphan_adjust=True)
    assert len(plan["deletable"]) == 3

    real_remove = os.remove

    def _flaky(path):
        if os.path.basename(path).startswith("b_"):
            raise OSError("模拟占用")
        return real_remove(path)

    monkeypatch.setattr(ch.os, "remove", _flaky)
    deleted, failed = ch.apply_clean(plan["deletable"])

    assert len(deleted) == 2
    assert len(failed) == 1
    assert "b_qfq.csv" in failed[0]["path"]
    assert sorted(os.listdir(kdir)) == ["b_qfq.csv"]


# ── AC-3.1 / AC-3.3 命令行：dry-run 默认 ──────────────

def test_main_clean_dry_run_keeps_files(kdir, stub_manifest, capsys):
    _mk_klines(kdir, ["sh600000_qfq.csv", "bj920000_qfq.csv"])
    stub_manifest([{"code": "sh600000"}])

    rc = ch.main(["clean", "--klines-dir", kdir])

    assert rc == 0
    assert sorted(os.listdir(kdir)) == ["bj920000_qfq.csv", "sh600000_qfq.csv"]
    out = capsys.readouterr().out
    assert "预演" in out and "未删除任何文件" in out


def test_main_clean_apply_deletes(kdir, stub_manifest, monkeypatch, capsys):
    _mk_klines(kdir, ["sh600000_qfq.csv", "bj920000_qfq.csv"])
    stub_manifest([{"code": "sh600000"}])
    monkeypatch.setattr(ch, "load_active_adjusts", lambda *a, **k: {"qfq"})

    rc = ch.main(["clean", "--apply", "--klines-dir", kdir])

    assert rc == 0
    assert os.listdir(kdir) == ["sh600000_qfq.csv"]
    assert "已删除" in capsys.readouterr().out


# ── AC-3.5 降级拒绝清理 ───────────────────────────────

def test_main_clean_refuses_when_degraded(kdir, stub_manifest, capsys):
    _mk_klines(kdir, ["bj920000_qfq.csv"])
    stub_manifest([{"code": "sh600000"}], degraded=True, reason="拉取失败，已回退旧缓存")

    rc = ch.main(["clean", "--apply", "--klines-dir", kdir])

    assert rc == 2                                  # 拒绝执行
    assert os.listdir(kdir) == ["bj920000_qfq.csv"]  # 一个都没删
    assert "拒绝清理" in capsys.readouterr().out


# ── 报告渲染 ──────────────────────────────────────────

def test_format_report_renders_key_fields(kdir):
    _mk_klines(kdir, ["sh600000_qfq.csv"])
    rep = ch.build_report(kdir, [{"code": "sh600000"}], active_adjusts={"qfq"})

    text = ch.format_report(rep, meta={"degraded": False, "count": 1, "reason": ""})

    for kw in ("K线缓存体检", "文件数", "行数分布", "数据新鲜度", "与清单比对", "复权孤儿"):
        assert kw in text


# ── 工具函数 ──────────────────────────────────────────

@pytest.mark.parametrize("d1,d2,expected", [
    ("2026-08-28", "2026-08-28", 0),   # 同一天 → 0
    ("2026-08-28", "2026-08-29", 0),   # 周六
    ("2026-08-28", "2026-08-31", 1),   # 周一
    ("2026-08-28", "2026-09-04", 5),   # 跨一周
    ("2026-08-31", "2026-08-28", 0),   # 逆序 → 0
])
def test_weekdays_between(d1, d2, expected):
    a = datetime.strptime(d1, "%Y-%m-%d").date()
    b = datetime.strptime(d2, "%Y-%m-%d").date()
    assert ch.weekdays_between(a, b) == expected


@pytest.mark.parametrize("n,expected", [
    (0, "0 B"), (999, "999 B"), (1024, "1.0 KB"), (1536, "1.5 KB"),
])
def test_human_size(n, expected):
    assert ch._human_size(n) == expected
