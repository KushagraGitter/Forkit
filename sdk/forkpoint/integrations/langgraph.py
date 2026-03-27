"""
LangGraph integration.

Wraps a CompiledGraph with a ForkpointTracer via LangChain callback hooks.
One import, one function call — all LLM calls, tool calls, and node transitions
are captured automatically.

Usage::

    from forkpoint.integrations.langgraph import instrument_langgraph
    graph = instrument_langgraph(graph, agent_id="my-pipeline")
    result = graph.invoke({"messages": [...]})
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from forkpoint.models.events import Framework, Message, MessageRole, TokenCounts
from forkpoint.core.tracer import ForkpointTracer
from forkpoint.transports.base import Transport

if TYPE_CHECKING:
    pass


class ForkpointLangGraphCallback:
    """
    LangChain/LangGraph BaseCallbackHandler shim.
    Intercepts every LLM start/end, tool start/end, and chain start/end.
    """

    def __init__(self, tracer: ForkpointTracer) -> None:
        self._tracer = tracer
        self._call_map: dict[str, str] = {}  # langchain run_id -> forkpoint call_id

    # ---------------------------------------------------------------
    # LLM callbacks
    # ---------------------------------------------------------------

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        model = (
            serialized.get("kwargs", {}).get("model_name")
            or serialized.get("kwargs", {}).get("model")
            or serialized.get("id", ["unknown"])[-1]
        )
        messages = [Message(role=MessageRole.USER, content=p) for p in prompts]
        params = {k: v for k, v in (kwargs.get("invocation_params") or {}).items()}
        call_id = self._tracer.on_llm_start(
            node_id=str(run_id),
            messages=messages,
            model=model,
            params=params,
        )
        self._call_map[str(run_id)] = call_id

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        model = (
            serialized.get("kwargs", {}).get("model_name")
            or serialized.get("kwargs", {}).get("model")
            or serialized.get("id", ["unknown"])[-1]
        )
        fp_messages = []
        for batch in messages:
            for msg in batch:
                fp_messages.append(_lc_message_to_fp(msg))

        call_id = self._tracer.on_llm_start(
            node_id=str(run_id),
            messages=fp_messages,
            model=model,
        )
        self._call_map[str(run_id)] = call_id

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        call_id = self._call_map.pop(str(run_id), None)
        if call_id is None:
            return
        # Extract response text
        try:
            gen = response.generations[0][0]
            text = getattr(gen, "text", None) or getattr(gen.message, "content", "")
            token_counts = None
            if hasattr(response, "llm_output") and response.llm_output:
                usage = response.llm_output.get("token_usage") or response.llm_output.get("usage", {})
                if usage:
                    token_counts = TokenCounts(
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        total_tokens=usage.get("total_tokens", 0),
                    )
        except (AttributeError, IndexError):
            text = str(response)
            token_counts = None

        self._tracer.on_llm_end(
            call_id=call_id,
            response=Message(role=MessageRole.ASSISTANT, content=text),
            token_counts=token_counts,
        )

    # ---------------------------------------------------------------
    # Tool callbacks
    # ---------------------------------------------------------------

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "unknown_tool")
        try:
            import json
            tool_input = json.loads(input_str)
        except Exception:
            tool_input = {"input": input_str}

        call_id = self._tracer.on_tool_start(
            node_id=str(run_id),
            tool_name=tool_name,
            tool_input=tool_input,
        )
        self._call_map[str(run_id)] = call_id

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        call_id = self._call_map.pop(str(run_id), None)
        if call_id is None:
            return
        self._tracer.on_tool_end(call_id=call_id, result=output)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        call_id = self._call_map.pop(str(run_id), None)
        if call_id is None:
            return
        self._tracer.on_tool_end(call_id=call_id, result=None, error=error)

    # ---------------------------------------------------------------
    # Chain callbacks (captures LangGraph node transitions)
    # ---------------------------------------------------------------

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        node_name = serialized.get("id", ["unknown"])[-1]
        # Only capture top-level chain starts as agent_start (not sub-chains)
        if parent_run_id is None:
            self._tracer.on_agent_start(node_id=node_name, state=inputs)

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        if parent_run_id is None:
            self._tracer.on_agent_end(node_id=str(run_id), state=outputs)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        if parent_run_id is None:
            self._tracer.on_agent_end(node_id=str(run_id), state={}, error=error)


# ---------------------------------------------------------------------------
# Public instrumentation function
# ---------------------------------------------------------------------------


def instrument_langgraph(
    graph: Any,
    agent_id: str,
    transport: Transport | None = None,
    tags: dict[str, str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> "_InstrumentedGraph":
    """
    Wrap a CompiledGraph so every invocation is traced automatically.

    Returns a thin proxy that passes ForkpointLangGraphCallback in the RunnableConfig.
    """
    tracer = ForkpointTracer(
        agent_id=agent_id,
        framework=Framework.LANGGRAPH,
        transport=transport,
        tags=tags or {},
        metadata=metadata or {},
    )
    return _InstrumentedGraph(graph, tracer)


class _InstrumentedGraph:
    """Proxy that injects the callback into every invoke/stream call."""

    def __init__(self, graph: Any, tracer: ForkpointTracer) -> None:
        self._graph = graph
        self._tracer = tracer

    def invoke(self, input: Any, config: dict | None = None, **kwargs: Any) -> Any:
        merged = self._merge_config(config)
        with self._tracer:
            return self._graph.invoke(input, merged, **kwargs)

    def stream(self, input: Any, config: dict | None = None, **kwargs: Any):
        merged = self._merge_config(config)
        with self._tracer:
            yield from self._graph.stream(input, merged, **kwargs)

    async def ainvoke(self, input: Any, config: dict | None = None, **kwargs: Any) -> Any:
        merged = self._merge_config(config)
        with self._tracer:
            return await self._graph.ainvoke(input, merged, **kwargs)

    def _merge_config(self, config: dict | None) -> dict:
        cb = ForkpointLangGraphCallback(self._tracer)
        base = dict(config or {})
        existing = base.get("callbacks", [])
        base["callbacks"] = [*existing, cb]
        return base

    @property
    def tracer(self) -> ForkpointTracer:
        return self._tracer

    def __getattr__(self, name: str) -> Any:
        return getattr(self._graph, name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lc_message_to_fp(msg: Any) -> Message:
    """Convert a LangChain BaseMessage to a Forkpoint Message."""
    role_map = {
        "human": MessageRole.USER,
        "ai": MessageRole.ASSISTANT,
        "system": MessageRole.SYSTEM,
        "tool": MessageRole.TOOL,
        "function": MessageRole.FUNCTION,
    }
    msg_type = getattr(msg, "type", "user")
    role = role_map.get(msg_type, MessageRole.USER)
    content = getattr(msg, "content", str(msg))
    return Message(role=role, content=content)
