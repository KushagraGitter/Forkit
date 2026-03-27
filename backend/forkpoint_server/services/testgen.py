"""
Failure → test case pipeline (Layer 5).

Every production failure automatically generates a reproducible pytest test
with all tool calls stubbed and LLM responses recorded.
This is the killer feature for teams moving agents to production.
"""

from __future__ import annotations

import json
import sys
import os
from datetime import datetime, timezone
from textwrap import dedent, indent
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../sdk"))
from forkpoint.models.events import GeneratedTestCase, NodeType, Snapshot


async def generate_test_case(run_id: str, snapshots: list[Snapshot]) -> GeneratedTestCase:
    """
    Generate a self-contained pytest test case from a run's snapshot history.
    All tool calls and LLM responses are stubbed with recorded values.
    """
    tool_stubs: dict[str, list[Any]] = {}
    llm_stubs: dict[str, list[str]] = {}
    failure_summary = _extract_failure_summary(snapshots)
    num_tool_stubs = 0
    num_llm_stubs = 0

    for snap in snapshots:
        for tc, tr in zip(snap.tool_calls, snap.tool_results):
            stub = {
                "tool_call_id": tc.id,
                "arguments": tc.arguments,
                "result": tr.result,
                "error": tr.error,
            }
            tool_stubs.setdefault(tc.name, []).append(stub)
            num_tool_stubs += 1

        if snap.messages_out and snap.model:
            msg = snap.messages_out[0]
            content = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
            llm_stubs.setdefault(snap.model, []).append(content)
            num_llm_stubs += 1

    # Build input state from first snapshot
    initial_state: dict[str, Any] = {}
    initial_messages: list[dict] = []
    if snapshots:
        first = snapshots[0]
        initial_state = first.agent_state
        initial_messages = [m.model_dump() for m in first.messages_in]

    test_source = _render_test_file(
        run_id=run_id,
        tool_stubs=tool_stubs,
        llm_stubs=llm_stubs,
        initial_state=initial_state,
        initial_messages=initial_messages,
        failure_summary=failure_summary,
        snapshots=snapshots,
    )

    return GeneratedTestCase(
        run_id=run_id,
        test_file_content=test_source,
        num_tool_stubs=num_tool_stubs,
        num_llm_stubs=num_llm_stubs,
        failure_summary=failure_summary,
    )


def _extract_failure_summary(snapshots: list[Snapshot]) -> str:
    for snap in reversed(snapshots):
        if snap.node_type == NodeType.AGENT_END:
            return "Agent ended (see snapshot for error details)"
        if snap.tool_results:
            for tr in snap.tool_results:
                if tr.error:
                    return f"Tool {tr.name!r} failed: {tr.error}"
    return "Run failed (no specific error captured)"


def _render_test_file(
    run_id: str,
    tool_stubs: dict[str, list[Any]],
    llm_stubs: dict[str, list[str]],
    initial_state: dict[str, Any],
    initial_messages: list[dict],
    failure_summary: str,
    snapshots: list[Snapshot],
) -> str:
    tool_stubs_json = json.dumps(tool_stubs, indent=4, default=str)
    llm_stubs_json = json.dumps(llm_stubs, indent=4, default=str)
    state_json = json.dumps(initial_state, indent=4, default=str)
    messages_json = json.dumps(initial_messages, indent=4, default=str)
    generated_at = datetime.now(timezone.utc).isoformat()

    # Build assertion hints from the final snapshot
    last_snap = snapshots[-1] if snapshots else None
    assertion_hint = ""
    if last_snap and last_snap.messages_out:
        content = last_snap.messages_out[0].content
        if isinstance(content, str) and content:
            short = content[:100].replace('"', '\\"')
            assertion_hint = f'    # Example: assert "{short}" in result.get("output", "")'

    return dedent(f'''\
        """
        Auto-generated Forkpoint test case.
        Run ID: {run_id}
        Failure: {failure_summary}
        Generated: {generated_at}

        All LLM calls and tool calls are stubbed with recorded production values.
        Re-run this test to reproduce the exact failure, then fix the agent.
        """

        import pytest
        import json
        from unittest.mock import AsyncMock, MagicMock, patch


        # ---------------------------------------------------------------------------
        # Recorded stubs — exact values from production run {run_id}
        # ---------------------------------------------------------------------------

        TOOL_STUBS = {tool_stubs_json}

        LLM_STUBS = {llm_stubs_json}

        INITIAL_STATE = {state_json}

        INITIAL_MESSAGES = {messages_json}


        # ---------------------------------------------------------------------------
        # Fixtures
        # ---------------------------------------------------------------------------


        @pytest.fixture
        def tool_stub_factory():
            """Returns a mock tool that replays recorded responses in order."""
            queues = {{name: list(stubs) for name, stubs in TOOL_STUBS.items()}}

            def make_tool(name: str):
                def _tool(**kwargs):
                    stub_list = queues.get(name, [])
                    if not stub_list:
                        raise ValueError(f"No more stubs for tool {{name!r}}")
                    stub = stub_list.pop(0)
                    if stub.get("error"):
                        raise RuntimeError(stub["error"])
                    return stub["result"]
                return MagicMock(side_effect=_tool)

            return make_tool


        @pytest.fixture
        def llm_stub_factory():
            """Returns a mock LLM that replays recorded responses in order."""
            queues = {{model: list(resps) for model, resps in LLM_STUBS.items()}}

            def make_llm(model: str):
                resp_list = queues.get(model, [])

                async def _acomplete(*args, **kwargs):
                    if not resp_list:
                        raise ValueError(f"No more LLM stubs for model {{model!r}}")
                    return resp_list.pop(0)

                return AsyncMock(side_effect=_acomplete)

            return make_llm


        # ---------------------------------------------------------------------------
        # Reproduced failure test
        # ---------------------------------------------------------------------------


        @pytest.mark.asyncio
        async def test_reproduced_failure_{run_id[:8]}(tool_stub_factory, llm_stub_factory):
            """
            Reproduces failure: {failure_summary}

            To fix this test:
            1. Run it and observe the failure.
            2. Edit the agent code to handle this case.
            3. The test should pass once the fix is correct.
            4. Add to your CI pipeline so this regression never recurs.
            """
            # TODO: Replace with your actual agent import
            # from my_agent import run_agent

            initial_input = {{
                "messages": INITIAL_MESSAGES,
                "state": INITIAL_STATE,
            }}

            # Wire up your tools with stubs
            # tools = {{
            #     name: tool_stub_factory(name) for name in TOOL_STUBS
            # }}

            # Wire up your LLM with stubs
            # llm = llm_stub_factory("your-model-name")

            # Run the agent
            # result = await run_agent(initial_input, tools=tools, llm=llm)

            # Assert expected behavior
            # assert result is not None
{assertion_hint}

            pytest.skip(
                "Replace the commented-out code above with your agent import and invocation. "
                "This test was auto-generated by Forkpoint from run {run_id}."
            )
    ''')
