# -*- coding: utf-8 -*-
"""
通达信公式解释器
- 支持常见技术指标函数：MA/EMA/SMA/REF/LLV/HHV/MAX/MIN/ABS/CROSS/RSI/MACD/KDJ/BOLL 等
- 支持 CODELIKE/NAMELIKE/CAPITAL 等股票属性函数
- 变量赋值：名称:=表达式（中间变量）/ 名称:表达式（输出变量）
- 逻辑运算符：AND OR NOT
- 比较运算符：= > < >= <= <>
- 注释：{ ... }
- 绘图属性（COLORxxx/LINETHICKn 等）自动忽略
所有计算基于 pandas Series 向量化，返回与输入 K 线等长的序列
"""
import re
import numpy as np
import pandas as pd


# ── 技术指标函数 ────────────────────────────────────────

def MA(close, n):
    """简单均线"""
    return close.rolling(n, min_periods=1).mean()


def EMA(close, n):
    """指数均线（通达信 EMA 用 alpha=2/(n+1) 递推）"""
    return close.ewm(span=n, adjust=False).mean()


def SMA(close, n, m=1):
    """通达信 SMA：SMA(X,N,M) = (M*X + (N-M)*SMA')/N"""
    alpha = m / n
    return close.ewm(alpha=alpha, adjust=False).mean()


def REF(x, n):
    """向前引用 n 期"""
    return x.shift(n)


def LLV(x, n):
    """n 期最低值"""
    return x.rolling(n, min_periods=1).min()


def HHV(x, n):
    """n 期最高值"""
    return x.rolling(n, min_periods=1).max()


def MAX(a, b):
    a_s = a if isinstance(a, pd.Series) else b
    b_s = b if isinstance(b, pd.Series) else a
    return np.maximum(pd.Series(a, index=a_s.index) if np.isscalar(a) else a,
                      pd.Series(b, index=b_s.index) if np.isscalar(b) else b)


def MIN(a, b):
    a_s = a if isinstance(a, pd.Series) else b
    b_s = b if isinstance(b, pd.Series) else a
    return np.minimum(pd.Series(a, index=a_s.index) if np.isscalar(a) else a,
                      pd.Series(b, index=b_s.index) if np.isscalar(b) else b)


def ABS(x):
    return np.abs(x)


def CROSS(a, b):
    """上穿：昨日 a<=b，今日 a>b"""
    return (a > b) & (REF(a, 1) <= REF(b, 1))


def RSI(close, n=14):
    """相对强弱指标"""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def MACD(close, fast=12, slow=26, signal=9):
    """MACD：返回 (DIF, DEA, MACD柱)"""
    dif = EMA(close, fast) - EMA(close, slow)
    dea = EMA(dif, signal)
    macd = 2 * (dif - dea)
    return dif, dea, macd


def KDJ(high, low, close, n=9, m1=3, m2=3):
    """KDJ 指标，返回 (K, D, J)"""
    rsv = (close - LLV(low, n)) / (HHV(high, n) - LLV(low, n)).replace(0, np.nan) * 100
    rsv = rsv.fillna(50)
    k = SMA(rsv, m1, 1)
    d = SMA(k, m2, 1)
    j = 3 * k - 2 * d
    return k, d, j


def BOLL(close, n=20, k=2):
    """布林带：返回 (上轨, 中轨, 下轨)"""
    mid = MA(close, n)
    std = close.rolling(n, min_periods=1).std()
    upper = mid + k * std
    lower = mid - k * std
    return upper, mid, lower


def IF(cond, a, b):
    """条件函数"""
    if isinstance(cond, pd.Series):
        return pd.Series(np.where(cond, a, b), index=cond.index)
    return a if cond else b


def COUNT(cond, n):
    """n 期内满足条件的次数"""
    return cond.astype(int).rolling(n, min_periods=1).sum()


def EVERY(cond, n):
    """n 期内一直满足条件"""
    return cond.astype(int).rolling(n, min_periods=1).min().astype(bool)


def EXIST(cond, n):
    """n 期内存在满足条件"""
    return cond.astype(int).rolling(n, min_periods=1).max().astype(bool)


def BARSLAST(cond):
    """上一次条件成立到当前的周期数"""
    result = pd.Series(np.nan, index=cond.index)
    last_pos = -1
    for i, v in enumerate(cond.values):
        if v:
            last_pos = i
            result.iloc[i] = 0
        elif last_pos >= 0:
            result.iloc[i] = i - last_pos
    return result


# ── 表达式解析辅助函数 ──────────────────────────────────

def _find_matching_paren(s, start):
    """从 start 位置的括号出发找匹配的括号，找不到返回 -1"""
    if s[start] == '(':
        depth = 1
        i = start + 1
        while i < len(s) and depth > 0:
            if s[i] == '(': depth += 1
            elif s[i] == ')': depth -= 1
            if depth == 0: return i
            i += 1
    elif s[start] == ')':
        depth = 1
        i = start - 1
        while i >= 0 and depth > 0:
            if s[i] == ')': depth += 1
            elif s[i] == '(': depth -= 1
            if depth == 0: return i
            i -= 1
    return -1


def _find_matching_bracket(s, start):
    """从 '[' 或 ']' 出发找匹配的另一种方括号，找不到返回 -1。

    用于识别「指标属性」展开后的下标后缀，如 KDJ(HIGH,LOW,CLOSE,9,3,3)[2] 里的 [2]。
    """
    if s[start] == '[':
        depth = 1
        i = start + 1
        while i < len(s) and depth > 0:
            if s[i] == '[': depth += 1
            elif s[i] == ']': depth -= 1
            if depth == 0: return i
            i += 1
    elif s[start] == ']':
        depth = 1
        i = start - 1
        while i >= 0 and depth > 0:
            if s[i] == ']': depth += 1
            elif s[i] == '[': depth -= 1
            if depth == 0: return i
            i -= 1
    return -1


def _consume_bracket_suffix(expr, end):
    """若 end 之后紧跟一个或多个 [...] 下标后缀，则一并纳入，返回新的末尾位置。"""
    while end + 1 < len(expr) and expr[end + 1] == '[':
        close = _find_matching_bracket(expr, end + 1)
        if close < 0:
            break
        end = close
    return end


def _extract_term_left(expr, pos):
    """从 pos 向左提取一个完整的项（变量/数字/字符串/括号/函数调用）"""
    i = pos
    while i >= 0 and expr[i] in ' \t': i -= 1
    if i < 0: return None
    # 下标后缀：如 KDJ(...)[2]。从 ']' 回溯到匹配的 '['，再继续取左侧的项。
    if expr[i] == ']':
        br = _find_matching_bracket(expr, i)
        if br < 0: return None
        inner = _extract_term_left(expr, br - 1)
        if inner is None: return None
        return inner[0], i
    end = i
    if expr[i] == ')':
        paren_end = i
        paren_start = _find_matching_paren(expr, paren_end)
        if paren_start < 0: return None
        # 向左看是不是函数名
        k = paren_start - 1
        while k >= 0 and (expr[k].isalpha() or expr[k] == '_' or '\u4e00' <= expr[k] <= '\u9fa5'):
            k -= 1
        k += 1
        if k < paren_start:
            return k, paren_end  # 函数调用
        return paren_start, paren_end  # 纯括号
    if expr[i] == "'":
        j = i - 1
        while j >= 0 and expr[j] != "'": j -= 1
        if j < 0: return None
        return j, end
    j = i
    while j >= 0 and (expr[j].isalnum() or expr[j] in '_%.\u4e00-\u9fa5'):
        j -= 1
    j += 1
    return j, end


def _extract_term_right(expr, pos):
    """从 pos 向右提取一个完整的项（含可选的 [...] 下标后缀）"""
    i = pos
    while i < len(expr) and expr[i] in ' \t': i += 1
    if i >= len(expr): return None
    start = i
    if expr[i] == '(':
        paren_end = _find_matching_paren(expr, i)
        if paren_end < 0: return None
        return start, _consume_bracket_suffix(expr, paren_end)
    if expr[i] == "'":
        j = i + 1
        while j < len(expr) and expr[j] != "'": j += 1
        if j >= len(expr): return None
        return start, j
    j = i
    while j < len(expr) and (expr[j].isalnum() or expr[j] in '_%.\u4e00-\u9fa5'):
        j += 1
    j -= 1
    # 检查后面是不是函数调用
    if j + 1 < len(expr) and expr[j + 1] == '(':
        paren_end = _find_matching_paren(expr, j + 1)
        if paren_end >= 0:
            return start, _consume_bracket_suffix(expr, paren_end)
    return start, _consume_bracket_suffix(expr, j)


# ── 公式预处理 ────────────────────────────────────────

_COMMENT_RE = re.compile(r"\{[^}]*\}")
_ASSIGN_RE = re.compile(r"^\s*([A-Za-z_\u4e00-\u9fa5][A-Za-z0-9_\u4e00-\u9fa5]*)\s*(:=|:)\s*(.+?)\s*;?\s*$")

# 多返回值指标的属性名 → 索引映射
_ATTR_MAP = {
    "KDJ": {"K": 0, "D": 1, "J": 2},
    "MACD": {"DIF": 0, "DIFF": 0, "DEA": 1, "DEM": 1, "MACD": 2, "BAR": 2},
    "BOLL": {"UPPER": 0, "UP": 0, "MID": 1, "BOLL": 1, "LOWER": 2, "LOW": 2},
}
_DEFAULT_PARAMS = {
    "KDJ": "HIGH,LOW,CLOSE,9,3,3",
    "MACD": "CLOSE,12,26,9",
    "BOLL": "CLOSE,20,2",
}

_CMP_OPS = [">=", "<=", "<>", "!=", "=", ">", "<"]
_CMP_FUNC = {
    ">=": "_ge", "<=": "_le", "<>": "_ne", "!=": "_ne",
    "=": "_eq", ">": "_gt", "<": "_lt",
}


def _strip_draw_attrs(expr):
    """去掉表达式末尾的绘图属性（COLORxxx, LINETHICKn, NODRAW 等）"""
    while True:
        m = re.search(
            r",\s*(COLOR[A-Z0-9]+|LINETHICK\d+|NODRAW|DOTLINE|VOLSTICK|CROSSDOT|STICK)\s*$",
            expr, re.IGNORECASE)
        if not m:
            break
        expr = expr[:m.start()]
    return expr


def _expand_attr_access(expr):
    """展开「指标.属性」语法，如 KDJ.J → KDJ(HIGH,LOW,CLOSE,9,3,3)[2]"""
    def _replace(m):
        func = m.group(1).upper()
        args = m.group(2)
        attr = m.group(3).upper()
        if func not in _ATTR_MAP:
            return m.group(0)
        idx = _ATTR_MAP[func].get(attr)
        if idx is None:
            return m.group(0)
        if args is None or args == "":
            params = _DEFAULT_PARAMS.get(func, "")
            return f"{func}({params})[{idx}]"
        return f"{func}{args}[{idx}]"

    pattern = re.compile(
        r"\b([A-Za-z]+)(\([^()]*\))?\.([A-Za-z]+)\b",
        re.IGNORECASE)
    return pattern.sub(_replace, expr)


def _in_string(expr, pos):
    """检查 pos 位置是否在字符串字面量内（单引号）"""
    count = 0
    for i in range(pos):
        if expr[i] == "'":
            # 检查是不是转义的（通达信里一般不转义）
            count += 1
    return count % 2 == 1


def _find_all_cmp(expr):
    """找所有比较运算符位置（全局，含括号内），返回 [(pos, op)]"""
    matches = []
    i = 0
    while i < len(expr):
        if _in_string(expr, i):
            i += 1
            continue
        for op in _CMP_OPS:
            if expr[i:i + len(op)] == op:
                if op == "=" and i > 0 and expr[i - 1] in '<>!':
                    i += 1
                    break
                if op == "=" and i + 1 < len(expr) and expr[i + 1] == '=':
                    i += 1
                    break
                matches.append((i, op))
                i += len(op)
                break
        else:
            i += 1
    return matches


def _find_all_word(expr, word):
    """找所有单词（AND/OR/NOT）位置（全局，含括号内），返回 [pos]"""
    matches = []
    i = 0
    wlen = len(word)
    while i <= len(expr) - wlen:
        if _in_string(expr, i):
            i += 1
            continue
        if expr[i:i + wlen].upper() == word.upper():
            before_ok = (i == 0) or not (expr[i - 1].isalnum() or expr[i - 1] in '_\u4e00-\u9fa5')
            after_pos = i + wlen
            after_ok = (after_pos >= len(expr)) or not (expr[after_pos].isalnum() or expr[after_pos] in '_\u4e00-\u9fa5')
            if before_ok and after_ok:
                matches.append(i)
            i += wlen
        else:
            i += 1
    return matches


def _comparisons_to_func(expr):
    """比较运算转函数调用（从右往左迭代，全局处理含嵌套括号）"""
    prev = None
    while prev != expr:
        prev = expr
        matches = _find_all_cmp(expr)
        if not matches: break
        pos, op = matches[-1]  # 最右边先处理
        left = _extract_term_left(expr, pos - 1)
        if left is None: break
        left_start, left_end = left
        right = _extract_term_right(expr, pos + len(op))
        if right is None: break
        right_start, right_end = right
        left_str = expr[left_start:left_end + 1]
        right_str = expr[right_start:right_end + 1]
        replacement = f"{_CMP_FUNC[op]}({left_str}, {right_str})"
        expr = expr[:left_start] + replacement + expr[right_end + 1:]
    return expr


def _binary_op_to_func(expr, op_word, func_name):
    """二元逻辑运算转函数调用（左结合，从左往右迭代，全局处理）"""
    prev = None
    while prev != expr:
        prev = expr
        positions = _find_all_word(expr, op_word)
        if not positions: break
        pos = positions[0]  # 最左边先处理
        left = _extract_term_left(expr, pos - 1)
        if left is None: break
        left_start, left_end = left
        right = _extract_term_right(expr, pos + len(op_word))
        if right is None: break
        right_start, right_end = right
        left_str = expr[left_start:left_end + 1]
        right_str = expr[right_start:right_end + 1]
        replacement = f"{func_name}({left_str}, {right_str})"
        expr = expr[:left_start] + replacement + expr[right_end + 1:]
    return expr


def _unary_op_to_func(expr, op_word, func_name):
    """一元逻辑运算转函数调用（从右往左迭代，全局处理）"""
    prev = None
    while prev != expr:
        prev = expr
        positions = _find_all_word(expr, op_word)
        if not positions: break
        pos = positions[-1]  # 最右边先处理
        right = _extract_term_right(expr, pos + len(op_word))
        if right is None: break
        right_start, right_end = right
        right_str = expr[right_start:right_end + 1]
        replacement = f"{func_name}({right_str})"
        expr = expr[:pos] + replacement + expr[right_end + 1:]
    return expr


def _preprocess(expr):
    """把通达信表达式转成 Python 可执行表达式
    步骤：剥离绘图属性 → 展开指标.属性 → 比较转函数 → 逻辑转函数
    """
    e = expr.strip()
    e = _strip_draw_attrs(e)
    e = _expand_attr_access(e)
    e = _comparisons_to_func(e)
    e = _unary_op_to_func(e, "NOT", "_not")
    e = _binary_op_to_func(e, "AND", "_and")
    e = _binary_op_to_func(e, "OR", "_or")
    return e


def parse_tdx(code):
    """解析通达信公式，返回 [(var_name, is_output, py_expr)], output_names"""
    lines = []
    outputs = []
    code = _COMMENT_RE.sub("", code)
    stmts = [s.strip() for s in re.split(r"[;\n]", code) if s.strip()]
    for stmt in stmts:
        m = _ASSIGN_RE.match(stmt)
        if m:
            name, op, expr = m.group(1), m.group(2), m.group(3)
            is_output = (op == ":")
            py_expr = _preprocess(expr)
            lines.append((name, is_output, py_expr))
            if is_output:
                outputs.append(name)
        else:
            py_expr = _preprocess(stmt)
            lines.append(("_result", True, py_expr))
            outputs.append("_result")
    return lines, outputs


# ── 公式执行 ──────────────────────────────────────────

def evaluate_tdx(code, df, stock_info=None):
    """
    执行通达信公式
    参数:
        code: 通达信公式代码字符串
        df: K线 DataFrame，含 date, open, high, low, close, volume
        stock_info: 股票信息 dict，如 code, name, industry, mcap_yi
    返回:
        (result_dict, signal)
        result_dict: 所有变量的 Series dict
        signal: 最后一个输出变量的最后一个值（选股信号 True/False）
    """
    stock_info = stock_info or {}
    lines, outputs = parse_tdx(code)
    if not lines:
        return {}, None

    n = len(df)
    idx = df.index
    CLOSE = pd.Series(df["close"].values, index=idx, dtype=float)
    OPEN = pd.Series(df["open"].values, index=idx, dtype=float)
    HIGH = pd.Series(df["high"].values, index=idx, dtype=float)
    LOW = pd.Series(df["low"].values, index=idx, dtype=float)
    VOL = pd.Series(df["volume"].values, index=idx, dtype=float)

    # 比较运算函数（向量化）
    def _eq(a, b): return a == b
    def _gt(a, b): return a > b
    def _lt(a, b): return a < b
    def _ge(a, b): return a >= b
    def _le(a, b): return a <= b
    def _ne(a, b): return a != b

    # 逻辑运算函数（向量化，用位运算符实现）
    def _and(a, b): return a & b
    def _or(a, b): return a | b
    def _not(a): return ~a

    ns = {
        "CLOSE": CLOSE, "C": CLOSE,
        "OPEN": OPEN, "O": OPEN,
        "HIGH": HIGH, "H": HIGH,
        "LOW": LOW, "L": LOW,
        "VOL": VOL, "V": VOL,
        "MA": MA, "EMA": EMA, "SMA": SMA,
        "REF": REF, "LLV": LLV, "HHV": HHV,
        "MAX": MAX, "MIN": MIN, "ABS": ABS,
        "CROSS": CROSS, "RSI": RSI, "MACD": MACD, "KDJ": KDJ, "BOLL": BOLL,
        "IF": IF, "COUNT": COUNT, "EVERY": EVERY, "EXIST": EXIST,
        "BARSLAST": BARSLAST,
        "_eq": _eq, "_gt": _gt, "_lt": _lt,
        "_ge": _ge, "_le": _le, "_ne": _ne,
        "_and": _and, "_or": _or, "_not": _not,
    }

    # 股票属性函数
    def CODELIKE(prefix):
        code = stock_info.get("code", "")
        pure = re.sub(r"^(sh|sz|bj)", "", code, flags=re.IGNORECASE)
        match = pure.startswith(str(prefix))
        return pd.Series([match] * n, index=idx)

    def NAMELIKE(s):
        name = stock_info.get("name", "")
        match = str(s) in name
        return pd.Series([match] * n, index=idx)

    def INBLOCK(block_name):
        industry = stock_info.get("industry", "")
        blocks = stock_info.get("blocks", [])
        match = (str(block_name) == industry) or (str(block_name) in blocks)
        return pd.Series([match] * n, index=idx)

    # CAPITAL：流通股本（手），用总市值近似反推
    mcap = stock_info.get("mcap_yi", 0)
    close_val = float(CLOSE.iloc[-1]) if n > 0 else 1
    hands = (mcap * 1e8 / close_val / 100) if (close_val > 0 and mcap > 0) else 0
    ns["CAPITAL"] = pd.Series([hands] * n, index=idx, dtype=float)
    ns["CODELIKE"] = CODELIKE
    ns["NAMELIKE"] = NAMELIKE
    ns["INBLOCK"] = INBLOCK

    # 逐行执行
    results = {}
    last_output = None
    for name, is_output, py_expr in lines:
        try:
            val = eval(py_expr, {"__builtins__": {}}, ns)
        except Exception as e:
            raise ValueError(f"公式行「{name}」计算失败：{e}\n表达式：{py_expr}") from e
        ns[name] = val
        results[name] = val
        if is_output:
            last_output = val

    signal = None
    if last_output is not None and len(last_output) > 0:
        valid = last_output.dropna()
        if len(valid) > 0:
            signal = bool(valid.iloc[-1])

    return results, signal


def get_signal(code, df, stock_info=None):
    """只返回选股信号（最后一个输出变量的最后值），出错返回 False"""
    try:
        _, signal = evaluate_tdx(code, df, stock_info)
        return signal or False
    except Exception:
        return False


# ── 语法检查 ──────────────────────────────────────────

def check_tdx_syntax(code):
    """检查通达信公式语法，返回 (ok, error_msg)"""
    try:
        lines, outputs = parse_tdx(code)
        if not lines:
            return False, "公式为空"
        if not outputs:
            return False, "没有输出信号（用冒号赋值：选股条件: ...）"
        test_df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=60),
            "open": [10 + i * 0.1 for i in range(60)],
            "high": [10.5 + i * 0.1 for i in range(60)],
            "low": [9.5 + i * 0.1 for i in range(60)],
            "close": [10.2 + i * 0.1 for i in range(60)],
            "volume": [100000] * 60,
        })
        evaluate_tdx(code, test_df, {
            "code": "sh600000", "name": "测试股票",
            "industry": "银行", "mcap_yi": 1000
        })
        return True, ""
    except Exception as e:
        return False, str(e)


# 各函数对K线天数的需求（取函数名对应的参数索引，默认第2个参数是周期）
# 格式: {函数名: (参数索引, 倍数系数)} — 实际需要天数 = 参数值 * 系数 + 余量
# EMA 需要更多历史数据来初始化，所以系数较大
_PERIOD_FUNC_MAP = {
    "MA":       (1, 1.0),    # MA(C, N) -> N
    "EMA":      (1, 2.5),    # EMA(C, N) -> N * 2.5 (需要更多历史来稳定)
    "SMA":      (1, 1.5),    # SMA(C, N, M) -> N * 1.5
    "REF":      (1, 1.0),    # REF(X, N) -> N
    "LLV":      (1, 1.0),    # LLV(X, N) -> N
    "HHV":      (1, 1.0),    # HHV(X, N) -> N
    "RSI":      (1, 1.5),    # RSI(C, N) -> N * 1.5
    "MACD":     (1, 2.0),    # MACD(C, fast, slow, signal) -> 取 slow 参数 * 2
    "KDJ":      (0, 1.5),    # KDJ(N, M1, M2) -> N * 1.5（N是第1个参数）
    "BOLL":     (0, 1.5),    # BOLL(N, K) -> N * 1.5
    "COUNT":    (1, 1.0),    # COUNT(cond, N) -> N
    "EVERY":    (1, 1.0),    # EVERY(cond, N) -> N
    "EXIST":    (1, 1.0),    # EXIST(cond, N) -> N
    "BARSLAST": (None, 60),  # BARSLAST(cond) -> 固定给60天
}

_MIN_DAYS = 30     # 最少30天（保证基础指标能初始化）
_MAX_DAYS = 250    # 最多250天（年线足够了）
_BUFFER_DAYS = 10  # 额外预留天数


def estimate_tdx_days(code):
    """
    扫描通达信代码，估算需要多少天的K线数据。
    返回估算天数（在 _MIN_DAYS ~ _MAX_DAYS 之间）
    """
    if not code or not code.strip():
        return _MIN_DAYS

    max_period = 0

    # 预处理：去掉注释 { ... }
    clean = re.sub(r'\{[^}]*\}', '', code)

    # 遍历所有已知周期函数，查找其调用
    for func_name, (param_idx, multiplier) in _PERIOD_FUNC_MAP.items():
        # 匹配 FUNC(...) 形式，大小写不敏感
        pattern = re.compile(
            r'\b' + re.escape(func_name) + r'\s*\(([^)]*)\)',
            re.IGNORECASE
        )
        for m in pattern.finditer(clean):
            args_str = m.group(1)
            if param_idx is None:
                # 固定天数的函数（如 BARSLAST）
                period = multiplier
            else:
                # 按逗号分割参数，取对应索引
                args = [a.strip() for a in args_str.split(',')]
                if param_idx >= len(args):
                    continue
                param_val = args[param_idx]
                # 尝试解析为数字
                try:
                    n = float(param_val)
                    period = int(n * multiplier)
                except (ValueError, TypeError):
                    # 参数不是纯数字（可能是变量/表达式），给个保守估计
                    period = 60

            if period > max_period:
                max_period = period

    # 加上缓冲天数，并限制在范围内
    days = max_period + _BUFFER_DAYS
    days = max(_MIN_DAYS, min(days, _MAX_DAYS))
    return days
