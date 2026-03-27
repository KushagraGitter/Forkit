"""
Causal analysis service (Layer 3).

For each LLM decision node, uses logprobs (when available) or a secondary
LLM summarization call to explain why the agent chose path A over B.
"""

from __future__ import annotations

import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../sdk"))
from forkpoint.models.events import (
    AlternativeDecision,
    CausalAnalysis,
    NodeType,
    Snapshot,
)


async def analyze_causal(snapshot: Snapshot) -> CausalAnalysis:
    """
    Analyze a single decision snapshot and return a CausalAnalysis.

    Priority:
    1. If logprobs are available, use them to rank alternatives.
    2. If OPENAI_API_KEY / ANTHROPIC_API_KEY is set, call a secondary LLM.
    3. Fall back to a heuristic summary.
    """
    alternatives: list[AlternativeDecision] = []
    reasoning = ""
    confidence = 0.5

    if snapshot.logprobs:
        alternatives, reasoning, confidence = _analyze_from_logprobs(snapshot)
    elif os.getenv("ANTHROPIC_API_KEY"):
        alternatives, reasoning, confidence = await _analyze_with_claude(snapshot)
    elif os.getenv("OPENAI_API_KEY"):
        alternatives, reasoning, confidence = await _analyze_with_openai(snapshot)
    else:
        reasoning = _heuristic_summary(snapshot)

    return CausalAnalysis(
        snapshot_id=snapshot.id,
        run_id=snapshot.run_id,
        node_id=snapshot.node_id,
        chosen_path_summary=_chosen_path_summary(snapshot),
        alternatives=alternatives,
        reasoning=reasoning,
        confidence=confidence,
    )


def _chosen_path_summary(snapshot: Snapshot) -> str:
    if snapshot.messages_out:
        content = snapshot.messages_out[0].content
        if isinstance(content, str):
            return content[:200] + ("..." if len(content) > 200 else "")
    if snapshot.tool_calls:
        tc = snapshot.tool_calls[0]
        return f"Called tool: {tc.name}({tc.arguments})"
    return "No output captured"


def _analyze_from_logprobs(
    snapshot: Snapshot,
) -> tuple[list[AlternativeDecision], str, float]:
    """Use logprobs to reconstruct top-k alternative continuations."""
    alternatives: list[AlternativeDecision] = []
    import math

    for entry in (snapshot.logprobs or [])[:5]:
        for alt_token, alt_logprob in (entry.top_logprobs or {}).items():
            if alt_token != entry.token:
                prob = math.exp(alt_logprob)
                alternatives.append(AlternativeDecision(
                    node_id=snapshot.node_id,
                    description=f"Alternative token: {alt_token!r}",
                    probability=prob,
                    logprob_delta=alt_logprob - entry.logprob,
                ))

    reasoning = (
        f"Analyzed {len(snapshot.logprobs or [])} logprob entries. "
        f"Found {len(alternatives)} alternatives at decision points."
    )
    confidence = 0.8 if alternatives else 0.3
    return alternatives, reasoning, confidence


async def _analyze_with_claude(
    snapshot: Snapshot,
) -> tuple[list[AlternativeDecision], str, float]:
    """Use Claude to explain the decision."""
    try:
        import anthropic

        client = anthropic.AsyncAnthropic()
        prompt = _build_analysis_prompt(snapshot)
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        return [], text, 0.7
    except Exception as e:
        return [], f"Claude analysis failed: {e}", 0.0


async def _analyze_with_openai(
    snapshot: Snapshot,
) -> tuple[list[AlternativeDecision], str, float]:
    """Use OpenAI to explain the decision."""
    try:
        import openai

        client = openai.AsyncOpenAI()
        prompt = _build_analysis_prompt(snapshot)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
        )
        text = response.choices[0].message.content or ""
        return [], text, 0.7
    except Exception as e:
        return [], f"OpenAI analysis failed: {e}", 0.0


def _heuristic_summary(snapshot: Snapshot) -> str:
    parts = []
    if snapshot.model:
        parts.append(f"Model: {snapshot.model}")
    if snapshot.messages_in:
        parts.append(f"Input messages: {len(snapshot.messages_in)}")
    if snapshot.tool_calls:
        names = [tc.name for tc in snapshot.tool_calls]
        parts.append(f"Tools called: {', '.join(names)}")
    if snapshot.latency_ms is not None:
        parts.append(f"Latency: {snapshot.latency_ms}ms")
    return " | ".join(parts) if parts else "No causal data available (set ANTHROPIC_API_KEY for LLM-based analysis)"


def _build_analysis_prompt(snapshot: Snapshot) -> str:
    lines = [
        "You are analyzing an AI agent's decision at a specific execution step.",
        "",
        f"Node: {snapshot.node_id}",
        f"Node type: {snapshot.node_type.value}",
        "",
    ]
    if snapshot.messages_in:
        lines.append("Input messages:")
        for msg in snapshot.messages_in[:3]:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            lines.append(f"  [{msg.role.value}]: {content[:300]}")
    if snapshot.messages_out:
        lines.append("Output:")
        out = snapshot.messages_out[0]
        content = out.content if isinstance(out.content, str) else str(out.content)
        lines.append(f"  {content[:300]}")
    if snapshot.tool_calls:
        lines.append("Tool calls made:")
        for tc in snapshot.tool_calls:
            lines.append(f"  {tc.name}({tc.arguments})")
    lines.extend([
        "",
        "In 2-3 sentences: Why did the agent make this decision? "
        "What alternatives might it have chosen, and why did it pick this path?",
    ])
    return "\n".join(lines)
