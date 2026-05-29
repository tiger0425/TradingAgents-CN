import logging
from typing import Dict, List, Optional, Set

from langgraph.graph import END, START, StateGraph

from ..agents import (
    create_market_analyst, create_fundamentals_analyst,
    create_news_analyst, create_social_media_analyst,
    create_bull_researcher, create_bear_researcher,
    create_research_manager, create_trader,
    create_aggressive_debator, create_conservative_debator,
    create_neutral_debator, create_portfolio_manager,
    create_msg_delete,
)
from ..agents.utils.agent_states import AgentState
from .conditional_logic import ConditionalLogic

logger = logging.getLogger(__name__)

DEEP_LLM_AGENTS = {"research_manager", "portfolio_manager"}

TOOL_KEY_MAP = {
    "market_analyst": "market",
    "fundamentals_analyst": "fundamentals",
    "news_analyst": "news",
    "social_analyst": "social",
    "macro_analyst": "market",
}


ANALYST_AGENTS = {
    "market_analyst", "fundamentals_analyst", "news_analyst",
    "social_analyst", "macro_analyst",
}


class DynamicGraphBuilder:
    def __init__(self, quick_thinking_llm, deep_thinking_llm, tool_nodes,
                 max_debate_rounds=2, max_risk_rounds=2, fan_out_enabled=False):
        self.quick_llm = quick_thinking_llm
        self.deep_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.conditional = ConditionalLogic(max_debate_rounds, max_risk_rounds)
        self.fan_out_enabled = fan_out_enabled

    def build(self, plan: dict, fan_out_enabled: Optional[bool] = None, checkpointer=None):
        fan_out_enabled = fan_out_enabled if fan_out_enabled is not None else self.fan_out_enabled
        workflow_steps = plan.get("workflow", [])
        if not workflow_steps:
            raise ValueError("Workflow plan has no steps")

        graph = StateGraph(AgentState)
        node_names: Dict[int, str] = {}
        tool_keys_used = set()

        for step in workflow_steps:
            agent_id = step.get("agent", "")
            if agent_id not in self._known_agents():
                logger.warning("Unknown agent: %s, skipping", agent_id)
                continue

            llm = self.deep_llm if agent_id in DEEP_LLM_AGENTS else self.quick_llm
            factory = self._agent_factory(agent_id)
            node_name = f"step{step['step']}_{agent_id}"
            graph.add_node(node_name, factory(llm))
            node_names[step["step"]] = node_name

            tool_key = TOOL_KEY_MAP.get(agent_id)
            if tool_key and tool_key in self.tool_nodes:
                tool_node_name = f"tools_{agent_id}_{step['step']}"
                clear_node_name = f"clear_{agent_id}_{step['step']}"
                graph.add_node(tool_node_name, self.tool_nodes[tool_key])
                graph.add_node(clear_node_name, create_msg_delete())
                tool_keys_used.add(agent_id)
                setattr(self, f"_tool_node_{agent_id}_{step['step']}", tool_node_name)
                setattr(self, f"_clear_node_{agent_id}_{step['step']}", clear_node_name)
                setattr(self, f"_analyst_node_{agent_id}_{step['step']}", node_name)

        # --- 分析师组顺序执行链（代替 Send 并行避免 state 冲突） ---
        parallel_steps: Set[int] = set()
        parallel_meta: Dict[int, str] = {}
        if fan_out_enabled:
            groups = self._detect_parallel_analyst_groups(workflow_steps)
            prev_end_node: str = ""  # node that precedes the current group
            for gidx, group in enumerate(groups):
                merge_name = f"merge_analysts_g{gidx}"
                graph.add_node(merge_name, self._make_merge_node())

                # Chain analysts sequentially: prev → analyst1 → ... → analystN → merge
                chain_prev: str = prev_end_node if gidx > 0 else START
                for step in group:
                    snum = step["step"]
                    analyst_node_name = f"step{snum}_{step['agent']}"
                    graph.add_edge(chain_prev, analyst_node_name)
                    chain_prev = analyst_node_name
                    parallel_steps.add(snum)
                    parallel_meta[snum] = merge_name
                graph.add_edge(chain_prev, merge_name)
                prev_end_node = merge_name

            # After the last parallel group, wire merge → next step
            if groups:
                last_merge = f"merge_analysts_g{len(groups) - 1}"
                last_group_step_nums = {s["step"] for s in groups[-1]}
                max_parallel_step = max(last_group_step_nums) if last_group_step_nums else -1
                next_steps = [s for s in workflow_steps if s["step"] > max_parallel_step
                              and s.get("agent", "") != ""]
                if next_steps:
                    next_snum = next_steps[0]["step"]
                    if next_snum in node_names:
                        graph.add_edge(last_merge, node_names[next_snum])
                logger.info("Groups: %d sequential chains, %d analyst steps", len(groups), len(parallel_steps))

        # --- 辩论/风控辩论组检测 ---
        has_debate = self._detect_debate_group(workflow_steps)
        has_risk_debate = self._detect_risk_debate_group(workflow_steps)
        skip_depends_agents = set()
        if has_debate:
            skip_depends_agents.update({"bear_researcher", "research_manager"})
        if has_risk_debate:
            skip_depends_agents.update({"risk_conservative", "risk_neutral", "portfolio_manager"})

        for step in workflow_steps:
            agent_id = step.get("agent", "")
            snum = step["step"]

            if agent_id not in node_names.values() and agent_id not in self._known_agents():
                continue

            target_node = self._resolve_node(step, node_names)

            # --- FIX-1: 并行组步骤 → 跳过普通边，路由到 Merge 节点 ---
            if snum in parallel_steps:
                merge_name = parallel_meta[snum]
                tool_key = TOOL_KEY_MAP.get(agent_id)
                if tool_key and tool_key in self.tool_nodes and agent_id in tool_keys_used:
                    analyst_node = getattr(self, f"_analyst_node_{agent_id}_{snum}")
                    clear_node = getattr(self, f"_clear_node_{agent_id}_{snum}")
                    tool_node = getattr(self, f"_tool_node_{agent_id}_{snum}")
                    condition_map = {
                        "market_analyst": "should_continue_market",
                        "fundamentals_analyst": "should_continue_fundamentals",
                        "news_analyst": "should_continue_news",
                        "social_analyst": "should_continue_social",
                        "macro_analyst": "should_continue_market",
                    }
                    cond_method = condition_map.get(agent_id)
                    if cond_method:
                        tool_key, clear_key = self._tool_route_keys(agent_id)
                        graph.add_conditional_edges(
                            analyst_node,
                            getattr(self.conditional, cond_method),
                            {tool_key: tool_node, clear_key: merge_name, "continue": analyst_node},
                        )
                        graph.add_edge(tool_node, analyst_node)
                else:
                    graph.add_edge(node_names[snum], merge_name)
                continue

            if not step.get("depends_on"):
                start_node = node_names[step["step"]]
                tool_key = TOOL_KEY_MAP.get(agent_id)
                if tool_key and tool_key in self.tool_nodes and agent_id in tool_keys_used:
                    self._add_tool_cycle(graph, agent_id, step["step"])
                graph.add_edge(START, start_node)

            for dep_num in step.get("depends_on", []):
                # 辩论/风控辩论组：跳过 depends_on 边，由条件边接管路由
                if agent_id in skip_depends_agents:
                    continue
                if dep_num in node_names:
                    prev_agent = next((s.get("agent", "") for s in workflow_steps if s["step"] == dep_num), "")
                    prev_tool_key = TOOL_KEY_MAP.get(prev_agent)
                    if prev_tool_key and prev_tool_key in self.tool_nodes and prev_agent in tool_keys_used:
                        graph.add_edge(
                            getattr(self, f"_clear_node_{prev_agent}_{dep_num}"),
                            node_names[step["step"]]
                        )
                    else:
                        graph.add_edge(node_names[dep_num], node_names[step["step"]])

        # --- 辩论条件边 ---
        if has_debate:
            self._add_debate_cycle(graph, workflow_steps, node_names)
        if has_risk_debate:
            self._add_risk_debate_cycle(graph, workflow_steps, node_names)

        last_step = workflow_steps[-1]
        last_agent = last_step.get("agent", "")
        last_tool_key = TOOL_KEY_MAP.get(last_agent)
        if last_tool_key and last_tool_key in self.tool_nodes and last_agent in tool_keys_used:
            graph.add_edge(
                getattr(self, f"_clear_node_{last_agent}_{last_step['step']}"),
                END
            )
        elif last_step["step"] in node_names:
            graph.add_edge(node_names[last_step["step"]], END)

        logger.info("Dynamic graph built: %d nodes", len(node_names) + len(tool_keys_used) * 2)
        if checkpointer:
            return graph.compile(checkpointer=checkpointer)
        return graph.compile()

    @staticmethod
    def _tool_route_keys(agent_id):
        """Return (tool_route_key, clear_route_key) matching ConditionalLogic return values."""
        mapping = {
            "market_analyst": ("tools_market", "Msg Clear Market"),
            "fundamentals_analyst": ("tools_fundamentals", "Msg Clear Fundamentals"),
            "news_analyst": ("tools_news", "Msg Clear News"),
            "social_analyst": ("tools_social", "Msg Clear Social"),
            "macro_analyst": ("tools_market", "Msg Clear Market"),
        }
        return mapping.get(agent_id, ("", ""))

    def _add_tool_cycle(self, graph, agent_id, step_num):
        analyst_node = getattr(self, f"_analyst_node_{agent_id}_{step_num}")
        tool_node = getattr(self, f"_tool_node_{agent_id}_{step_num}")
        clear_node = getattr(self, f"_clear_node_{agent_id}_{step_num}")

        condition_map = {
            "market_analyst": "should_continue_market",
            "fundamentals_analyst": "should_continue_fundamentals",
            "news_analyst": "should_continue_news",
            "social_analyst": "should_continue_social",
            "macro_analyst": "should_continue_market",
        }
        condition_method = condition_map.get(agent_id)
        if condition_method:
            tool_key, clear_key = self._tool_route_keys(agent_id)
            graph.add_conditional_edges(
                analyst_node,
                getattr(self.conditional, condition_method),
                {tool_key: tool_node, clear_key: clear_node, "continue": analyst_node},
            )
            graph.add_edge(tool_node, analyst_node)

    @staticmethod
    def _detect_debate_group(workflow_steps):
        required = {"bull_researcher", "bear_researcher", "research_manager"}
        agents = {s.get("agent", "") for s in workflow_steps}
        return required.issubset(agents)

    @staticmethod
    def _detect_risk_debate_group(workflow_steps):
        required = {"risk_aggressive", "risk_conservative", "risk_neutral", "portfolio_manager"}
        agents = {s.get("agent", "") for s in workflow_steps}
        return required.issubset(agents)

    def _add_debate_cycle(self, graph, workflow_steps, node_names):
        bull_step = next(s for s in workflow_steps if s["agent"] == "bull_researcher")
        bear_step = next(s for s in workflow_steps if s["agent"] == "bear_researcher")
        rm_step = next(s for s in workflow_steps if s["agent"] == "research_manager")

        bull_node = node_names[bull_step["step"]]
        bear_node = node_names[bear_step["step"]]
        rm_node = node_names[rm_step["step"]]

        graph.add_conditional_edges(
            bull_node,
            self.conditional.should_continue_debate,
            {"Bear Researcher": bear_node, "Research Manager": rm_node},
        )
        graph.add_conditional_edges(
            bear_node,
            self.conditional.should_continue_debate,
            {"Bull Researcher": bull_node, "Research Manager": rm_node},
        )
        logger.info("Debate cycle added: Bull ↔ Bear (%d rounds max)",
                     self.conditional.max_debate_rounds)

    def _add_risk_debate_cycle(self, graph, workflow_steps, node_names):
        agg_step = next(s for s in workflow_steps if s["agent"] == "risk_aggressive")
        con_step = next(s for s in workflow_steps if s["agent"] == "risk_conservative")
        neu_step = next(s for s in workflow_steps if s["agent"] == "risk_neutral")
        pm_step = next(s for s in workflow_steps if s["agent"] == "portfolio_manager")

        agg_node = node_names[agg_step["step"]]
        con_node = node_names[con_step["step"]]
        neu_node = node_names[neu_step["step"]]
        pm_node = node_names[pm_step["step"]]

        graph.add_conditional_edges(
            agg_node,
            self.conditional.should_continue_risk_analysis,
            {"Conservative Analyst": con_node, "Portfolio Manager": pm_node},
        )
        graph.add_conditional_edges(
            con_node,
            self.conditional.should_continue_risk_analysis,
            {"Neutral Analyst": neu_node, "Portfolio Manager": pm_node},
        )
        graph.add_conditional_edges(
            neu_node,
            self.conditional.should_continue_risk_analysis,
            {"Aggressive Analyst": agg_node, "Portfolio Manager": pm_node},
        )
        logger.info("Risk debate cycle added: Aggressive ↔ Conservative ↔ Neutral (%d rounds max)",
                     self.conditional.max_risk_discuss_rounds)

    def _resolve_node(self, step, node_names):
        return node_names.get(step["step"], "")

    def _known_agents(self):
        return {
            "market_analyst", "fundamentals_analyst", "news_analyst",
            "social_analyst", "macro_analyst", "bull_researcher",
            "bear_researcher", "research_manager", "trader",
            "risk_aggressive", "risk_conservative", "risk_neutral",
            "portfolio_manager",
        }

    @staticmethod
    def _agent_factory(agent_id):
        mapping = {
            "market_analyst": create_market_analyst,
            "fundamentals_analyst": create_fundamentals_analyst,
            "news_analyst": create_news_analyst,
            "social_analyst": create_social_media_analyst,
            "macro_analyst": create_market_analyst,
            "bull_researcher": create_bull_researcher,
            "bear_researcher": create_bear_researcher,
            "research_manager": create_research_manager,
            "trader": create_trader,
            "risk_aggressive": create_aggressive_debator,
            "risk_conservative": create_conservative_debator,
            "risk_neutral": create_neutral_debator,
            "portfolio_manager": create_portfolio_manager,
        }
        return mapping[agent_id]

    # ------------------------------------------------------------------
    # FIX-1: 并行分析师检测与扇出节点工厂
    # ------------------------------------------------------------------

    # Agents whose outputs write to the same state key (can't run in parallel)
    _ANALYST_STATE_KEY_MAP = {
        "market_analyst": "market_report",
        "macro_analyst": "market_report",         # same factory → same key
        "fundamentals_analyst": "fundamentals_report",
        "news_analyst": "news_report",
        "social_analyst": "sentiment_report",
    }

    @staticmethod
    def _detect_parallel_analyst_groups(workflow_steps):
        """Find groups of contiguous independent analyst steps.

        Returns a list of groups (each group is a list of steps). Steps in
        the same group have no `depends_on` and belong to ANALYST_AGENTS.
        A group ends when a non-analyst step or a step with `depends_on` is
        encountered.

        Agents writing to the same state key are never grouped together
        (LangGraph Send parallel execution can't write to the same key).
        """
        key_map = DynamicGraphBuilder._ANALYST_STATE_KEY_MAP
        groups = []
        current_group = []
        for step in workflow_steps:
            agent = step.get("agent", "")
            if agent in ANALYST_AGENTS and not step.get("depends_on"):
                # Flush group if this agent shares a state key with any existing member
                agent_key = key_map.get(agent)
                if agent_key and any(key_map.get(m.get("agent", "")) == agent_key for m in current_group):
                    if len(current_group) >= 2:
                        groups.append(current_group)
                    current_group = []
                current_group.append(step)
            else:
                if len(current_group) >= 2:
                    groups.append(current_group)
                current_group = []
        if len(current_group) >= 2:
            groups.append(current_group)
        return groups

    @staticmethod
    def _make_merge_node():
        """Create a merge/sync barrier node after parallel analysts complete."""
        def merge(state: AgentState):
            return state
        return merge
