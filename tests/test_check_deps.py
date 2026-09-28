# -*- coding: utf-8 -*-
"""依赖核查脚本的回归测试（ROADMAP 第 4 项）。

最后一个用例是「守门用例」：requirements.txt 一旦有人改回 `>=`，
核查就会形同虚设——必须让它变红。
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_ROOT, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "scripts"))

import check_deps as cd  # noqa: E402


def _write(tmp_path, text, name="requirements.txt"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


# ── 解析 ──────────────────────────────────────────────

def test_parse_pins_only(tmp_path):
    p = _write(tmp_path, "\n".join([
        "# 注释",
        "",
        "requests==2.34.2",
        "flask == 3.1.3",
        "-r other.txt",
        "pandas==3.0.3  # 行尾注释",
        "numpy==2.4.6; python_version >= '3.9'",
    ]))
    pins, skipped = cd.parse_requirements(p)

    assert pins == [("requests", "2.34.2"), ("flask", "3.1.3"),
                    ("pandas", "3.0.3"), ("numpy", "2.4.6")]
    assert skipped == []


def test_parse_reports_non_pinned(tmp_path):
    """下限约束与裸包名不能被静默忽略，须进 skipped 供人察觉。"""
    p = _write(tmp_path, "requests>=2.28\nflask\n")

    pins, skipped = cd.parse_requirements(p)

    assert pins == []
    assert skipped == ["requests>=2.28", "flask"]


def test_parse_missing_file():
    pins, skipped = cd.parse_requirements("no_such_file.txt")
    assert pins == [] and skipped == []


# ── 版本比对 ──────────────────────────────────────────

def test_check_statuses(monkeypatch):
    versions = {"requests": "2.34.2", "flask": "2.2.0"}

    def fake_version(name):
        if name not in versions:
            raise cd.md.PackageNotFoundError(name)
        return versions[name]

    monkeypatch.setattr(cd.md, "version", fake_version)

    res = cd.check([("requests", "2.34.2"), ("flask", "3.1.3"), ("numpy", "2.4.6")])

    assert [r["status"] for r in res] == ["ok", "mismatch", "missing"]
    assert res[1]["installed"] == "2.2.0"
    assert res[2]["installed"] is None


# ── 命令行 ────────────────────────────────────────────

def test_main_all_ok(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cd.md, "version", lambda n: "1.0")
    p = _write(tmp_path, "requests==1.0\nflask==1.0\n")

    rc = cd.main(["--requirements", p])

    assert rc == 0
    assert "依赖全部满足" in capsys.readouterr().out


def test_main_reports_mismatch(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cd.md, "version", lambda n: "9.9")
    p = _write(tmp_path, "requests==1.0\n")

    rc = cd.main(["--requirements", p])

    assert rc == 1
    out = capsys.readouterr().out
    assert "版本不符" in out and "实装 9.9" in out


def test_main_missing_mode_detects_absent(tmp_path, monkeypatch, capsys):
    def fake_version(name):
        raise cd.md.PackageNotFoundError(name)

    monkeypatch.setattr(cd.md, "version", fake_version)
    p = _write(tmp_path, "requests==2.34.2\nflask==3.1.3\n")

    rc = cd.main(["--requirements", p, "--missing"])

    assert rc == 1
    assert "缺少依赖" in capsys.readouterr().out


def test_main_missing_mode_ignores_mismatch(tmp_path, monkeypatch, capsys):
    """--missing 只判"在不在"：版本不符不触发安装（避免断网时启动失败）。"""
    monkeypatch.setattr(cd.md, "version", lambda n: "0.0.1")
    p = _write(tmp_path, "requests==2.34.2\n")

    rc = cd.main(["--requirements", p, "--missing"])

    assert rc == 0
    assert capsys.readouterr().out == ""


def test_main_warns_on_non_pinned(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cd.md, "version", lambda n: "1.0")
    p = _write(tmp_path, "requests==1.0\nnumpy>=1.24\n")

    rc = cd.main(["--requirements", p])

    assert rc == 0
    assert "未纳入核查" in capsys.readouterr().out


def test_main_empty_pins_is_failure(tmp_path, capsys):
    p = _write(tmp_path, "requests>=2.28\n")

    assert cd.main(["--requirements", p]) == 1
    assert capsys.readouterr().out.startswith("未从")


# ── 守门用例 ──────────────────────────────────────────

def test_project_requirements_fully_pinned():
    """项目根的 requirements.txt 必须全部为精确锁定。

    一旦有人改回 `>=`，核查工具会静默放过版本漂移 —— 这个用例就是那道闸。
    改动 requirements.txt 后必须同步更新本用例的期望（见 scripts/check_deps.py）。
    """
    pins, skipped = cd.parse_requirements(cd._REQ_FILE)

    assert pins, "requirements.txt 应包含至少一条 `<包>==<版本>` 锁定"
    assert skipped == [], "requirements.txt 存在非精确锁定行：%s" % (skipped,)
