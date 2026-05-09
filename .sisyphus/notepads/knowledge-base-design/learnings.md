# learnings — knowledge-base-design

## 2026-05-09: AnalysisArchive 模块实现

### 模式与约定
- `from __future__ import annotations` 放在模块顶部
- 使用 `pathlib.Path` 处理所有路径操作（与 memory.py / watchlist.py 一致）
- 原子写入模式：写 `.tmp` → `pathlib.Path.replace()`（POSIX 下原子操作）
- config dict 支持两种用法：直接路径 (`str | Path`) 或 config dict
- JSON 写入使用 `json.dumps(data, ensure_ascii=False, indent=2)` 保持中文可读
- 归档目录结构：`{archive_dir}/YYYY/MM/DD/{entry_type}_{ticker}.json`
- index.json 三个层级：root (全量) / month / day，每层共享同一 schema

### 设计决策
- 构造函数同时接受 `str | Path | dict | None`，与现有模块灵活性一致
- `_update_index` 使用增量更新（单条 add/remove）避免全量重建
- `_build_index` / `rebuild_index` 提供全量重建能力，用于修复/迁移
- `_extract_meta` 从完整分析 JSON 提取索引元数据，统一入口格式
- `list()` 只返回元数据（不加载完整文件），`get()` 才加载完整 JSON

### 成功方法
- 使用 `_rebuild_lookups` 统一重建 `by_ticker` / `by_decision` 倒排索引
- `_index_paths_for_entry` 从日期字符串推导三个层级的索引路径
- `_load_index` 对缺失/损坏的 index.json 返回 `_empty_index()`，确保不抛异常
