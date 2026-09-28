# -*- coding: utf-8 -*-
"""历史重写校验器：证明「重写只改了 message，其余一律没动」。

用途（见 specs/clean-history-messages/design.md §6）：

    # 重写前：把当前 HEAD 的逐条档案落成基线（存到仓库外的备份目录）
    python scripts/verify_history_rewrite.py --dump <备份>/baseline.json

    # 重写后：与基线逐条比对，并按映射表判定每条消息是否为预期成品
    python scripts/verify_history_rewrite.py --verify <备份>/baseline.json \\
        --map specs/clean-history-messages/message_map.json

判定逐条进行（不是只比 HEAD）：条数、tree、作者/提交者及其时间戳必须完全一致；
消息则必须等于「映射表里的成品」或「基线里的原文」。退出码 0 = 全部通过，1 = 有违规。

设计为纯标准库、离线可跑；比对逻辑与 git 解耦，便于单测。
"""
import argparse
import base64
import io
import json
import re
import subprocess
import sys

# commit 对象头形如：author Name <mail> 1785549600 +0800
_IDENT_RE = re.compile(r"^([^<]*?)\s*<([^>]*)>\s*(\d+)\s*[+-]\d{4}$")

# 改写后消息中「原始文件清单」段的标题——AC-1.3 要求清单原文保留在此段之下
MSG_LIST_MARKER = "原始文件清单（git status 原文）："


# ── 纯函数（可单测，不依赖 git） ───────────────────────────

def parse_identity(value):
    """'Name <mail> 1785549600 +0800' -> {'name', 'email', 'ts'}；解析不了返回 None。"""
    m = _IDENT_RE.match(value or "")
    if not m:
        return None
    return {"name": m.group(1), "email": m.group(2), "ts": m.group(3)}


def parse_commit_object(raw):
    """解析 `git cat-file commit` 的原始字节。

    返回 {'tree', 'parents', 'author', 'committer', 'message'}；
    message 为**原始字节**（不含头部分隔空行）。
    """
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    head, _, message = raw.partition(b"\n\n")
    tree = None
    parents = []
    author = committer = None
    for line in head.decode("utf-8", "replace").splitlines():
        if line.startswith("tree "):
            tree = line[5:].strip()
        elif line.startswith("parent "):
            parents.append(line[7:].strip())
        elif line.startswith("author "):
            author = parse_identity(line[7:])
        elif line.startswith("committer "):
            committer = parse_identity(line[10:])
    return {"tree": tree, "parents": parents,
            "author": author, "committer": committer, "message": message}


def message_to_str(message):
    """消息字节 -> 便于 JSON 与人读的字符串（非 UTF-8 时以 replace 兜底）。"""
    if isinstance(message, str):
        return message
    return message.decode("utf-8", "replace")


def expected_message(record, mapping):
    """该提交重写后应有的消息（bytes）。在映射中取成品，否则取基线原文。"""
    if record["sha"] in mapping:
        return mapping[record["sha"]]
    return record["message"]


def _first_diff(actual, expect):
    """给出一句可读的差异提示（首个不同的行号与内容）。"""
    a = actual.decode("utf-8", "replace").splitlines()
    e = expect.decode("utf-8", "replace").splitlines()
    for i in range(max(len(a), len(e))):
        av = a[i] if i < len(a) else "<无此行>"
        ev = e[i] if i < len(e) else "<无此行>"
        if av != ev:
            return "第 %d 行 实际=%r 期望=%r" % (i + 1, av, ev)
    if actual != expect:
        return "字节不同但逐行相同（行尾/末尾换行差异）"
    return ""


def compare_records(old_records, new_records, mapping):
    """逐条比对，返回违规描述列表；空列表 = 全部通过。

    mapping: {旧 sha: 新消息 bytes}
    """
    problems = []
    if len(old_records) != len(new_records):
        problems.append("提交条数不同：重写前 %d 条，重写后 %d 条"
                        % (len(old_records), len(new_records)))
    for i, (o, n) in enumerate(zip(old_records, new_records), 1):
        tag = "序号%d (%s)" % (i, o["sha"][:8])
        if o["tree"] != n["tree"]:
            problems.append("%s tree 变化：%s -> %s（文件内容被改动了）"
                            % (tag, o["tree"][:8], n["tree"][:8]))
        if o["author"] != n["author"]:
            problems.append("%s 作者信息变化：%s -> %s"
                            % (tag, o["author"], n["author"]))
        if o["committer"] != n["committer"]:
            problems.append("%s 提交者/时间戳变化：%s -> %s"
                            % (tag, o["committer"], n["committer"]))
        expect = expected_message(o, mapping)
        if n["message"] != expect:
            problems.append("%s 消息不符预期：%s" % (tag, _first_diff(n["message"], expect)))
    return problems


def flag_bad_subjects(records, markers=None):
    """返回 subject 命中 git status 原文标记的提交（AC-1.4）。"""
    markers = markers or ("Changes to be committed:", "On branch ", "Untracked files:",
                          "Changes not staged", "nothing to commit", "Your branch is",
                          "no changes added to commit")
    bad = []
    for i, r in enumerate(records, 1):
        subject = message_to_str(r["message"]).splitlines()[0] if r["message"] else ""
        if any(subject.startswith(m) for m in markers):
            bad.append((i, r["sha"][:8], subject[:60]))
    return bad


# ── 与 git 交互的部分 ────────────────────────────────────

def _git(*args):
    proc = subprocess.run(["git", *args], capture_output=True)
    if proc.returncode != 0:
        raise SystemExit("git %s 失败：%s" % (" ".join(args),
                                             proc.stderr.decode("utf-8", "replace")))
    return proc.stdout


def list_shas(rev):
    """按「从最早算」的顺序列出 rev 可达的全部提交。"""
    out = _git("rev-list", "--reverse", rev)
    return [s.strip() for s in out.decode("utf-8").splitlines() if s.strip()]


def read_records(rev="HEAD"):
    """采集 rev 的逐条档案。message 以 base64 存 JSON，保证字节无损。"""
    records = []
    for i, sha in enumerate(list_shas(rev), 1):
        parsed = parse_commit_object(_git("cat-file", "commit", sha))
        records.append({
            "index": i,
            "sha": sha,
            "tree": parsed["tree"],
            "parents": parsed["parents"],
            "author": parsed["author"],
            "committer": parsed["committer"],
            "message_b64": base64.b64encode(parsed["message"]).decode("ascii"),
        })
    return records


def add_message_bytes(records):
    """给 JSON 形态的记录补上 message 字节（就地修改并返回）。

    比对用的记录必须有 message(bytes)；而落盘的记录不能带 bytes，故分两步。
    """
    for r in records:
        if "message" not in r:
            r["message"] = base64.b64decode(r["message_b64"])
    return records


def records_from_json(blob):
    """把基线 JSON 还原成比对用的记录（message 转回 bytes）。"""
    out = []
    for r in blob:
        out.append({
            "index": r.get("index"),
            "sha": r["sha"],
            "tree": r.get("tree"),
            "parents": r.get("parents") or [],
            "author": r.get("author"),
            "committer": r.get("committer"),
            "message": base64.b64decode(r["message_b64"]),
        })
    return out


def mapping_to_bytes(mapping):
    return {k: v.encode("utf-8") for k, v in mapping.items()}


# ── CLI ──────────────────────────────────────────────────

def main(argv):
    ap = argparse.ArgumentParser(description="历史重写校验器（只读，不改仓库）")
    ap.add_argument("--dump", metavar="PATH", help="把当前 HEAD 的逐条档案写入 PATH")
    ap.add_argument("--verify", metavar="BASELINE", help="与基线 JSON 逐条比对")
    ap.add_argument("--map", metavar="MAP_JSON", help="消息映射表（旧 sha -> 新消息）")
    ap.add_argument("--rev", default="HEAD", help="采集用的 rev（默认 HEAD）")
    args = ap.parse_args(argv)

    if bool(args.dump) == bool(args.verify):
        ap.error("必须且只能指定 --dump 或 --verify 之一")

    if args.dump:
        records = read_records(args.rev)
        with io.open(args.dump, "w", encoding="utf-8", newline="\n") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("已记录 %d 条提交 -> %s" % (len(records), args.dump))
        return 0

    with io.open(args.verify, encoding="utf-8") as f:
        old_records = records_from_json(json.load(f))
    mapping = {}
    if args.map:
        with io.open(args.map, encoding="utf-8") as f:
            mapping = mapping_to_bytes(json.load(f))
    new_records = add_message_bytes(read_records(args.rev))

    print("重写前 %d 条 / 重写后 %d 条 / 映射表 %d 条"
          % (len(old_records), len(new_records), len(mapping)))

    problems = compare_records(old_records, new_records, mapping)
    bad = flag_bad_subjects(new_records)

    hit = 0
    for o, n in zip(old_records, new_records):
        if n["message"] != o["message"]:
            hit += 1
            old_sub = message_to_str(o["message"]).splitlines()[0] if o["message"] else ""
            new_sub = message_to_str(n["message"]).splitlines()[0] if n["message"] else ""
            print("  改写 %s\n    旧: %s\n    新: %s" % (o["sha"][:8], old_sub[:70], new_sub[:70]))
    print("消息发生变化的提交：%d 条（映射表 %d 条）" % (hit, len(mapping)))

    if bad:
        print("\n仍有 git status 原文 subject（AC-1.4 不满足）：%d 条" % len(bad))
        for i, sha, sub in bad:
            print("  序号%d %s  %s" % (i, sha, sub))
        problems.append("仍有 %d 条 git status 原文 subject（AC-1.4）" % len(bad))
    else:
        print("subject 合规：未发现 git status 原文开头的提交（AC-1.4）")

    if problems:
        print("\n违规 %d 项：" % len(problems))
        for p in problems:
            print("  - " + p)
        return 1

    print("\n全部逐条比对通过：tree / 作者 / 提交者 / 时间戳一致，消息符合预期。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
