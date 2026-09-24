# -*- coding: utf-8 -*-
"""AC-1.6 验证脚本：比较 get_boards() 返回的 industry[0] 与新浪原始源第一名"""
import sys, os, json, re, inspect
sys.path.insert(0, os.getcwd())

import requests
from core.data import UA

# 1) 直接调用新浪接口，拿到其第一名
def _parse_sina_direct(url):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
        r.encoding = "gbk"
        m = re.search(r"=\s*(\{.*?\})\s*;?\s*$", r.text, re.S)
        if not m:
            print(f"[sina_direct] 正则未匹配到 JSON：{r.text[:200]}")
            return []
        d = json.loads(m.group(1))
        rows = []
        for raw in d.values():
            parts = raw.split(",")
            if len(parts) < 13:
                continue
            try:
                rows.append({
                    "name": parts[1],
                    "avg_pct": round(float(parts[4]), 2),
                    "amount_yi": round(float(parts[7]) / 1e8, 2),
                    "leader_name": parts[12],
                })
            except (ValueError, IndexError):
                continue
        # 按 avg_pct 降序
        rows.sort(key=lambda x: x["avg_pct"], reverse=True)
        return rows
    except Exception as e:
        print(f"[sina_direct] 拉取异常: {type(e).__name__}: {e}")
        return []

print("=" * 60)
print("[Step 1] 单独拉取新浪 industry(newSinaHy) 第一名...")
try:
    sina_ind = _parse_sina_direct("https://money.finance.sina.com.cn/q/view/newSinaHy.php")
except Exception as e:
    print(f"  新浪拉取异常（外层）: {e}")
    sina_ind = []

print(f"  sina_ind 长度: {len(sina_ind)}")
sina_top = sina_ind[0] if sina_ind else None
if sina_top:
    print(f"  新浪第1名: name={sina_top['name']}  avg_pct={sina_top['avg_pct']:.2f}%  leader={sina_top.get('leader_name','')}")
    if len(sina_ind) >= 2:
        print(f"  新浪第2名: name={sina_ind[1]['name']}  avg_pct={sina_ind[1]['avg_pct']:.2f}%")
else:
    print("  sina_ind = [] (空) —— 网络/代理不可达 或 解析失败")

print()
print("=" * 60)
print("[Step 2] 调用 core.market.get_boards() —— 双源校准结果")
try:
    import core.market as m
    b = m.get_boards()
    ind = b["industry"]
    print(f"  industry 总数: {len(ind)}")
    for i, x in enumerate(ind[:5]):
        print(f"    Top{i+1}: name={x.get('name',''):<10}  avg_pct={x.get('avg_pct',0):.2f}%  "
              f"amount={x.get('amount_yi',0):.2f}亿  leader={x.get('leader_name','')}")
except Exception as e:
    import traceback
    print(f"  get_boards() 异常: {type(e).__name__}: {e}")
    traceback.print_exc()
    ind = []

print()
print("=" * 60)
print("[Step 3] 判定：industry[0] vs 新浪第1名")
if not ind:
    print("  RESULT: BLOCKED (最终 industry 为空，无法比较)")
elif not sina_top:
    print("  RESULT: BLOCKED (新浪源不可达，无法建立锚点)")
else:
    final_top = ind[0]
    name_match = final_top.get("name") == sina_top["name"]
    diff = abs(final_top.get("avg_pct", 0) - sina_top["avg_pct"])
    print(f"  最终第1名: {final_top.get('name')} {final_top.get('avg_pct',0):.2f}%")
    print(f"  新浪第1名: {sina_top['name']} {sina_top['avg_pct']:.2f}%")
    print(f"  name 相同: {name_match}")
    print(f"  avg_pct 差值: {diff:.2f}pp  (容差 ≤0.3pp)")
    if name_match and diff <= 0.3:
        print("  RESULT: PASS (双源切换生效，已对齐新浪主源)")
    else:
        print("  RESULT: FAIL (未对齐新浪第一名，偏差超容差或name不同)")
