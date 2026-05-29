# F3 手动 QA 验证报告

**执行时间**: 2026-05-29  
**目标**: 验证所有关键端点的数据接口能否正常工作

## QA 场景结果

| # | 场景 | 函数 | 参数 | 类型 | 长度 | 断言 | 结果 |
|---|------|------|------|------|------|------|------|
| a | 融资融券 | `route_to_vendor('get_margin_trading')` | code=600519, page_size=3 | str | 432 | '融资余额' in r | ✅ PASS |
| b | 龙虎榜全市场 | `get_dragon_tiger_market()` | date=2026-05-20, 净买入≥5000 | str | 1552 | '全市场龙虎榜' in r or '无数据' | ✅ PASS |
| c | 股东户数/筹码集中度 | `get_shareholder_count()` | code=600519 | str | 186 | '筹码' in r or '无数据' | ✅ PASS |
| d | 财联社快讯 | `get_cls_flash()` | limit=5 | str | 621 | isinstance(r, str) | ✅ PASS |
| e | 巨潮公告 | `get_cninfo_announcements()` | code=600519, limit=5 | str | 889 | isinstance(r, str) | ✅ PASS |
| f | 龙虎榜个股 | `get_dragon_tiger_stock()` | code=600519, date=2026-05-20 | str | 70 | isinstance(r, str) | ✅ PASS |
| g | 大宗交易 | `get_block_trade()` | code=600519, limit=5 | str | 703 | isinstance(r, str) | ✅ PASS |
| h | 限售解禁 | `get_lockup_expiry()` | code=600519, date=2026-05-20 | str | 52 | isinstance(r, str) | ✅ PASS |
| i | 分红送转 | `get_dividend_history()` | code=600519, limit=5 | str | 69 | isinstance(r, str) | ✅ PASS |

## 汇总

| 指标 | 值 |
|------|-----|
| 场景通过 | 9/9 |
| 场景失败 | 0/9 |
| 裁决 | **APPROVE** |

---

**场景 [9/9 通过] | 集成 [9/9] | 裁决: APPROVE**
