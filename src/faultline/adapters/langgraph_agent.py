"""Real LangGraph StateGraph adapter implementing a multi-step research agent."""

from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from faultline.adapters.base import AgentAdapter, ToolHandler, default_mock_tool_handler
from faultline.schemas.adapter import (
    AgentExecutionOutput,
    AgentStep,
    AgentTaskInput,
    ExecutionStatus,
    ToolCallRequest,
)


class ResearchGraphState(TypedDict):
    """Typed state dictionary flowing through the LangGraph StateGraph nodes."""

    task_prompt: str
    model_name: str
    planned_calls: list[ToolCallRequest]
    cursor: int
    steps: list[AgentStep]
    collected_evidence: list[str]
    max_steps: int
    allow_fallback: bool
    tokens_per_step: int
    model_latency_ms: float
    status: ExecutionStatus
    final_answer: str | None
    error_message: str | None


class LangGraphResearchAdapter(AgentAdapter):
    """LangGraph StateGraph adapter for testing multi-step research agent workflows."""

    adapter_type = "langgraph"

    async def execute(
        self,
        *,
        model_name: str,
        config_payload: dict[str, Any],
        task_input: AgentTaskInput,
        tool_handler: ToolHandler | None = None,
    ) -> AgentExecutionOutput:
        """Compile and invoke a LangGraph StateGraph for the given research task."""
        active_handler = tool_handler or default_mock_tool_handler
        allow_fallback = bool(config_payload.get(
            "fallback_on_tool_error", False))
        tokens_per_step = int(config_payload.get("tokens_per_step", 35))
        model_latency_ms = float(config_payload.get("model_latency_ms", 15.0))
        auto_plan = bool(config_payload.get("auto_plan_research_tools", False))

        planned_calls = self._resolve_research_plan(
            task_input=task_input,
            auto_plan=auto_plan,
        )

        async def planner_node(state: ResearchGraphState) -> dict[str, Any]:
            steps = list(state["steps"])
            cursor = state["cursor"]
            calls = state["planned_calls"]

            if cursor >= len(calls):
                return {}

            if len(steps) >= state["max_steps"]:
                return {
                    "status": "max_steps_exceeded",
                    "error_message": (
                        f"LangGraph execution exceeded max_steps limit ({state['max_steps']})."
                    ),
                }

            next_call = calls[cursor]
            steps.append(
                AgentStep(
                    step_index=len(steps),
                    step_type="model_invocation",
                    name=state["model_name"],
                    status="ok",
                    input_payload={
                        "graph_node": "planner",
                        "cursor": cursor,
                        "task_prompt": state["task_prompt"][:120],
                    },
                    output_payload={
                        "decision": "route_to_tool_executor",
                        "call_id": next_call.call_id,
                        "tool_name": next_call.tool_name,
                    },
                    latency_ms=state["model_latency_ms"],
                    tokens_used=state["tokens_per_step"],
                )
            )
            return {"steps": steps}

        async def tool_executor_node(state: ResearchGraphState) -> dict[str, Any]:
            steps = list(state["steps"])
            evidence = list(state["collected_evidence"])
            cursor = state["cursor"]
            tool_request = state["planned_calls"][cursor]

            if len(steps) >= state["max_steps"]:
                return {
                    "status": "max_steps_exceeded",
                    "error_message": (
                        f"LangGraph execution exceeded max_steps limit ({state['max_steps']})."
                    ),
                }

            tool_result = await active_handler(tool_request)
            effective_tool = tool_result.tool_name or tool_request.tool_name
            step_status: Literal["ok", "error"] = (
                "ok" if tool_result.status == "success" else "error"
            )

            steps.append(
                AgentStep(
                    step_index=len(steps),
                    step_type="tool_call",
                    name=effective_tool,
                    status=step_status,
                    input_payload={
                        "graph_node": "tool_executor",
                        "call_id": tool_request.call_id,
                        "arguments": tool_request.arguments,
                    },
                    output_payload=tool_result.model_dump(mode="json"),
                    latency_ms=tool_result.latency_ms,
                    tokens_used=0,
                )
            )

            if tool_result.status == "error":
                if not state["allow_fallback"]:
                    return {
                        "steps": steps,
                        "cursor": cursor + 1,
                        "status": "failed",
                        "error_message": (
                            f"LangGraph tool node '{effective_tool}' failed with "
                            f"{tool_result.error_type or 'ToolError'}: "
                            f"{tool_result.error_message or 'Unknown error'}"
                        ),
                    }
                evidence.append(
                    f"[fallback:{effective_tool}={tool_result.error_type}]"
                )
            else:
                evidence.append(f"[ok:{effective_tool}]")

            return {
                "steps": steps,
                "cursor": cursor + 1,
                "collected_evidence": evidence,
            }

        async def synthesizer_node(state: ResearchGraphState) -> dict[str, Any]:
            steps = list(state["steps"])
            evidence = state["collected_evidence"]

            if len(steps) >= state["max_steps"]:
                return {
                    "status": "max_steps_exceeded",
                    "error_message": (
                        f"LangGraph execution exceeded max_steps limit ({state['max_steps']})."
                    ),
                }

            evidence_str = " ".join(evidence) if evidence else "[no-tools]"
            final_answer = (
                f"LangGraph research synthesis for '{state['task_prompt']}': {evidence_str}"
            )

            steps.append(
                AgentStep(
                    step_index=len(steps),
                    step_type="final_response",
                    name=state["model_name"],
                    status="ok",
                    input_payload={
                        "graph_node": "synthesizer",
                        "evidence_count": len(evidence),
                    },
                    output_payload={"final_answer": final_answer},
                    latency_ms=state["model_latency_ms"],
                    tokens_used=state["tokens_per_step"],
                )
            )
            return {
                "steps": steps,
                "status": "completed",
                "final_answer": final_answer,
            }

        def route_after_planner(
            state: ResearchGraphState,
        ) -> Literal["tool_executor", "synthesizer", "__end__"]:
            if state["status"] in ("failed", "max_steps_exceeded"):
                return "__end__"
            if state["cursor"] < len(state["planned_calls"]):
                return "tool_executor"
            return "synthesizer"

        def route_after_tool(
            state: ResearchGraphState,
        ) -> Literal["planner", "__end__"]:
            if state["status"] in ("failed", "max_steps_exceeded"):
                return "__end__"
            return "planner"

        workflow: StateGraph[Any] = StateGraph(ResearchGraphState)
        workflow.add_node("planner", planner_node)
        workflow.add_node("tool_executor", tool_executor_node)
        workflow.add_node("synthesizer", synthesizer_node)

        workflow.add_edge(START, "planner")
        workflow.add_conditional_edges("planner", route_after_planner)
        workflow.add_conditional_edges("tool_executor", route_after_tool)
        workflow.add_edge("synthesizer", END)

        compiled_graph = workflow.compile()

        initial_state: ResearchGraphState = {
            "task_prompt": task_input.task_prompt,
            "model_name": model_name,
            "planned_calls": planned_calls,
            "cursor": 0,
            "steps": [],
            "collected_evidence": [],
            "max_steps": task_input.max_steps,
            "allow_fallback": allow_fallback,
            "tokens_per_step": tokens_per_step,
            "model_latency_ms": model_latency_ms,
            "status": "completed",
            "final_answer": None,
            "error_message": None,
        }

        final_state: dict[str, Any] = await compiled_graph.ainvoke(initial_state)
        final_steps: list[AgentStep] = final_state["steps"]
        total_tokens = sum(s.tokens_used for s in final_steps)
        total_latency_ms = sum(s.latency_ms for s in final_steps)

        return AgentExecutionOutput(
            adapter_type=self.adapter_type,
            model_name=model_name,
            status=final_state["status"],
            final_answer=final_state["final_answer"],
            steps=final_steps,
            total_tokens=total_tokens,
            total_latency_ms=total_latency_ms,
            error_message=final_state["error_message"],
        )

    def _resolve_research_plan(
        self,
        *,
        task_input: AgentTaskInput,
        auto_plan: bool,
    ) -> list[ToolCallRequest]:
        if task_input.planned_tool_calls:
            return list(task_input.planned_tool_calls)
        if auto_plan:
            return [
                ToolCallRequest(
                    call_id="lg-search-1",
                    tool_name="search_web",
                    arguments={"query": task_input.task_prompt[:80]},
                ),
                ToolCallRequest(
                    call_id="lg-retrieve-1",
                    tool_name="retrieve_docs",
                    arguments={"topic": task_input.task_prompt[:80]},
                ),
            ]
        return []
