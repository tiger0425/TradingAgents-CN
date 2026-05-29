# FreshnessManager.maintain() 实现记录

## 实现细节
- `tradingagents/kb/freshness.py` 已实现 `maintain()` + `_process_collection()` 辅助方法
- 目录遍历模式：`shared/{collection_name}/*.json` 和 `users/{user_id}/{collection_name}/*.json`
- 每个 JSON 文件的 `freshness` 字段通过 `compute_freshness()` 重新计算，仅在标签变化时写回
- 所有 `import` 移到了模块级别（`json`, `logging`, `Path`, `Tuple`），避免 pyright 找不到变量
- 验证通过：4 条测试用例覆盖 FRESH/STALE/EXPIRED 三种状态以及 shared/users 两种作用域

## 注意事项
- `Path.glob("*.json")` 返回 `Generator`，需要用 `sorted()` 包装以排序
- `write_text` 返回 `int`（写入字节数），LSP 会有 `reportUnusedCallResult` 警告，可忽略
- 用户目录结构比 shared 多一层（`users/{user_id}/{collection_name}/`），需要嵌套 `iterdir()`
