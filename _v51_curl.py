import json, urllib.request
url = 'http://127.0.0.1:8000/api/liangneng'
d = json.loads(urllib.request.urlopen(url, timeout=20).read().decode('utf-8'))
print('trade_date', d['trade_date'])
print('A/P/Y', d['actual'], d['predict'], d['yesterday'])
print('cp/ca', d['change_pct'], d['change_abs'])
print('trend_len', len(d['trend']))
print('intraday_len', len(d['intraday']))

# 检查 null / clamp
nulls = sum(1 for x in d['intraday'] if x['chg'] is None)
vals = [x['chg'] for x in d['intraday'] if x['chg'] is not None]
print('null_count', nulls, 'min', min(vals), 'max', max(vals))

# 关键分钟采样
target_indices = {}
for i, x in enumerate(d['intraday']):
    t = x['time']
    hm = int(t.replace(':', ''))
    e = None
    if hm == 931: e = 1
    elif hm == 935: e = 5
    elif hm == 945: e = 15
    elif hm == 1000: e = 30
    elif hm == 1030: e = 60
    elif hm == 1130: e = 120
    elif hm == 1400: e = 180
    elif hm == 1500: e = 240
    if e is not None and e not in target_indices:
        target_indices[e] = (i, x['time'], x['chg'])
for e in sorted(target_indices):
    i, t, chg = target_indices[e]
    # 注：接口 cp 以 actual/yesterday(20831) 为基准，不是 21259。这里只看形状和量级
    print(f'e={e:>3} idx={i:>3} t={t} chg={chg:+.2f}')

# 单调性检查：首段 e=1..180 应逐步衰减
mono_pts = [(e, target_indices[e][2]) for e in [1,5,15,30,60,120,180] if e in target_indices]
print('mono sequence:', ' > '.join(f'{v:+.2f}' for _, v in mono_pts))
decreasing = all(mono_pts[i][1] > mono_pts[i+1][1] for i in range(len(mono_pts)-1))
print('monotonically decreasing (e1..180):', 'PASS' if decreasing else 'FAIL')

# 收盘最后一个值和 change_pct 接近（盘后模式）
last_t, last_chg = d['intraday'][-1]['time'], d['intraday'][-1]['chg']
print(f'last point {last_t} chg={last_chg:+.2f}, card change_pct={d["change_pct"]:+.2f}, diff={last_chg - d["change_pct"]:+.2f}')
