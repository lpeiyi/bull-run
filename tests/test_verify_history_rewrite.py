# -*- coding: utf-8 -*-
"""历史重写校验器的回归测试（ROADMAP 第 7 项 / specs/clean-history-messages）。

校验器是这次历史重写唯一的硬保障，所以它自己必须「有牙齿」：
下面逐条断言它**确实能识别**出各类失配（tree 被改、作者被改、时间戳被改、
条数变化、未映射的消息被改、已映射的消息没写对）。

最后一个用例是「守门用例」：绑住 message_map.json 的形态，
防止映射表被改成不合规的消息——那样重写会直接写出坏的 commit message。
"""
import base64
import io
import json
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_ROOT, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "scripts"))

import verify_history_rewrite as vhr  # noqa: E402

_MAP_FILE = os.path.join(_ROOT, "specs", "clean-history-messages", "message_map.json")
_SUBJECT_RE = re.compile(
    r"^(feat|fix|refactor|docs|test|chore|style|perf|build|ci)(\([a-z0-9_.-]+\))?: .+")


def _ident(name="老陆", email="l@x.net", ts="1785549600"):
    return {"name": name, "email": email, "ts": ts}


def _rec(sha="a" * 40, tree="t" * 40, message=b"msg\n", author=None, committer=None):
    return {"index": 1, "sha": sha, "tree": tree,
            "author": author or _ident(), "committer": committer or _ident(),
            "message": message}


def _commit_blob(tree="1111111111111111111111111111111111111111",
                 parents=("2222222222222222222222222222222222222222",),
                 message=b"subject\n\nbody\n"):
    lines = ["tree " + tree]
    lines += ["parent " + p for p in parents]
    lines.append("author 老陆 <l@x.net> 1785549600 +0800")
    lines.append("committer 老陆 <l@x.net> 1785549601 +0800")
    return ("\n".join(lines) + "\n\n").encode("utf-8") + message


# ── 解析 ──────────────────────────────────────────────

def test_parse_identity_ok():
    assert vhr.parse_identity("老陆 <l@x.net> 1785549600 +0800") == {
        "name": "老陆", "email": "l@x.net", "ts": "1785549600"}


def test_parse_identity_with_spaces_in_name():
    got = vhr.parse_identity("Lu Peiyi <l@x.net> 1785549600 -0500")
    assert got["name"] == "Lu Peiyi" and got["ts"] == "1785549600"


def test_parse_identity_rejects_garbage():
    assert vhr.parse_identity("") is None
    assert vhr.parse_identity("老陆 l@x.net") is None
    assert vhr.parse_identity(None) is None


def test_parse_commit_object_fields():
    parsed = vhr.parse_commit_object(_commit_blob())
    assert parsed["tree"] == "1" * 40
    assert parsed["parents"] == ["2" * 40]
    assert parsed["author"] == _ident(ts="1785549600")
    assert parsed["committer"] == _ident(ts="1785549601")
    assert parsed["message"] == b"subject\n\nbody\n"


def test_parse_commit_object_keeps_message_bytes_verbatim():
    """无结尾换行 / 行尾空格的消息必须原样取出（AC-1.2 的字节比对依赖这一点）。"""
    for msg in (b"no trailing newline", "带空格   \n\n正文 \n".encode("utf-8")):
        assert vhr.parse_commit_object(_commit_blob(message=msg))["message"] == msg


def test_parse_commit_object_root_commit_has_no_parent():
    parsed = vhr.parse_commit_object(_commit_blob(parents=()))
    assert parsed["parents"] == []


# ── 逐条比对 ───────────────────────────────────────────

def test_compare_identical_passes():
    old = [_rec(sha="a" * 40), _rec(sha="b" * 40)]
    new = [_rec(sha="c" * 40), _rec(sha="d" * 40)]
    assert vhr.compare_records(old, new, {}) == []


def test_compare_detects_tree_change():
    problems = vhr.compare_records([_rec(tree="t" * 40)], [_rec(tree="u" * 40)], {})
    assert len(problems) == 1 and "tree" in problems[0]


def test_compare_detects_author_change():
    old = [_rec(author=_ident(name="老陆"))]
    new = [_rec(author=_ident(name="别人"))]
    problems = vhr.compare_records(old, new, {})
    assert len(problems) == 1 and "作者" in problems[0]


def test_compare_detects_committer_timestamp_change():
    old = [_rec(committer=_ident(ts="100"))]
    new = [_rec(committer=_ident(ts="200"))]
    problems = vhr.compare_records(old, new, {})
    assert len(problems) == 1 and "时间戳" in problems[0]


def test_compare_detects_count_mismatch():
    problems = vhr.compare_records([_rec()], [_rec(), _rec()], {})
    assert problems and "条数不同" in problems[0]


def test_compare_detects_unmapped_message_change():
    """不在映射表里的提交，消息被改动就必须报出来（这就是 AC-1.2 的守门）。"""
    old = [_rec(sha="a" * 40, message="feat(x): 原样\n".encode("utf-8"))]
    new = [_rec(sha="b" * 40, message="feat(x): 被顺手改了\n".encode("utf-8"))]
    problems = vhr.compare_records(old, new, {})
    assert len(problems) == 1 and "消息不符预期" in problems[0]


def test_compare_accepts_mapped_message():
    old = [_rec(sha="a" * 40, message=b"Changes to be committed:\n\tmodified:   app.py\n")]
    new = [_rec(sha="b" * 40, message="feat(kline): 新增\n".encode("utf-8"))]
    mapping = {"a" * 40: "feat(kline): 新增\n".encode("utf-8")}
    assert vhr.compare_records(old, new, mapping) == []


def test_compare_detects_mapped_message_mismatch():
    old = [_rec(sha="a" * 40, message=b"Changes to be committed:\n")]
    new = [_rec(sha="b" * 40, message="feat(kline): 写错了\n".encode("utf-8"))]
    mapping = {"a" * 40: "feat(kline): 期望的\n".encode("utf-8")}
    problems = vhr.compare_records(old, new, mapping)
    assert len(problems) == 1 and "期望" in problems[0]


def test_compare_reports_first_differing_line():
    old = [_rec(message=b"line1\nline2\n")]
    new = [_rec(message=b"line1\nCHANGED\n")]
    hint = vhr.compare_records(old, new, {})[0]
    assert "第 2 行" in hint and "CHANGED" in hint


# ── AC-1.4 的 subject 扫描 ──────────────────────────────

def test_flag_bad_subjects_detects_git_status_markers():
    recs = [{"sha": "a" * 40, "message": b"Changes to be committed:\n"},
            {"sha": "b" * 40, "message": b"On branch main\n"},
            {"sha": "c" * 40, "message": "feat(x): 正常\n".encode("utf-8")}]
    bad = vhr.flag_bad_subjects(recs)
    assert [b[1] for b in bad] == ["a" * 8, "b" * 8]


def test_flag_bad_subjects_clean_history_passes():
    recs = [{"sha": "a" * 40, "message": b"initial commit: bull-run\n"},
            {"sha": "b" * 40, "message": "feat(x): 正常\n".encode("utf-8")}]
    assert vhr.flag_bad_subjects(recs) == []


# ── 记录形态往返 ────────────────────────────────────────

def test_add_message_bytes_roundtrip():
    raw = "带中文的消息   \n\n正文 \n".encode("utf-8")
    recs = [{"sha": "a" * 40, "message_b64": base64.b64encode(raw).decode("ascii")}]
    assert vhr.add_message_bytes(recs)[0]["message"] == raw


# ── 守门用例：映射表形态 ─────────────────────────────────

def test_message_map_shape_is_valid():
    """映射表必须恰好 10 条，且每条都是「合规 subject + 概括 + 原始清单」。

    对应用户可感知的结果：`git log --oneline` 可读（AC-1.1），
    且原文件清单没丢（AC-1.3）。
    """
    assert os.path.exists(_MAP_FILE), "映射表缺失：" + _MAP_FILE
    with io.open(_MAP_FILE, encoding="utf-8") as f:
        mapping = json.load(f)

    assert len(mapping) == 10, "待改写提交应为 10 条，实际 %d" % len(mapping)

    for sha, message in mapping.items():
        assert re.fullmatch(r"[0-9a-f]{40}", sha), "键必须是 40 位 sha：" + sha
        lines = message.split("\n")
        assert _SUBJECT_RE.match(lines[0]), "subject 不合规：" + lines[0]
        assert vhr.MSG_LIST_MARKER in message, "缺少清单段标题：" + sha[:8]
        # 清单段：标题之后每行都以 \t 开头（git status 原文的缩进），且以换行结尾
        tail = message.split(vhr.MSG_LIST_MARKER, 1)[1].lstrip("\n")
        assert tail.endswith("\n"), "清单段未以换行结尾：" + sha[:8]
        for line in tail.rstrip("\n").split("\n"):
            assert line.startswith("\t"), "清单行未保留原缩进：%r" % line
