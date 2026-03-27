# Forkpoint ⚡

**Runtime debugger for multi-agent AI systems. Treat agent runs like git commits.**

Every state transition is a snapshot. You can branch from any point. You can diff two runs. You can rebase a failed run with corrected inputs.

---

## What's Here

```
forkpoint/
├── sdk/                  # Layer 1 — Universal instrumentation SDK (Python)
├── backend/              # REST + WebSocket API server (FastAPI + SQLAlchemy)
├── frontend/             # Visual debugger UI (React + ReactFlow)
├── examples/             # Working example scripts
└── docs/                 # Architecture and API reference
```

## The Five Layers

| Layer | What it does | Status |
|-------|-------------|--------|
| **1 — SDK** | Thin wrapper for LangGraph, CrewAI, AutoGen, raw loops. Captures every LLM call, tool call, and state transition as an immutable snapshot. | ✅ Built |
| **2 — UI** | Visual execution graph. Click any node to inspect full state, edit it, fork from it. | ✅ Built |
| **3 — Causal analysis** | For each agent decision, explain *why* the agent chose path A over B using logprobs or a secondary LLM call. | ✅ Built |
| **4 — Semantic drift** | Flag when inter-agent handoffs degrade semantically — technically valid JSON that lost context. | ✅ Built |
| **5 — Test generation** | Every production failure auto-generates a reproducible pytest fixture with all LLM and tool calls stubbed. | ✅ Built |

---

## Quickstart

### 1. Instrument your agent (zero config)

```python
from forkpoint import ForkpointTracer

with ForkpointTracer(agent_id="my-pipeline") as tracer:
    result = my_agent.run(inputs)
```

### 2. LangGraph (one line)

```python
from forkpoint import instrument_langgraph

graph = instrument_langgraph(graph, agent_id="my-pipeline")
result = graph.invoke({"messages": [...]})  # all captured automatically
```

### 3. Raw loop with full control

```python
from forkpoint import ForkpointTracer
from forkpoint.integrations.raw import AgentNode
from forkpoint.models.events import Message, MessageRole

with ForkpointTracer(agent_id="my-pipeline") as tracer:
    with AgentNode(tracer, node_id="planner") as node:
        call_id = node.llm_start(messages, model="gpt-4o")
        response = my_llm.complete(messages)
        node.llm_end(call_id, response)

        tool_id = node.tool_start("search", {"query": "..."})
        result = search_tool(...)
        node.tool_end(tool_id, result)
```

### 4. Fork from any historical point

```python
from forkpoint.models.events import StatePatch

child_tracer = tracer.fork(
    from_snapshot_id="abc123",
    patch=StatePatch(state_overrides={"system_prompt": "Be more concise"}),
    reason="Testing shorter prompts",
)
```

### 5. Replay deterministically

```python
from forkpoint.core.replay import build_replay_context

bundle = tracer.get_replay_bundle()
ctx = build_replay_context(bundle)

# In your agent, replace LLM/tool calls with stub calls:
result = ctx.call_tool("search", {"query": "test"})  # returns recorded value
response = ctx.call_llm("gpt-4o", messages)           # returns recorded response
```

---

## Run the Full Stack

```bash
# Option 1: Docker Compose (recommended)
docker compose up

# Option 2: Manual
# Backend
cd backend && pip install -e . && uvicorn forkpoint_server.main:app --reload

# Frontend
cd frontend && npm install && npm run dev

# SDK demo
cd sdk && pip install -e . && python ../examples/langgraph_example.py
```

Open **http://localhost:5173** for the UI.

---

## SDK: Local vs. Server mode

The SDK works with **zero infrastructure** by default — data writes to `~/.forkpoint/local.db` (SQLite). Switch to server mode when you're ready for the full UI:

```python
from forkpoint import ForkpointTracer, HttpTransport

tracer = ForkpointTracer(
    agent_id="my-pipeline",
    transport=HttpTransport(server_url="http://localhost:8000"),
)
```

---

## API Reference (Backend)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/runs/` | List runs (filter by agent_id, status) |
| `GET` | `/api/v1/runs/{id}` | Get run detail |
| `GET` | `/api/v1/runs/{id}/replay-bundle` | Download full ReplayBundle |
| `POST` | `/api/v1/runs/{id}/fork` | Fork a run from a snapshot |
| `GET` | `/api/v1/runs/{id}/snapshots` | List snapshots for a run |
| `GET` | `/api/v1/snapshots/{id}` | Get single snapshot |
| `GET` | `/api/v1/diff/?run_a=&run_b=` | Diff two runs |
| `POST` | `/api/v1/analysis/causal/{snap_id}` | Trigger causal analysis |
| `POST` | `/api/v1/analysis/drift/{run_id}` | Trigger semantic drift detection |
| `POST` | `/api/v1/analysis/testgen/{run_id}` | Generate test case from failure |
| `WS` | `/ws/runs/{run_id}` | Live event stream |

---

## Data Model: The Git Analogy

| Git concept | Forkpoint concept |
|-------------|-------------------|
| Commit | `Run` — one complete agent execution |
| Tree entry | `Snapshot` — state at one node, content-addressable |
| Branch | `Fork` — diverge from any snapshot |
| `git diff` | `RunDiff` — field-level comparison of two runs |
| Object store | `ReplayBundle` — self-contained deterministic re-execution package |
| `git checkout + replay` | Fork + StatePatch + replay engine |

---

## Architecture

```
┌─────────────────────────────────────────────┐
│                  Agent Code                  │
│  (LangGraph / CrewAI / AutoGen / raw loop)  │
└──────────────┬──────────────────────────────┘
               │ ForkpointTracer.on_llm_start/end
               │ ForkpointTracer.on_tool_start/end
               ▼
┌─────────────────────────────────────────────┐
│           SDK (forkpoint package)            │
│  tracer.py → snapshot.py → transport        │
│  LocalTransport (SQLite) / HttpTransport    │
└──────────────┬──────────────────────────────┘
               │ POST /api/v1/ingest/events
               ▼
┌─────────────────────────────────────────────┐
│        Backend (FastAPI + PostgreSQL)        │
│  runs / snapshots / forks / analysis APIs   │
│  WebSocket: WS /ws/runs/{run_id}            │
└──────────────┬──────────────────────────────┘
               │ REST + WebSocket
               ▼
┌─────────────────────────────────────────────┐
│       Frontend (React + ReactFlow)           │
│  ExecutionGraph → SnapshotInspector          │
│  RunDiff → StateEditor → Fork & Replay       │
└─────────────────────────────────────────────┘
```
