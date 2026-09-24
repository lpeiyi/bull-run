# -*- coding: utf-8 -*-
"""板块榜单验收脚本（对应 specs/fix-boards-source-selection 的 AC-5.3）。

判定口径（2026-09-24 修订）：
  ① get_boards()['industry'] 的 avg_pct 严格降序；
  ② 榜首与东财 m:90+t:2（fid=f3&po=1）源榜首一致（名称相同 + 涨幅差 ≤0.01）；
  ③ 榜单中无「去掉末尾罗马数字后同名」的重复项。

原口径「比对新浪源第一名」已废弃：新浪返回 49 个大类、东财返回 496 个细分
板块，名称体系不同（重合率仅 12.2%），二者不具可比性，该锚点本身不成立。

用法（需能访问外网）：
  python scripts/verify_boards.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402
from core.data import UA  # noqa: E402

_LEVEL_SUFFIX = ("Ⅲ", "Ⅱ", "Ⅰ")


def _em_top(fs_code):
    """直接请求东财，返回按 f3 降序的原始榜单（作为验收基准）。"""
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {"pn": 1, "pz": 100, "po": 1, "np": 1, "fid": "f3",
              "fields": "f12,f14,f3,f6", "fs": fs_code}
    r = requests.get(url, headers={"User-Agent": UA}, params=params, timeout=15)
    diff = (r.json().get("data") or {}).get("diff") or []
    return [{"name": it["f14"], "avg_pct": round(float(it["f3"]) / 100, 2)}
            for it in diff]


def _base(name):
    n = name or ""
    while n and n[-1] in _LEVEL_SUFFIX:
        n = n[:-1]
    return n


def main():
    print("=" * 64)
    print("[Step 1] 调用 core.market.get_boards()")
    try:
        import core.market as m
        boards = m.get_boards()
        ind = boards.get("industry") or []
        con = boards.get("concept") or []
        print(f"  industry 条数: {len(ind)}    concept 条数: {len(con)}")
        for i, x in enumerate(ind[:10]):
            print(f"    Top{i + 1:>2}: {x.get('name', ''):<18} "
                  f"{x.get('avg_pct', 0):>6.2f}%")
    except Exception as e:
        import traceback
        print(f"  get_boards() 异常: {type(e).__name__}: {e}")
        traceback.print_exc()
        ind = []

    print()
    print("=" * 64)
    print("[Step 2] 拉取东财原始源（fid=f3&po=1）作为基准")
    try:
        em = _em_top("m:90+t:2")
        if em:
            print(f"  东财源条数: {len(em)}")
            print(f"  东财第1名: {em[0]['name']} {em[0]['avg_pct']:.2f}%")
            print(f"  东财第2名: {em[1]['name']} {em[1]['avg_pct']:.2f}%"
                  if len(em) >= 2 else "")
        else:
            print("  东财源为空")
    except Exception as e:
        print(f"  东财拉取异常: {type(e).__name__}: {e}")
        em = []

    print()
    print("=" * 64)
    print("[Step 3] 判定")
    results = []

    # ① 严格降序
    if ind:
        pcts = [x.get("avg_pct", 0) for x in ind]
        desc = all(pcts[i] >= pcts[i + 1] for i in range(len(pcts) - 1))
        results.append(("① 榜单严格降序", desc, f"{len(pcts)} 条"))
    else:
        results.append(("① 榜单严格降序", False, "榜单为空"))

    # ② 榜首与东财源一致
    if ind and em:
        a, b = ind[0], em[0]
        diff = abs(a.get("avg_pct", 0) - b["avg_pct"])
        ok = (a.get("name") == b["name"]) and diff <= 0.01
        results.append(("② 榜首与东财源一致", ok,
                        f"榜单={a.get('name')} {a.get('avg_pct')}% vs "
                        f"东财={b['name']} {b['avg_pct']}% (差 {diff:.2f}pp)"))
    else:
        results.append(("② 榜首与东财源一致", False, "榜单或东财源为空"))

    # ③ 无同层级重复项
    bases = [_base(x.get("name", "")) for x in ind]
    dups = sorted({b for b in bases if b and bases.count(b) > 1})
    results.append(("③ 无同层级重复项", not dups,
                    f"重复基名: {'、'.join(dups) if dups else '无'}"))

    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  —— {detail}")

    print()
    if all(ok for _, ok, _ in results):
        print("  RESULT: PASS（榜单来源正确、排序正确、无重复）")
        return 0
    print("  RESULT: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
