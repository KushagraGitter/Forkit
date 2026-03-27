"""
Example: Instrument a LangGraph agent with Forkpoint.

Run with: python examples/langgraph_example.py
Then open http://localhost:5173 to see the execution graph.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../sdk"))

from forkpoint import ForkpointTracer
from forkpoint.integrations.raw import AgentNode
from forkpoint.models.events import Message, MessageRole, TokenCounts


def simulate_llm_call(messages: list[Message], model: str) -> Message:
    """Fake LLM call for demo purposes."""
    last = messages[-1].content if messages else ""
    return Message(
        role=MessageRole.ASSISTANT,
        content=f"[{model}] Processed: {str(last)[:80]}",
    )


def simulate_tool_call(tool_name: str, args: dict) -> str:
    """Fake tool call for demo purposes."""
    return f"Tool {tool_name!r} returned result for {args}"


def run_demo_agent():
    """
    Simulates a multi-agent pipeline:
    1. Planner agent — breaks down the task
    2. Researcher agent — gathers information
    3. Writer agent — synthesizes the output
    """
    print("Starting demo Forkpoint run...")

    with ForkpointTracer(
        agent_id="demo-pipeline",
        tags={"env": "demo", "version": "1"},
        metadata={"description": "Demo multi-agent pipeline"},
    ) as tracer:

        # --- Planner node ---
        with AgentNode(tracer, node_id="planner") as node:
            node.update_state({"phase": "planning", "task": "Write a report on AI agents"})
            tracer.on_agent_start("planner", {"phase": "planning"})

            msgs = [
                Message(role=MessageRole.SYSTEM, content="You are a planning agent."),
                Message(role=MessageRole.USER, content="Write a report on AI agents"),
            ]
            call_id = node.llm_start(msgs, model="gpt-4o")
            response = simulate_llm_call(msgs, "gpt-4o")
            node.llm_end(call_id, response, token_counts=TokenCounts(prompt_tokens=50, completion_tokens=100, total_tokens=150))

        # --- Researcher node ---
        with AgentNode(tracer, node_id="researcher") as node:
            node.update_state({"phase": "research"})

            # Tool call: web search
            tool_id = node.tool_start("search_web", {"query": "latest AI agent frameworks 2024"})
            search_result = simulate_tool_call("search_web", {"query": "AI agents"})
            node.tool_end(tool_id, result=search_result)

            # Tool call: fetch page
            tool_id2 = node.tool_start("fetch_page", {"url": "https://example.com/ai-agents"})
            page_result = simulate_tool_call("fetch_page", {"url": "example.com"})
            node.tool_end(tool_id2, result=page_result)

            msgs2 = [
                Message(role=MessageRole.SYSTEM, content="You are a research agent."),
                Message(role=MessageRole.USER, content="Summarize findings about AI agents"),
                Message(role=MessageRole.TOOL, content=search_result),
            ]
            call_id2 = node.llm_start(msgs2, model="gpt-4o")
            response2 = simulate_llm_call(msgs2, "gpt-4o")
            node.llm_end(call_id2, response2, token_counts=TokenCounts(prompt_tokens=200, completion_tokens=150, total_tokens=350))

        # --- Writer node ---
        with AgentNode(tracer, node_id="writer") as node:
            node.update_state({"phase": "writing"})

            msgs3 = [
                Message(role=MessageRole.SYSTEM, content="You are a writing agent."),
                Message(role=MessageRole.USER, content="Write the final report"),
                Message(role=MessageRole.ASSISTANT, content=str(response2.content)),
            ]
            call_id3 = node.llm_start(msgs3, model="gpt-4o")
            response3 = simulate_llm_call(msgs3, "gpt-4o")
            node.llm_end(call_id3, response3, token_counts=TokenCounts(prompt_tokens=400, completion_tokens=500, total_tokens=900))

            tracer.on_agent_end("writer", {"phase": "done", "output": str(response3.content)})

    print(f"\nRun complete!")
    print(f"  Run ID : {tracer.run_id}")
    print(f"  Status : {tracer.run.status.value}")
    print(f"  Snapshots: {len(tracer.snapshots)}")
    print(f"\nReplay bundle ready. To view in the UI:")
    print(f"  1. Start the backend: cd backend && uvicorn forkpoint_server.main:app")
    print(f"  2. Start the frontend: cd frontend && npm run dev")
    print(f"  3. Open http://localhost:5173")

    # Demonstrate fork
    if tracer.snapshots:
        fork_point = tracer.snapshots[0].id
        print(f"\nForking from snapshot {fork_point[:12]}...")
        from forkpoint.models.events import StatePatch
        child = tracer.fork(
            fork_point,
            patch=StatePatch(state_overrides={"task": "Rewrite report with different angle"}),
            reason="Testing alternative task framing",
        )
        print(f"  Forked run ID: {child.run_id}")
        print(f"  Parent run ID: {child.run.parent_run_id}")


if __name__ == "__main__":
    run_demo_agent()
