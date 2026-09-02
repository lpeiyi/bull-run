# -*- coding: utf-8 -*-
"""
选股引擎：全市场股票列表 + K线缓存 + 通达信指标选股 + 过滤条件
"""
import os
import time
import json
import re
from datetime import datetime

import pandas as pd
import requests

from core.data import kline, real_quotes, to_symbol, UA
from core.tdx import get_signal, evaluate_tdx, check_tdx_syntax, estimate_tdx_days

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE_DIR = os.path.join(_BASE, "data", "screener")
_KLINE_DIR = os.path.join(_CACHE_DIR, "klines")
_LIST_FILE = os.path.join(_CACHE_DIR, "stock_list.json")

os.makedirs(_KLINE_DIR, exist_ok=True)

_EM_SESSION = requests.Session()
_EM_SESSION.headers.update({"User-Agent": UA})


def _safe_float(v, default=0.0):
    """安全转 float，处理 '-' 等非数值"""
    try:
        if v is None or v == "-" or v == "":
            return default
        return float(v)
    except (ValueError, TypeError):
        return default


def _sina_get(node, page, num=100):
    """新浪股票列表接口"""
    url = "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
    params = {
        "page": page, "num": num, "sort": "symbol", "asc": 1,
        "node": node, "symbol": "", "_s_r_a": "page",
    }
    r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=15)
    return r.json()


# ── 全市场股票列表 ────────────────────────────────────

def load_stock_list(force=False):
    """
    获取全市场 A 股列表（沪深京），缓存 24 小时
    返回 [{code, name, market, mcap_yi, fmcap_yi, industry, ...}]
    """
    now = time.time()
    if not force and os.path.exists(_LIST_FILE):
        try:
            with open(_LIST_FILE, encoding="utf-8") as f:
                d = json.load(f)
            if now - d.get("ts", 0) < 24 * 3600:
                return d.get("stocks", [])
        except (OSError, ValueError):
            pass

    stocks = _fetch_sina_stock_list()
    with open(_LIST_FILE, "w", encoding="utf-8") as f:
        json.dump({"ts": now, "stocks": stocks}, f, ensure_ascii=False)
    return stocks


def _fetch_sina_stock_list():
    """从新浪财经分页拉全市场 A 股列表"""
    node = "hs_a"  # 沪深A股（含北交所）
    page_size = 100
    max_page = 200  # 上限保护
    all_data = []

    for page in range(1, max_page + 1):
        try:
            diff = _sina_get(node, page, page_size)
        except Exception:
            break

        if not diff:
            break
        all_data.extend(diff)
        if len(diff) < page_size:
            break

    out = []
    for item in all_data:
        symbol = item.get("symbol", "")   # 如 sh600000 / sz000001 / bj920000
        code = item.get("code", "")
        name = item.get("name", "")
        if not symbol:
            continue

        # 判断市场
        if symbol.startswith("sh"):
            market = "sh"
        elif symbol.startswith("sz"):
            market = "sz"
        elif symbol.startswith("bj"):
            market = "bj"
        else:
            market = "sz"

        # 新浪 mktcap 单位是万元，转成亿
        mktcap_wan = _safe_float(item.get("mktcap"))
        nmc_wan = _safe_float(item.get("nmc"))
        amount_yuan = _safe_float(item.get("amount"))   # 元

        out.append({
            "code": symbol,
            "pure_code": code,
            "name": name,
            "market": market,
            "price": _safe_float(item.get("trade")),
            "change_pct": _safe_float(item.get("changepercent")),
            "amount_yi": round(amount_yuan / 1e8, 2),
            "turnover_pct": _safe_float(item.get("turnoverratio")),
            "pe_ttm": _safe_float(item.get("per")),
            "mcap_yi": round(mktcap_wan / 1e4, 2),   # 万元 → 亿元
            "fmcap_yi": round(nmc_wan / 1e4, 2),
            "industry": "",   # 新浪接口暂无行业字段，由 _industry_map() 补充
        })
    return out


# ── 东财行业映射（补充新浪缺字段） ────────────────────────

_INDUSTRY_MAP_FILE = os.path.join(_BASE, "data", "industry_map.json")
_industry_map_cache = None   # 进程内缓存，避免重复读文件


def _fetch_em_industry_map():
    """从东财 clist 接口拉全 A 股列表，构建 {pure_code: industry_name} 映射。

    东财 clist 接口 fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048
    覆盖沪深京全 A 股；f100 为所属行业（东财行业分类）。
    """
    url = "http://push2.eastmoney.com/api/qt/clist/get"
    # fs: 深主板+创业板+沪主板+科创板+北交所
    fs = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
    out = {}
    page_size = 100
    for page in range(1, 60):   # 上限保护，A股约 5500 只 / 100 ≈ 55 页
        params = {"pn": page, "pz": page_size, "po": 1, "np": 1,
                  "fields": "f12,f100", "fs": fs}
        try:
            r = _EM_SESSION.get(url, params=params, timeout=12)
            diff = (r.json().get("data") or {}).get("diff") or []
        except Exception:
            break
        if not diff:
            break
        for item in diff:
            code = item.get("f12", "")
            ind = item.get("f100", "")
            if code and ind:
                out[code] = ind
        if len(diff) < page_size:
            break
    return out


def _industry_map():
    """惰性加载全市场个股 → 行业映射，缓存 24 小时。

    首次调用时从东财拉取并写入 data/industry_map.json，后续直接读缓存。
    返回 {pure_code: industry_name}；拉取失败时返回空 dict（前端显示 "--"）。
    """
    global _industry_map_cache
    if _industry_map_cache is not None:
        return _industry_map_cache

    now = time.time()
    # 尝试从缓存文件读（24h 有效）
    if os.path.exists(_INDUSTRY_MAP_FILE):
        try:
            with open(_INDUSTRY_MAP_FILE, encoding="utf-8") as f:
                d = json.load(f)
            if now - d.get("ts", 0) < 24 * 3600:
                _industry_map_cache = d.get("map", {})
                return _industry_map_cache
        except (OSError, ValueError):
            pass

    # 缓存过期或不存在，从东财拉取
    m = _fetch_em_industry_map()
    _industry_map_cache = m
    try:
        with open(_INDUSTRY_MAP_FILE, "w", encoding="utf-8") as f:
            json.dump({"ts": now, "map": m}, f, ensure_ascii=False)
    except OSError:
        pass
    return m


# ── K 线缓存 ──────────────────────────────────────────

def _kline_cache_path(code, adjust):
    """K线缓存文件路径"""
    return os.path.join(_KLINE_DIR, f"{code}_{adjust}.csv")


def get_cached_kline(code, days=250, adjust="qfq"):
    """
    获取 K 线，带本地文件缓存
    当日已缓存则直接读文件；否则重新拉取并保存
    """
    path = _kline_cache_path(code, adjust)
    today = datetime.now().strftime("%Y-%m-%d")
    need_fetch = True

    if os.path.exists(path):
        try:
            df = pd.read_csv(path, parse_dates=["date"])
            # 检查缓存是否是今天的
            cache_date = df["date"].max().strftime("%Y-%m-%d") if len(df) else ""
            if cache_date == today:
                need_fetch = False
                return df.tail(days).reset_index(drop=True)
        except Exception:
            pass

    if need_fetch:
        try:
            df = kline(code, days=max(days + 150, 300), adjust=adjust)
            if len(df) > 0:
                df.to_csv(path, index=False)
            return df.tail(days).reset_index(drop=True)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


# ── 选股范围过滤 ──────────────────────────────────────

def _match_scope(stock, scope):
    """判断股票是否在选股范围内"""
    if not scope:
        return True
    code = stock["pure_code"]
    market = stock["market"]
    # scope 是列表，如 ['sh_main', 'sz_main', 'cyb', 'kcb', 'bj']
    # 先做简单判断：默认全选
    if "all" in scope:
        return True
    in_any = False
    if "sh_main" in scope and market == "sh" and not code.startswith("688"):
        in_any = True
    if "sz_main" in scope and market == "sz" and not code.startswith("300"):
        in_any = True
    if "cyb" in scope and code.startswith("300"):
        in_any = True
    if "kcb" in scope and code.startswith("688"):
        in_any = True
    if "bj" in scope and market == "bj":
        in_any = True
    return in_any


def _match_exclude(stock, exclude):
    """判断是否需要排除"""
    name = stock["name"]
    if not exclude:
        return False
    if "st" in exclude and ("ST" in name.upper() or "*ST" in name.upper()):
        return True
    if "suspend" in exclude and stock.get("price", 0) <= 0:
        return True
    if "new" in exclude:
        # 新股上市未满 N 天暂时不处理（需要上市日期）
        pass
    return False


# ── 选股执行 ──────────────────────────────────────────

_SCREEN_STATE = {}   # 选股任务状态：{task_id: {status, progress, results, error}}


def run_screen(indicator_code, config=None):
    """
    执行选股（同步，用于小范围测试）
    参数:
        indicator_code: 通达信公式代码
        config: 选股配置 dict
            - scope: 选股范围列表，如 ['sh_main', 'sz_main', 'cyb', 'kcb', 'bj']
            - exclude: 排除列表，如 ['st', 'suspend', 'new']
            - adjust: 复权方式 qfq/hfq/bfq
            - days: K线天数（默认 250）
            - limit: 结果上限
            - sort_by: 排序字段
    返回: [stock_info...]
    """
    config = config or {}
    scope = config.get("scope", ["all"])
    exclude = config.get("exclude", ["st"])
    adjust = config.get("adjust", "qfq")
    # 自动估算K线天数，也支持配置里显式指定
    config_days = int(config.get("days", 0) or 0)
    estimated = estimate_tdx_days(indicator_code)
    days = max(config_days, estimated)
    limit = int(config.get("limit", 100))
    sort_by = config.get("sort_by", "change_pct")

    stocks = load_stock_list()
    results = []

    for s in stocks:
        # 范围过滤
        if not _match_scope(s, scope):
            continue
        # 排除过滤
        if _match_exclude(s, exclude):
            continue
        # 拉 K 线
        df = get_cached_kline(s["code"], days=days, adjust=adjust)
        if df.empty or len(df) < min(days, 20):
            continue
        # 计算信号
        stock_info = {
            "code": s["code"],
            "name": s["name"],
            "industry": s.get("industry", ""),
            "mcap_yi": s.get("mcap_yi", 0),
            "fmcap_yi": s.get("fmcap_yi", 0),
        }
        hit = get_signal(indicator_code, df, stock_info)
        if hit:
            results.append({
                "code": s["code"],
                "pure_code": s["pure_code"],
                "name": s["name"],
                "price": s.get("price", 0),
                "change_pct": s.get("change_pct", 0),
                "amount_yi": s.get("amount_yi", 0),
                "turnover_pct": s.get("turnover_pct", 0),
                "mcap_yi": s.get("mcap_yi", 0),
                "industry": s.get("industry", "")
                    or _industry_map().get(s.get("pure_code", ""), "")
                    or _industry_map().get(s.get("code", ""), ""),
            })
            if len(results) >= limit:
                break

    # 排序
    results.sort(key=lambda x: x.get(sort_by, 0), reverse=True)
    return results[:limit]


# ── 异步选股（后台线程） ────────────────────────────────

import threading
import uuid


def start_screen_async(indicator_code, config=None):
    """启动异步选股任务，返回 task_id"""
    task_id = uuid.uuid4().hex[:8]
    _SCREEN_STATE[task_id] = {
        "status": "running",
        "progress": 0,
        "total": 0,
        "results": [],
        "error": None,
        "start_time": time.time(),
        "cancelled": False,
    }

    def _worker():
        try:
            config_ = config or {}
            scope = config_.get("scope", ["all"])
            exclude = config_.get("exclude", ["st"])
            adjust = config_.get("adjust", "qfq")
            # 自动估算K线天数，也支持配置里显式指定
            config_days = int(config_.get("days", 0) or 0)
            estimated = estimate_tdx_days(indicator_code)
            days = max(config_days, estimated)
            limit = int(config_.get("limit", 100))
            sort_by = config_.get("sort_by", "change_pct")
            min_required = min(days, 20)

            stocks = load_stock_list()
            # 先过滤范围和排除项，得到待选池
            pool = [s for s in stocks if _match_scope(s, scope) and not _match_exclude(s, exclude)]
            total = len(pool)
            _SCREEN_STATE[task_id]["total"] = total
            _SCREEN_STATE[task_id]["est_days"] = days
            results = []

            for idx, s in enumerate(pool):
                # 检查是否被取消
                if _SCREEN_STATE.get(task_id, {}).get("cancelled"):
                    _SCREEN_STATE[task_id]["status"] = "cancelled"
                    return

                df = get_cached_kline(s["code"], days=days, adjust=adjust)
                if df.empty or len(df) < min_required:
                    _SCREEN_STATE[task_id]["progress"] = idx + 1
                    continue
                stock_info = {
                    "code": s["code"],
                    "name": s["name"],
                    "industry": s.get("industry", ""),
                    "mcap_yi": s.get("mcap_yi", 0),
                    "fmcap_yi": s.get("fmcap_yi", 0),
                }
                hit = get_signal(indicator_code, df, stock_info)
                if hit:
                    results.append({
                        "code": s["code"],
                        "pure_code": s["pure_code"],
                        "name": s["name"],
                        "price": s.get("price", 0),
                        "change_pct": s.get("change_pct", 0),
                        "amount_yi": s.get("amount_yi", 0),
                        "turnover_pct": s.get("turnover_pct", 0),
                        "mcap_yi": s.get("mcap_yi", 0),
                        "industry": s.get("industry", "")
                            or _industry_map().get(s.get("pure_code", ""), "")
                            or _industry_map().get(s.get("code", ""), ""),
                    })
                    if len(results) >= limit:
                        _SCREEN_STATE[task_id]["progress"] = total
                        break
                _SCREEN_STATE[task_id]["progress"] = idx + 1

            results.sort(key=lambda x: x.get(sort_by, 0), reverse=True)
            _SCREEN_STATE[task_id]["results"] = results[:limit]
            _SCREEN_STATE[task_id]["status"] = "done"
        except Exception as e:
            _SCREEN_STATE[task_id]["status"] = "error"
            _SCREEN_STATE[task_id]["error"] = str(e)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return task_id


def cancel_screen(task_id):
    """取消正在运行的选股任务"""
    if task_id in _SCREEN_STATE and _SCREEN_STATE[task_id]["status"] == "running":
        _SCREEN_STATE[task_id]["cancelled"] = True
        return True
    return False


def get_screen_state(task_id):
    """获取选股任务状态"""
    return _SCREEN_STATE.get(task_id)


# ── 飞书推送选股结果 ────────────────────────────────────

def push_screen_results(indicator_name, results, webhook):
    """
    把选股结果推送到飞书
    """
    from core.notifier import send_feishu

    if not webhook:
        return False, "未配置 webhook"

    count = len(results)
    title = f"【智能选股】{indicator_name} · 命中 {count} 只"

    if count == 0:
        text = "今日无符合条件的股票。"
    else:
        lines = [f"{'代码':<8}{'名称':<10}{'现价':>8}{'涨跌幅':>8}"]
        lines.append("-" * 40)
        for r in results[:20]:  # 最多显示 20 只
            chg = r.get("change_pct", 0)
            chg_str = f"{chg:+.2f}%"
            lines.append(f"{r.get('pure_code', r.get('code','')):<8}{r.get('name',''):<10}{r.get('price',0):>8.2f}{chg_str:>8}")
        if count > 20:
            lines.append(f"... 还有 {count - 20} 只，详见选股页")
        text = "\n".join(lines)

    ok, msg = send_feishu(webhook, title, text)
    return ok, msg

def backtest_indicator(indicator_code, code, days=250, adjust="qfq"):
    """
    对单个标的回测通达信指标
    返回 {total_ret, annual_ret, max_drawdown, win_rate, trade_count, benchmark_ret, trades, equity, dates}
    """
    df = get_cached_kline(code, days=days, adjust=adjust)
    if df.empty:
        return {"error": "K线数据为空"}

    stock_info = {"code": code, "name": "", "industry": "", "mcap_yi": 0}
    results, _ = evaluate_tdx(indicator_code, df, stock_info)
    if not results:
        return {"error": "指标计算失败"}

    # 找输出变量（最后一个变量如果是 bool 型就作为买卖信号）
    signal_series = None
    for name in reversed(list(results.keys())):
        v = results[name]
        if isinstance(v, pd.Series):
            signal_series = v
            break
    if signal_series is None:
        return {"error": "未找到输出信号"}

    # 将信号转为 1（买入）/-1（卖出）/0（无操作）
    # 信号从 0 变 1 的下一日开盘买入，从 1 变 0 的下一日开盘卖出
    signal_bool = signal_series.astype(bool)
    n = len(df)
    init_cash = 100000.0
    fee_rate = 0.00025

    cash, shares = init_cash, 0.0
    equity, trades = [], []
    buy_date = buy_price = None
    holding = False

    for i in range(n):
        price = float(df["close"].iloc[i])
        date = df["date"].iloc[i]
        sig = bool(signal_bool.iloc[i])

        if sig and not holding:
            # 买入（用收盘价近似，实际应次日开盘）
            shares = cash * (1 - fee_rate) / price
            cash = 0.0
            buy_date, buy_price = date, price
            holding = True
        elif not sig and holding:
            # 卖出
            cash = shares * price * (1 - fee_rate)
            trades.append({
                "buy_date": buy_date.strftime("%Y-%m-%d"),
                "sell_date": date.strftime("%Y-%m-%d"),
                "buy_price": round(buy_price, 4),
                "sell_price": round(price, 4),
                "ret": round(price / buy_price - 1, 4),
                "days": (date - buy_date).days,
            })
            shares = 0.0
            buy_date = buy_price = None
            holding = False

        equity.append(cash + shares * price)

    eq = pd.Series(equity)
    total_ret = float(eq.iloc[-1] / init_cash - 1)
    years = n / 252 if n else 1
    annual_ret = float((eq.iloc[-1] / init_cash) ** (1 / years) - 1) if eq.iloc[-1] > 0 else -1.0
    cummax = eq.cummax()
    mdd = float(((eq - cummax) / cummax).min())
    wins = sum(1 for t in trades if t["ret"] > 0)
    win_rate = round(wins / len(trades) * 100, 2) if trades else 0.0
    bh = pd.Series(df["close"] / df["close"].iloc[0] * init_cash)
    bh_ret = float(bh.iloc[-1] / init_cash - 1)

    return {
        "total_ret": round(total_ret * 100, 2),
        "annual_ret": round(annual_ret * 100, 2),
        "max_drawdown": round(mdd * 100, 2),
        "win_rate": win_rate,
        "trade_count": len(trades),
        "benchmark_ret": round(bh_ret * 100, 2),
        "dates": [d.strftime("%Y-%m-%d") for d in df["date"]],
        "equity": [round(x, 2) for x in eq],
        "benchmark": [round(x, 2) for x in bh],
        "trades": trades,
    }
