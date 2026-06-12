# Cogito-Agent

Cogito-Agent is a local personal agent runtime with CLI/API entry points,
trace recording, OpenAI-compatible LLM support, tool calling, and Markdown
memory.

## Current Capabilities

- CLI chat loop with `/history`, `/tools`, `/memory`, `/forget`, `/trace last`
- OpenAI-compatible provider, tested with DeepSeek configuration
- PromptManager with system prompt, session history, and memory injection
- ToolRegistry with schema export, argument validation, risk checks, and trace
- Built-in tools: calculator, current time, workspace file read/write, memory write/recall, tool search, optional web fetch, schedule create
- JSONL trace store under `workspace/traces` or optional SQLite trace store, with structured trace list, step/tool/memory queries, and tool statistics
- FastAPI app with `/chat`, `/dashboard`, `/dashboard/data`, `/health`, session reset/history, `/tools`, `/memory`, `/prompts/system`, `/traces`, `/traces/stats/tools`, `/traces/{trace_id}`, `/traces/{trace_id}/steps`, `/schedules`, `/schedules/due`, `/plugins`, `/proactive/status`, `/proactive/config`, `/proactive/outbox`, `/drift/skills`
- Plugin lifecycle and tool interception with built-in observe, shell safety, and loop guard plugins
- Markdown memory consolidation plus lexical or embedding-backed RAG over `workspace/docs`, with optional reranking
- SubAgent runner with parent/child trace linkage for scoped child tasks
- File-backed Scheduler with due detection and create/update/cancel APIs
- Proactive tick loop with alert/content/context scoring, quota, cooldown, quiet hours, outbox delivery records, schedule triggering, and trace events
- Drift runner with SKILL.md loading, built-in audit/self-diagnosis skills, min-interval state, finish markers, and trace events
- Dashboard/API management for prompt versions, Drift skills, proactive config, system health, trace timeline, memory, schedules, and tool statistics
- Optional OpenTelemetry span export hook, disabled by default and safe when OpenTelemetry packages are not installed
- Offline rule-based fallback when `LLM_API_KEY` is not configured

## Setup

```bash
conda activate cogito-agent
python -m pip install -e .[dev]
```

Model roles and credentials are configured in `config.toml`. Environment
variables can still override values when needed, but `apikey.txt` is no longer
read by the runtime.

## Run

```bash
python main.py
```

API server:

```bash
uvicorn cogito_agent.api.server:app --reload
```

## Test

```bash
python -m pytest
```
