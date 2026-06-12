# Cogito-Agent

Cogito-Agent 是一个面向个人使用场景的本地 AI Agent Runtime。它具备对话、工具调用、长期记忆、RAG、Trace 可观测、主动任务、后台 Drift 任务、API 服务和 Dashboard 管理能力。

项目目标不是做一个普通聊天机器人，而是构建一个“能记住你、能调用工具、能追踪原因、能后台运行、能主动提醒”的个人 Agent 运行时。

## 当前状态

当前版本已经覆盖 `task.md` 中 P0、P1、P2 的主要验收项，并实现了 P3 的核心管理面。

最近测试结果：

```bash
42 passed, 1 warning
```

## 主要能力

- CLI 对话入口：支持 `/history`、`/tools`、`/memory`、`/forget`、`/trace last`
- OpenAI-compatible LLM Provider：可接 DeepSeek、硅基流动等兼容接口
- 多模型角色配置：主模型、快速模型、推理模型、总结模型、评估模型、Embedding、视觉、多模态、Reranker
- PromptManager：系统提示词、会话历史、记忆和文档检索注入
- ToolRegistry：工具注册、schema 导出、参数校验、风险等级、安全拦截、trace 记录
- 内置工具：计算器、时间、工作区文件读写、记忆写入/回忆、工具搜索、可选网页抓取、计划任务创建
- Reasoner Tool Loop：支持 LLM 多步工具调用和工具结果回填
- Markdown Memory：长期记忆、pending 记忆、记忆优化和删除
- RAG：支持本地 `workspace/docs` 文档检索
- Embedding RAG：启用 embedding 配置后可使用真实 embedding 模型
- Reranker：启用 reranker 配置后可对 RAG 结果重排
- Plugin System：生命周期 phase、工具调用前拦截、工具结果后处理
- Trace：JSONL / SQLite 存储，支持 trace 列表、步骤、工具、记忆、统计
- OpenTelemetry：可选 console / OTLP span export hook
- Scheduler：本地计划任务、due 检测、触发标记、取消和更新
- Proactive：主动 tick、评分、quota、cooldown、quiet hours、outbox、trace
- Drift：`SKILL.md` 后台技能、内置记忆审计和自诊断、最小间隔、state、trace
- SubAgent：子任务执行和 parent/child trace 关联
- API Server：FastAPI 对外接口
- Dashboard：系统健康、Trace Timeline、工具统计、记忆、计划任务、Prompt、Drift、Proactive 配置管理
- Webhook 集成：通用入站 webhook 和 Telegram webhook 形态入口
- 安全默认值：本地密钥不入库，工作区文件沙箱，web 工具默认关闭

## 目录结构

```text
cogito-agent/
  README.md
  main.py
  config.example.toml
  pyproject.toml

  cogito_agent/
    agent/          AgentCore、Session、Reasoner、SubAgent
    api/            FastAPI 服务和 Dashboard/API 路由
    cli/            CLI 入口和默认 runtime 组装
    drift/          后台 SKILL.md 任务
    llm/            LLM、Embedding、Reranker 客户端
    memory/         Markdown Memory、RAG、Vector Store
    plugins/        插件系统和内置插件
    proactive/      主动任务、quota、outbox、scoring
    prompting/      PromptManager、system prompt、PromptStore
    tools/          内置工具和 ToolRegistry
    tracing/        JSONL/SQLite TraceStore、OpenTelemetry hook

  tests/
```

运行后会在 `workspace/` 下生成本地数据：

```text
workspace/
  memory/
  docs/
  traces/
  drift/
  prompts/
  schedules.json
  proactive_sources.json
  proactive_quota.json
  proactive_outbox.jsonl
```

## 安装

推荐使用项目同名 conda 环境：

```bash
conda create -n cogito-agent python=3.11 -y
conda activate cogito-agent
python -m pip install -e .[dev]
```

如果环境已经创建过：

```bash
conda activate cogito-agent
python -m pip install -e .[dev]
```

## 配置

复制 example 配置：

```bash
copy config.example.toml config.toml
```

Linux/macOS：

```bash
cp config.example.toml config.toml
```

`config.toml` 是本地私密配置，已被 `.gitignore` 忽略，不会上传到 GitHub。

### 模型角色

项目支持多个模型角色：

| 角色 | 用途 |
|---|---|
| `llm.main` | 主对话、主要推理、最终回答 |
| `llm.fast` | 快速分类、轻量判断、低成本路由 |
| `llm.reasoning` | 深度推理、复杂分析 |
| `llm.summarizer` | 会话压缩、记忆整理、长文摘要 |
| `llm.judge` | 评估、打分、主动推送判断 |
| `llm.embedding` | 语义向量、RAG 检索 |
| `llm.multimodal` | 多模态模型 |
| `llm.vision` | 图片理解、OCR、视觉任务 |
| `llm.reranker` | RAG 检索结果重排 |

示例配置中已经包含 DeepSeek 和硅基流动模型占位符。真实 API key 请只写在本地 `config.toml` 或环境变量中。

### DeepSeek 主模型

```toml
[llm.main]
enabled = true
model = "deepseek-chat"
api_key = "你的 DeepSeek API Key"
base_url = "https://api.deepseek.com"
temperature = 0.2
max_tokens = 2048
```

### 硅基流动 Embedding / Reranker / Vision

```toml
[llm.embedding]
enabled = true
model = "BAAI/bge-m3"
api_key = "你的硅基流动 API Key"
base_url = "https://api.siliconflow.cn/v1"

[llm.reranker]
enabled = true
model = "BAAI/bge-reranker-v2-m3"
api_key = "你的硅基流动 API Key"
base_url = "https://api.siliconflow.cn/v1"

[llm.vision]
enabled = true
model = "Qwen/Qwen3.6-27B"
api_key = "你的硅基流动 API Key"
base_url = "https://api.siliconflow.cn/v1"
enable_thinking = false
multimodal = true
```

注意：DeepSeek 不能直接读图。图片理解应交给 `llm.vision` 或 `llm.multimodal` 角色。

### Trace 存储

默认使用 JSONL：

```toml
[tracing]
enabled = true
store = "jsonl"
```

也可以切换 SQLite：

```toml
[tracing]
store = "sqlite"
```

可选 OpenTelemetry：

```toml
[tracing]
otel_enabled = true
otel_service_name = "cogito-agent"
otel_exporter = "otlp"
otel_endpoint = "http://localhost:4318/v1/traces"
```

如果没有安装 OpenTelemetry 相关依赖，系统会自动降级为 no-op，不影响主流程。

### 工具开关

```toml
[tools]
enable_filesystem = true
enable_web = false
enable_shell = false
require_approval_for_write = false
```

`web_fetch` 默认关闭。Shell 工具目前默认不开放，避免高风险自动执行。

### Proactive

```toml
[proactive]
enabled = false
threshold = 0.6
daily_limit = 5
cooldown_seconds = 3600
quiet_hours = "23:00-07:00"
```

### Drift

```toml
[drift]
enabled = false
max_steps = 30
min_interval_hours = 1
```

## 运行 CLI

```bash
conda activate cogito-agent
python main.py
```

常用命令：

```text
/help
/history
/tools
/memory
/forget <memory_id>
/memory optimize
/schedules
/plugins
/debug on
/debug off
/trace last
/trace <trace_id>
/proactive status
/proactive tick
/drift skills
/drift run
/exit
```

如果没有配置真实 LLM key，系统会使用离线 rule-based fallback，仍然可以测试 CLI、session、trace 等基础链路。

## 运行 API 服务

```bash
conda activate cogito-agent
uvicorn cogito_agent.api.server:app --reload
```

默认地址：

```text
http://127.0.0.1:8000
```

Dashboard：

```text
http://127.0.0.1:8000/dashboard
```

OpenAPI 文档：

```text
http://127.0.0.1:8000/docs
```

## API 概览

### 对话

```http
POST /chat
```

请求：

```json
{
  "session_id": "default",
  "message": "你好",
  "channel": "api",
  "metadata": {}
}
```

### 通用 Webhook

```http
POST /webhooks/inbound/{source}
```

请求：

```json
{
  "message": "来自外部系统的消息",
  "session_id": "webhook-session",
  "user_id": "optional-user",
  "metadata": {
    "source_url": "optional"
  }
}
```

### Telegram Webhook

```http
POST /telegram/webhook
```

接受 Telegram update payload，读取 `message.text` 并送入 Agent。

### 集成发现

```http
GET /integrations
```

### Session

```http
GET /sessions/{session_id}
POST /sessions/{session_id}/reset
```

### Tools

```http
GET /tools
```

### Memory

```http
GET /memory
DELETE /memory/{memory_id}
POST /memory/optimize
```

### Prompt 管理

```http
GET /prompts/system
PUT /prompts/system
GET /prompts/system/history
```

### Trace

```http
GET /traces
GET /traces/stats/tools
GET /traces/{trace_id}
GET /traces/{trace_id}/steps
GET /traces/{trace_id}/tools
GET /traces/{trace_id}/memory
```

### Scheduler

```http
POST /schedules
GET /schedules
GET /schedules/due
GET /schedules/{schedule_id}
PATCH /schedules/{schedule_id}
DELETE /schedules/{schedule_id}
```

### Proactive

```http
GET /proactive/status
PATCH /proactive/config
POST /proactive/tick
GET /proactive/outbox
```

### Drift

```http
GET /drift/skills
GET /drift/skills/{name}
PUT /drift/skills/{name}
DELETE /drift/skills/{name}
POST /drift/run
```

### Dashboard / Health

```http
GET /dashboard
GET /dashboard/data
GET /health
```

## Memory 和 RAG

长期记忆默认保存在：

```text
workspace/memory/MEMORY.md
```

待整理记忆和近期上下文保存在：

```text
workspace/memory/PENDING.md
workspace/memory/RECENT_CONTEXT.md
```

本地知识库文档放在：

```text
workspace/docs/
```

支持 `.md` 和 `.txt` 文档。启用 `llm.embedding` 后，RAG 会使用 embedding-backed 检索；启用 `llm.reranker` 后，会对候选文档进行重排。

## Scheduler / Proactive / Drift

### Scheduler

计划任务保存在：

```text
workspace/schedules.json
```

支持：

- 一次性任务：`trigger = "once"`
- 简单间隔任务：`trigger = "every"`
- 基础 cron 形态：`@daily` 或 `HH:MM`

### Proactive

主动任务输入源：

```text
workspace/proactive_sources.json
```

主动推送结果 outbox：

```text
workspace/proactive_outbox.jsonl
```

Proactive tick 会读取 alert/content/context 数据，评分后根据 quota、cooldown、quiet hours 决定是否写入 outbox。

### Drift

Drift 技能目录：

```text
workspace/drift/skills/<skill-name>/SKILL.md
```

内置技能：

- `audit-dirty-memories`
- `self-diagnosis`

每次 Drift run 会写入 state 和 trace，并在结果中包含 `finish_drift` 标记。

## Trace 和可观测

每次请求都会生成 `trace_id`。Trace 覆盖：

- 用户输入
- session 加载
- prompt 渲染
- LLM 调用
- 工具调用
- memory / RAG 检索
- proactive 决策
- drift 执行
- final response

JSONL 存储路径：

```text
workspace/traces/YYYY-MM-DD.jsonl
```

SQLite 存储路径：

```text
workspace/traces.sqlite3
```

Dashboard 中可以查看最近 trace、工具统计、系统健康、记忆、计划任务、Proactive、Drift 和 Prompt 状态。

## 安全设计

- `config.toml` 不应提交到 GitHub
- API Key 只从本地配置或环境变量读取
- Trace 和日志会做敏感信息 redaction
- 文件工具限制在 workspace 内
- `web_fetch` 默认关闭
- Shell 工具默认关闭
- 外部内容只作为上下文，不视为系统指令
- Memory 写入有 source trace 关联，可删除、可审计

## 测试

```bash
conda activate cogito-agent
python -m pytest
```

当前测试覆盖：

- AgentCore
- SessionManager
- Reasoner Tool Loop
- ToolRegistry 和内置工具
- Memory / RAG / Embedding / Reranker
- Trace JSONL / SQLite / OTEL hook
- Plugin system
- API routes
- Scheduler
- Proactive
- Drift
- Dashboard 管理接口
- Webhook / Telegram webhook

## GitHub 提交说明

仓库只应提交：

- 源代码
- 测试
- README
- `config.example.toml`

不应提交：

- `config.toml`
- 真实 API Key
- 本地 workspace 数据
- trace、memory、outbox 等运行时数据

## 当前完成度

按 `task.md` 估算：

| 范围 | 状态 |
|---|---|
| P0 核心 Agent Runtime | 完成 |
| P1 Memory / RAG / Plugin / API | 完成 |
| P2 Scheduler / Proactive / Drift / SubAgent | 完成 |
| P3 Dashboard / SQLite / Observability / Integration | 基本完成 |

剩余更多属于外部部署和真实服务联调：

- 将 OTLP 指向真实 Jaeger / Phoenix / Langfuse 网关
- 将 Telegram webhook 挂到公网回调地址
- 将 Dashboard 做成更复杂的前端应用
- 将 Proactive / Drift 包装为长期 daemon/service

这些不需要在代码中硬编码凭据或外部服务地址。
