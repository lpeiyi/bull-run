# 诊断行业板块数据
import sys, os
# 脚本位于 scripts/ 下：取上一级（项目根）入 sys.path，保证 `python scripts/diag_boards.py` 能 import core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core.market as m

b = m.get_boards()
ind = b["industry"]
print("行业总数:", len(ind))
print("== 前15名 ==")
for i, x in enumerate(ind[:15]):
    n = x["name"]
    p = x["avg_pct"]
    a = x["amount_yi"]
    l = x.get("leader_name", "")
    print("  %2d. %-8s avg_pct=%6.2f  amount=%8.2f亿  leader=%s" % (i+1, n, p, a, l))
print("== 后10名 ==")
start = max(0, len(ind)-10)
for i in range(start, len(ind)):
    x = ind[i]
    print("  %3d. %-8s avg_pct=%6.2f" % (i+1, x["name"], x["avg_pct"]))

# 单独测东财 push2 接口参数（对比加 fl=f3 vs 不加）
import requests
UA = "Mozilla/5.0"
def _call(extra_params, label):
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {"pn": 1, "pz": 10, "po": 1, "np": 1, "fields": "f12,f14,f3,f6", "fs": "m:90+t:2"}
    params.update(extra_params)
    r = requests.get(url, headers={"User-Agent": UA}, params=params, timeout=12)
    diff = (r.json().get("data") or {}).get("diff") or []
    rows = []
    for it in diff:
        rows.append((it["f14"], round(float(it["f3"])/100, 2)))
    print("\n== %s 前10名 ==" % label)
    for i, (n, p) in enumerate(rows):
        print("  %2d. %-8s pct=%6.2f" % (i+1, n, p))

_call({}, "默认（不加 fl 排序字段）")
_call({"fl": "f3"}, "加 fl=f3（按涨跌幅降序）")
