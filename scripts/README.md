# scripts/ — 诊断与验证脚本

非运行时脚本，供开发调试和历史问题回归时手工执行，不参与 `app.py` 启动流程。

## 运行前提

- 在**项目根目录**下执行（`python scripts/xxx.py`），脚本依赖根目录作为工作目录。
- 已装依赖：`pip install -r requirements.txt`。

## 脚本清单

| 脚本 | 用途 | 运行方式 |
|---|---|---|
| `diag_boards.py` | 诊断行业板块数据：打印 `get_boards()` 返回的行业前 15 / 后 10 名；并对比东财 `push2` 接口「加 `fl=f3`」与「不加」返回的前 10 名顺序差异 | `python scripts/diag_boards.py` |
| `verify_boards.py` | 验收 `fix-industry-top10-sort-order`：直接拉新浪 `newSinaHy` 源第一名，与 `get_boards()` 的第一名做名称 + 涨幅比对，容差 ≤0.3pp，输出 PASS / FAIL | `python scripts/verify_boards.py` |
| `v51_curl.py` | 校验量能卡片接口 `/api/liangneng`：null 数、clamp 范围、关键分钟采样、首段单调衰减、收盘值与卡片涨幅差值 | 先 `start.bat` 启动服务，再 `python scripts/v51_curl.py` |
| `v51_mock.py` | 校验 V5.1 量能累积权重 `_kpl_cum_weight()`：打印各锚点权重，并用 08-28 真实累积量反推预测曲线是否落在预期区间 | `python scripts/v51_mock.py` |

## 备注

- `diag_boards.py`、`verify_boards.py` 需要联网（东财 / 新浪接口）。
- `v51_curl.py` 依赖本地服务运行在 `127.0.0.1:8000`（由 `start.bat` 启动）。
- 这些脚本写于对应 spec 的排查过程中，背景资料见：
  - `.trae/specs/fix-industry-top10-sort-order/`
  - `.trae/specs/optimize-overview-sentiment-volume/`（含量能校准参考截图，放在同目录 `reference/`）
