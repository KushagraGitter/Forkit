"""
Raw integration — manual instrumentation via context managers and decorators.
No framework required. Use this for custom agent loops.

Usage::

    from forkpoint.integrations.raw import AgentNode, ToolNode

    with ForkpointTracer(agent_id="my-pipeline") as tracer:
        with AgentNode(tracer, node_id="planner") as node:
            call_id = node.llm_start(messages, model="gpt-4o")
            response = my_llm_client.complete(messages)
            node.llm_end(call_id, response)

            tool_id = node.tool_start("search", {"query": "..."})
            result = search_tool(...)
            node.tool_end(tool_id, result)
"""

from __future__ import annotations

from typing import Any

from forkpoint.core.tracer import ForkpointTracer
from forkpoint.models.events import Message, TokenCounts


class AgentNode:
    """
    Context manager wrapping one logical agent node in a raw loop.
    Provides a clean API for recording LLM and tool interactions.
    """

    def __init__(self, tracer: ForkpointTracer, node_id: str) -> None:
        self._tracer = tracer
        self._node_id = node_id

    def __enter__(self) -> "AgentNode":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass  # agent lifecycle managed by outer ForkpointTracer

    # ------------------------------------------------------------------
    # LLM
    # ------------------------------------------------------------------

    def llm_start(
        self,
        messages: list[Message],
        model: str,
        params: dict[str, Any] | None = None,
    ) -> str:
        """Returns call_id. Pass to llm_end."""
        return self._tracer.on_llm_start(
            node_id=self._node_id,
            messages=messages,
            model=model,
            params=params,
        )

    def llm_end(
        self,
        call_id: str,
        response: Message,
        token_counts: TokenCounts | None = None,
    ) -> None:
        self._tracer.on_llm_end(
            call_id=call_id,
            response=response,
            token_counts=token_counts,
        )

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def tool_start(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Returns call_id. Pass to tool_end."""
        return self._tracer.on_tool_start(
            node_id=self._node_id,
            tool_name=tool_name,
            tool_input=tool_input,
        )

    def tool_end(self, call_id: str, result: Any, error: Exception | None = None) -> None:
        self._tracer.on_tool_end(call_id=call_id, result=result, error=error)

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def emit_message(self, message: Message) -> None:
        self._tracer.on_agent_message(node_id=self._node_id, message=message)

    def update_state(self, state: dict[str, Any]) -> None:
        self._tracer.update_state(state)
