#!/usr/bin/env python3
"""
verify_tool_alignment.py

使用 Python ast 模块解析：
  1. tradingagents/agents/analysts/*.py 中各 analyst 的 `tools = [...]` 列表
  2. tradingagents/bootstrap.py `_create_tool_nodes()` 中 ToolNode 注册表

对比两组工具名，输出不匹配详情。
退出码: 0 = 完全对齐, 1 = 存在不匹配。
"""

import ast
import os
import sys

# 项目根目录
PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..")
)
ANALYSTS_DIR = os.path.join(
    PROJECT_ROOT, "tradingagents", "agents", "analysts"
)
BOOTSTRAP_PATH = os.path.join(
    PROJECT_ROOT, "tradingagents", "bootstrap.py"
)

# 文件名 → TOOL_KEY_MAP 中的 agent key
# TOOL_KEY_MAP 定义了 analyst agent → bootstrap ToolNode key 的映射
FILENAME_TO_AGENT_KEY = {
    "fundamentals_analyst.py": "fundamentals_analyst",
    "news_analyst.py": "news_analyst",
    "market_analyst.py": "market_analyst",
    "social_media_analyst.py": "social_analyst",  # 文件名不含 "media"
}

# agent key → bootstrap ToolNode dict key
TOOL_KEY_MAP = {
    "market_analyst": "market",
    "fundamentals_analyst": "fundamentals",
    "news_analyst": "news",
    "social_analyst": "social",
}


def extract_name(node: ast.expr) -> str:
    """从 AST 节点提取完全限定名。
    处理 ast.Name('get_news') 和 ast.Attribute(...) 链。
    """
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return extract_name(node.value) + "." + node.attr
    elif isinstance(node, ast.Subscript):
        return extract_name(node.value) + "[]"
    else:
        return ast.dump(node)


def extract_tools_from_analyst(filepath: str) -> list[str]:
    """解析 analyst.py 文件，返回 `tools = [...]` 列表中的工具名。"""
    with open(filepath, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    tools_list: list[str] | None = None

    for node in ast.walk(tree):
        # 查找 `tools = [...]` 的赋值语句
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "tools"
                    and isinstance(node.value, ast.List)
                ):
                    tools_list = [
                        extract_name(el) for el in node.value.elts
                    ]
                    break

    return tools_list or []


def extract_tool_nodes_from_bootstrap(filepath: str) -> dict[str, list[str]]:
    """解析 bootstrap.py，从 _create_tool_nodes() 返回的 dict 中提取
    {bootstrap_key: [tool_name, ...], ...}。
    """
    with open(filepath, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name != "_create_tool_nodes":
            continue

        # 在 _create_tool_nodes 中寻找 return { ... }
        for child in ast.walk(node):
            if not isinstance(child, ast.Return):
                continue
            if not isinstance(child.value, ast.Dict):
                continue

            result: dict[str, list[str]] = {}
            dict_node = child.value
            for key_node, val_node in zip(
                dict_node.keys, dict_node.values
            ):
                # key 必须是字符串字面量
                if not isinstance(key_node, ast.Constant):
                    continue
                bootstrap_key = key_node.value

                # value 必须是 ToolNode([...]) 调用
                if not isinstance(val_node, ast.Call):
                    continue
                func = val_node.func
                if not isinstance(func, ast.Name) or func.id != "ToolNode":
                    continue
                if not val_node.args:
                    continue
                first_arg = val_node.args[0]
                if not isinstance(first_arg, ast.List):
                    continue

                tool_names = [
                    extract_name(el) for el in first_arg.elts
                ]
                result[bootstrap_key] = tool_names

            return result

    return {}


def main() -> int:
    has_mismatch = False

    # 1) 解析 bootstrap.py ToolNode 注册表
    bootstrap_tools = extract_tool_nodes_from_bootstrap(BOOTSTRAP_PATH)
    if not bootstrap_tools:
        print("ERROR: 未能从 bootstrap.py 提取 ToolNode 注册表", file=sys.stderr)
        return 1

    # 2) 遍历所有 analyst 文件
    analyst_files = sorted(
        f for f in os.listdir(ANALYSTS_DIR) if f.endswith(".py")
    )

    for filename in analyst_files:
        filepath = os.path.join(ANALYSTS_DIR, filename)

        # 跳过 __init__.py
        if filename == "__init__.py":
            continue

        # 获取 agent key
        agent_key = FILENAME_TO_AGENT_KEY.get(filename)
        if agent_key is None:
            print(f"SKIP: {filename} — 不在映射表中")
            continue

        # 获取 bootstrap key
        bootstrap_key = TOOL_KEY_MAP.get(agent_key)
        if bootstrap_key is None:
            print(f"SKIP: {filename} (agent={agent_key}) — 不在 TOOL_KEY_MAP 中")
            continue

        # 提取 bind_tools 工具列表
        bind_tools = extract_tools_from_analyst(filepath)

        # 提取 ToolNode 工具列表
        tool_node_tools = bootstrap_tools.get(bootstrap_key, [])
        if not tool_node_tools:
            print(
                f"WARN: bootstrap_key={bootstrap_key!r} 未在 ToolNode 注册表中找到",
                file=sys.stderr,
            )
            continue

        # 比较
        set_bind = set(bind_tools)
        set_node = set(tool_node_tools)

        if set_bind == set_node:
            print(
                f"OK: {filename} ({agent_key} → {bootstrap_key}) — "
                f"bind_tools({len(bind_tools)}) == ToolNode({len(tool_node_tools)})"
            )
        else:
            has_mismatch = True
            missing_in_bind = set_node - set_bind
            extra_in_bind = set_bind - set_node

            parts = [
                f"MISMATCH: {filename} ({agent_key} → {bootstrap_key})",
                f"  bind_tools[{len(bind_tools)}]: {bind_tools}",
                f"  ToolNode[{len(tool_node_tools)}]: {tool_node_tools}",
            ]
            if missing_in_bind:
                parts.append(
                    f"  → ToolNode 中有但 bind_tools 缺少: {sorted(missing_in_bind)}"
                )
            if extra_in_bind:
                parts.append(
                    f"  → bind_tools 中有但 ToolNode 缺少: {sorted(extra_in_bind)}"
                )
            print("\n".join(parts))

    # 3) 检查 bootstrap 中有但无对应 analyst 的 key
    known_bootstrap_keys = set(TOOL_KEY_MAP.values())
    for bkey in bootstrap_tools:
        if bkey not in known_bootstrap_keys:
            print(f"INFO: bootstrap 中有额外 ToolNode key={bkey!r}（无对应 analyst）")

    return 1 if has_mismatch else 0


if __name__ == "__main__":
    sys.exit(main())
