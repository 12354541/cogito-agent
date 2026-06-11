# Cogito-Agent

Cogito-Agent is a local personal agent runtime with CLI/API entry points,
trace recording, OpenAI-compatible LLM support, tool calling, and Markdown
memory.

## Current Capabilities

- CLI chat loop with `/history`, `/tools`, `/memory`, `/trace last`
- OpenAI-compatible provider, tested with DeepSeek configuration
- PromptManager with system prompt, session history, and memory injection
- ToolRegistry with schema export, argument validation, risk checks, and trace
- Built-in tools: calculator, current time, workspace file read/write, memory write/recall, schedule create
- JSONL trace store under `workspace/traces`
- FastAPI app with `/chat`, `/tools`, `/memory`, `/traces/{trace_id}`, `/schedules`, `/plugins`, `/proactive/status`, `/drift/skills`
- Plugin lifecycle and tool interception with built-in observe, shell safety, and loop guard plugins
- Markdown memory consolidation plus dependency-free lexical RAG over `workspace/docs`
- File-backed Scheduler, Proactive single-tick decisions, and Drift skill audit runner
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
