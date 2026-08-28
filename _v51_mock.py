import py_compile
py_compile.compile('core/market.py', doraise=True)
print('py_compile OK', flush=True)

from core.market import _kpl_cum_weight

# 权重采样
for e in [1,5,15,30,60,120,180,240]:
    w = _kpl_cum_weight(e)
    print(f'w({e:>3}) = {w:.4f}', flush=True)
print('w(0)', _kpl_cum_weight(0), 'w(500)', _kpl_cum_weight(500), flush=True)

# 08-28 真实 cum 验证
Y=21259.0
cums = {1:887.76, 5:2458.32, 15:4951.61, 30:7306.76, 60:10411.33, 120:14233.29, 180:17168.06, 240:21017.15}
exp = {1:(10,25),5:(5,13),15:(2,7),30:(-2,8),60:(-4,5),120:(-5,3),180:(-6,0)}
prev_chg = None
monotone = True
for e in sorted(cums):
    cum = cums[e]
    w = _kpl_cum_weight(e)
    pred = cum / w
    raw = (pred / Y - 1) * 100
    chg = min(30.0, max(-30.0, raw))
    if prev_chg is not None and e != 240 and chg > prev_chg + 1e-5:
        monotone = False
    prev_chg = chg
    if e == 240:
        ok = abs(chg - (-1.14)) < 3
        tag = 'target=-1.14+/-3'
    else:
        lo, hi = exp[e]
        ok = lo <= chg <= hi
        tag = f'exp=[{lo:+d},{hi:+d}]'
    print(f'e={e:>3} w={w:.4f} raw={raw:+.2f} chg={chg:+.2f} {tag} {"OK" if ok else "FAIL"}', flush=True)
print(f'monotone 1..180: {"PASS" if monotone else "FAIL"}', flush=True)
