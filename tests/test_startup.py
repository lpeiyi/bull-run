# -*- coding: utf-8 -*-
"""启动链路回归测试（ROADMAP 第 4 项）。

守的是 start.bat 在 Windows cmd（默认 GBK 代码页）下能被正确解析。
"""
import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_START_BAT = os.path.join(_ROOT, "start.bat")


def _read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def test_start_bat_is_pure_ascii():
    """start.bat 必须是纯 ASCII。

    cmd 默认按 GBK 代码页解析批处理。一旦写入中文注释（UTF-8 字节会被解成乱码），
    cmd 会把乱码当命令执行，表现为「系统找不到指定的路径」并导致启动失败。
    """
    data = _read_bytes(_START_BAT)
    bad = [i for i, b in enumerate(data) if b > 0x7F]

    assert not bad, ("start.bat 含非 ASCII 字节 %d 处（首个偏移 %d）。"
                     "注释请用英文——cmd 会按 GBK 解析。" % (len(bad), bad[0]))


def test_start_bat_has_no_bom():
    """UTF-8 BOM 会让 cmd 把首行 `@echo off` 解读失败。"""
    assert not _read_bytes(_START_BAT).startswith(b"\xef\xbb\xbf")


def test_start_bat_referenced_files_exist():
    """bat 里引用的脚本与依赖文件必须真实存在，否则启动即失败。"""
    text = _read_bytes(_START_BAT).decode("ascii")

    for rel in re.findall(r"scripts\\?([A-Za-z0-9_]+\.py)", text):
        assert os.path.exists(os.path.join(_ROOT, "scripts", rel)), \
            "start.bat 引用了不存在的脚本：scripts\\%s" % rel
    for rel in re.findall(r"-r\s+([A-Za-z0-9_.]+\.txt)", text):
        assert os.path.exists(os.path.join(_ROOT, rel)), \
            "start.bat 引用了不存在的依赖文件：%s" % rel


def test_start_bat_checks_before_installing():
    """必须先探依赖、缺了才装。

    依赖已精确锁定，若退回「每次启动都 pip install」，本机版本与锁定值一旦有偏差，
    每次启动都会尝试联网改版本，断网时直接 exit 1 起不来。
    """
    text = _read_bytes(_START_BAT).decode("ascii")

    assert "check_deps.py --missing" in text, "启动脚本应先探测依赖是否齐备"
    assert "if not errorlevel 1 goto :start" in text, \
        "依赖齐备时应直接启动，不进入安装分支"
