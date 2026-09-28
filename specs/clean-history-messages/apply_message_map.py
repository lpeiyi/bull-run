# -*- coding: utf-8 -*-
"""`git filter-branch --msg-filter` 的入口：按**原**提交 hash 改写提交消息。

- 命中 `message_map.json` → 输出映射中的新消息
- 未命中 → 把 stdin 收到的原始消息**字节原样透传**

第二条是 AC-1.2（其余提交消息逐字节不变）的实现。`--msg-filter` 会把
原始消息字节通过 stdin 传入，且导出 `GIT_COMMIT`（= 本次处理的原提交 sha），
两者均已由 `design.md` §2.2 的探针实测确认。

调用方式见 `design.md` §2.4。
"""
import io
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_MAP_FILE = os.path.join(_HERE, "message_map.json")


def load_map(path=_MAP_FILE):
    """读 {旧 sha: 新 message} 映射。"""
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    mapping = load_map()
    raw = sys.stdin.buffer.read()               # 原始消息字节
    sha = os.environ.get("GIT_COMMIT", "")
    new = mapping.get(sha)
    if new is None:
        sys.stdout.buffer.write(raw)            # 字节透传，不做任何规范化
    else:
        sys.stdout.buffer.write(new.encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
