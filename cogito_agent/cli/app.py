from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cogito_agent.agent.core import AgentCore
from cogito_agent.agent.reasoner import LLMReasoner, RuleBasedReasoner
from cogito_agent.agent.session import JSONLSessionStore, SessionManager, SessionStore, SQLiteSessionStore
from cogito_agent.agent.state import InboundMessage
from cogito_agent.agent.subagent import SubAgentRunner
from cogito_agent.cli.commands import HELP_TEXT, CommandResult
from cogito_agent.config import AppConfig, load_config
from cogito_agent.drift.runner import DriftRunner
from cogito_agent.llm.embeddings import OpenAICompatibleEmbeddingClient
from cogito_agent.llm.openai_compatible import OpenAICompatibleProvider
from cogito_agent.llm.reranker import OpenAICompatibleRerankerClient
from cogito_agent.memory.consolidation import MemoryConsolidator
from cogito_agent.memory.markdown_store import MarkdownMemoryStore
from cogito_agent.memory.optimizer import MemoryOptimizer
from cogito_agent.memory.retriever import MemoryRetriever
from cogito_agent.memory.vector_store import InMemoryVectorStore
from cogito_agent.plugins.builtin.observe import ObservePlugin
from cogito_agent.plugins.builtin.shell_safety import ShellSafetyPlugin
from cogito_agent.plugins.builtin.tool_loop_guard import ToolLoopGuardPlugin
from cogito_agent.plugins.manager import PluginManager
from cogito_agent.proactive.loop import ProactiveLoop
from cogito_agent.proactive.quota import ProactiveQuota
from cogito_agent.prompting.manager import PromptManager
from cogito_agent.prompting.store import PromptStore
from cogito_agent.tools.calculator import CalculatorTool
from cogito_agent.tools.filesystem import FileReadTool, FileWriteTool
from cogito_agent.tools.memory_tools import MemoryRecallTool, MemoryWriteTool
from cogito_agent.tools.registry import ToolRegistry
from cogito_agent.tools.schedule import ScheduleCreateTool, ScheduleStore
from cogito_agent.tools.time_tool import TimeTool
from cogito_agent.tools.tool_search import ToolSearchTool
from cogito_agent.tools.web import WebFetchTool
from cogito_agent.tracing.tracer import Tracer


@dataclass(slots=True)
class RuntimeServices:
    agent: AgentCore
    session_manager: SessionManager
    tracer: Tracer
    tool_registry: ToolRegistry
    memory_store: MarkdownMemoryStore
    memory_optimizer: MemoryOptimizer
    schedule_store: ScheduleStore
    proactive_loop: ProactiveLoop
    drift_runner: DriftRunner
    plugin_manager: PluginManager
    subagent_runner: SubAgentRunner
    prompt_store: PromptStore


def build_default_runtime(config: AppConfig | None = None) -> RuntimeServices:
    config = config or load_config()
    workspace = config.workspace
    workspace.mkdir(parents=True, exist_ok=True)

    session_store: SessionStore
    if config.session.store == "sqlite":
        session_store = SQLiteSessionStore(workspace)
    else:
        session_store = JSONLSessionStore(workspace)
    session_manager = SessionManager(store=session_store, max_messages=config.agent.memory_window)
    tracer = Tracer(
        workspace=workspace,
        store=config.tracing.store,
        otel_enabled=config.tracing.otel_enabled,
        otel_service_name=config.tracing.otel_service_name,
        otel_exporter=config.tracing.otel_exporter,
        otel_endpoint=config.tracing.otel_endpoint,
    )
    memory_store = MarkdownMemoryStore(workspace=workspace)
    embedding_role = config.llm.roles.get("embedding")
    embedding_client = (
        OpenAICompatibleEmbeddingClient(
            api_key=embedding_role.api_key,
            base_url=embedding_role.base_url,
            model=embedding_role.model,
        )
        if embedding_role and embedding_role.enabled and embedding_role.api_key and embedding_role.base_url and embedding_role.model
        else None
    )
    reranker_role = config.llm.roles.get("reranker")
    reranker = (
        OpenAICompatibleRerankerClient(
            api_key=reranker_role.api_key,
            base_url=reranker_role.base_url,
            model=reranker_role.model,
        )
        if reranker_role and reranker_role.enabled and reranker_role.api_key and reranker_role.base_url and reranker_role.model
        else None
    )
    vector_store = InMemoryVectorStore.from_workspace_docs(workspace, embedding_client=embedding_client)
    memory_retriever = MemoryRetriever(memory_store, vector_store=vector_store, reranker=reranker, top_k=config.memory.top_k)
    memory_consolidator = MemoryConsolidator(workspace, memory_store)
    memory_optimizer = MemoryOptimizer(memory_consolidator)
    prompt_store = PromptStore(workspace, Path(__file__).parents[1] / "prompting" / "system_prompt.md")
    schedule_store = ScheduleStore(workspace)
    drift_runner = DriftRunner(
        workspace,
        tracer=tracer,
        enabled=config.drift.enabled,
        min_interval_hours=config.drift.min_interval_hours,
        max_steps=config.drift.max_steps,
    )
    proactive_loop = ProactiveLoop(
        workspace,
        quota=ProactiveQuota(
            workspace,
            daily_limit=config.proactive.daily_limit,
            cooldown_seconds=config.proactive.cooldown_seconds,
            quiet_hours=config.proactive.quiet_hours,
        ),
        schedule_store=schedule_store,
        tracer=tracer,
        threshold=config.proactive.threshold,
        enabled=config.proactive.enabled,
    )
    plugin_manager = PluginManager([ToolLoopGuardPlugin(), ShellSafetyPlugin(), ObservePlugin()])

    tool_registry = ToolRegistry(plugin_manager=plugin_manager)
    tool_registry.register(CalculatorTool())
    tool_registry.register(TimeTool())
    if config.tools.enable_filesystem:
        tool_registry.register(FileReadTool(workspace))
        tool_registry.register(FileWriteTool(workspace, require_approval_for_write=config.tools.require_approval_for_write))
    if config.tools.enable_web:
        tool_registry.register(WebFetchTool())
    tool_registry.register(MemoryWriteTool(memory_store))
    tool_registry.register(MemoryRecallTool(memory_store))
    tool_registry.register(ScheduleCreateTool(schedule_store))
    tool_registry.register(ToolSearchTool(tool_registry))

    if config.llm.api_key:
        llm = OpenAICompatibleProvider(
            api_key=config.llm.api_key,
            base_url=config.llm.base_url,
            model=config.llm.model,
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
            tracer=tracer,
        )
        reasoner = LLMReasoner(
            llm_provider=llm,
            prompt_manager=PromptManager(system_prompt_path=prompt_store.current_path),
            tool_registry=tool_registry,
            memory_retriever=memory_retriever if config.memory.enabled else None,
            max_iterations=config.agent.max_iterations,
        )
    else:
        reasoner = RuleBasedReasoner()

    agent = AgentCore(
        session_manager=session_manager,
        reasoner=reasoner,
        tracer=tracer,
        plugin_manager=plugin_manager,
        memory_consolidator=memory_consolidator,
    )
    subagent_runner = SubAgentRunner(agent)
    return RuntimeServices(
        agent=agent,
        session_manager=session_manager,
        tracer=tracer,
        tool_registry=tool_registry,
        memory_store=memory_store,
        memory_optimizer=memory_optimizer,
        schedule_store=schedule_store,
        proactive_loop=proactive_loop,
        drift_runner=drift_runner,
        plugin_manager=plugin_manager,
        subagent_runner=subagent_runner,
        prompt_store=prompt_store,
    )


def build_default_agent(config: AppConfig | None = None) -> tuple[AgentCore, SessionManager, Tracer, ToolRegistry, MarkdownMemoryStore]:
    runtime = build_default_runtime(config)
    return runtime.agent, runtime.session_manager, runtime.tracer, runtime.tool_registry, runtime.memory_store


class CogitoCLI:
    def __init__(self, workspace: Path | None = None, session_id: str = "default") -> None:
        config = load_config()
        if workspace is not None:
            config.workspace = workspace
        self.workspace = config.workspace
        self.session_id = session_id
        self.debug = config.debug
        self.runtime = build_default_runtime(config)

    async def run(self) -> None:
        print("Cogito-Agent Runtime started.")
        print("输入 /help 查看命令。")
        while True:
            try:
                text = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye.")
                return

            if not text:
                continue

            command = self.handle_command(text)
            if command.handled:
                if command.output:
                    print(command.output)
                if command.should_exit:
                    print("Bye.")
                    return
                continue

            response = await self.runtime.agent.process(InboundMessage.from_cli(text, session_id=self.session_id))
            print(f"Cogito: {response.content}")
            print(f"trace_id: {response.trace_id}")
            if self.debug:
                print(f"debug: {response.metadata}")

    def handle_command(self, text: str) -> CommandResult:
        if text == "/exit":
            return CommandResult(handled=True, should_exit=True)
        if text == "/help":
            return CommandResult(handled=True, output=HELP_TEXT)
        if text == "/reset":
            self.runtime.session_manager.reset(self.session_id)
            return CommandResult(handled=True, output="当前 session 已清空。")
        if text == "/history":
            messages = self.runtime.session_manager.history(self.session_id)
            if not messages:
                return CommandResult(handled=True, output="当前 session 暂无历史。")
            return CommandResult(handled=True, output="\n".join(f"[{m.role}] {m.content}" for m in messages))
        if text == "/tools":
            tools = self.runtime.tool_registry.list_tools()
            return CommandResult(handled=True, output="\n".join(f"- {tool.name}: {tool.description}" for tool in tools))
        if text == "/memory":
            entries = self.runtime.memory_store.list_entries()
            if not entries:
                return CommandResult(handled=True, output="暂无长期记忆。")
            return CommandResult(handled=True, output="\n".join(f"- {e.memory_id}: {e.content_preview}" for e in entries))
        if text == "/memory optimize":
            result = self.runtime.memory_optimizer.run_once()
            return CommandResult(handled=True, output=f"已归档 {len(result.promoted_ids)} 条 pending 记忆。")
        if text.startswith("/forget "):
            memory_id = text.removeprefix("/forget ").strip()
            ok = self.runtime.memory_store.forget(memory_id)
            return CommandResult(handled=True, output="已删除记忆。" if ok else "未找到该记忆。")
        if text == "/schedules":
            schedules = self.runtime.schedule_store.list()
            if not schedules:
                return CommandResult(handled=True, output="暂无 schedule。")
            return CommandResult(handled=True, output="\n".join(f"- {s.schedule_id} [{s.trigger}] {s.name}: {s.prompt}" for s in schedules))
        if text == "/plugins":
            return CommandResult(handled=True, output="\n".join(f"- {p['name']}" for p in self.runtime.plugin_manager.list_plugins()))
        if text == "/debug on":
            self.debug = True
            return CommandResult(handled=True, output="Debug 已开启。")
        if text == "/debug off":
            self.debug = False
            return CommandResult(handled=True, output="Debug 已关闭。")
        if text == "/trace last":
            return CommandResult(handled=True, output=self.runtime.tracer.get_last_trace_summary())
        if text.startswith("/trace "):
            trace_id = text.removeprefix("/trace ").strip()
            if not trace_id:
                return CommandResult(handled=True, output="请提供 trace_id。")
            return CommandResult(handled=True, output=self.runtime.tracer.get_trace_summary(trace_id))
        if text == "/proactive status":
            return CommandResult(handled=True, output=str(self.runtime.proactive_loop.status()))
        if text == "/proactive tick":
            decision = self.runtime.proactive_loop.tick_once()
            return CommandResult(handled=True, output=str(decision))
        if text == "/drift skills":
            return CommandResult(handled=True, output=str(self.runtime.drift_runner.status()))
        if text == "/drift run":
            return CommandResult(handled=True, output=str(self.runtime.drift_runner.run_once()))
        return CommandResult(handled=False)
