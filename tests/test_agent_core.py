from __future__ import annotations

import asyncio

from cogito_agent.agent.core import AgentCore
from cogito_agent.agent.reasoner import RuleBasedReasoner
from cogito_agent.agent.session import JSONLSessionStore, MemorySessionStore, SessionManager, SQLiteSessionStore
from cogito_agent.agent.state import InboundMessage, Message
from cogito_agent.agent.subagent import SubAgentRunner, SubAgentTask
from cogito_agent.tracing.tracer import Tracer


def test_agent_process_returns_echo_and_trace_id(tmp_path):
    session_manager = SessionManager(store=MemorySessionStore())
    tracer = Tracer(workspace=tmp_path)
    agent = AgentCore(session_manager=session_manager, reasoner=RuleBasedReasoner(), tracer=tracer)

    response = asyncio.run(agent.process(InboundMessage.from_cli("你好")))

    assert response.content == "我收到了你的消息：你好"
    assert response.trace_id.startswith("trace_")
    assert response.status == "ok"


def test_session_history_keeps_user_and_assistant(tmp_path):
    session_manager = SessionManager(store=MemorySessionStore())
    tracer = Tracer(workspace=tmp_path)
    agent = AgentCore(session_manager=session_manager, reasoner=RuleBasedReasoner(), tracer=tracer)

    asyncio.run(agent.process(InboundMessage.from_cli("第一条")))

    history = session_manager.history("default")
    assert [m.role for m in history] == ["user", "assistant"]
    assert history[0].content == "第一条"
    assert history[1].content == "我收到了你的消息：第一条"


def test_session_reset():
    manager = SessionManager(store=MemorySessionStore())
    inbound = InboundMessage.from_cli("hello")

    manager.append(Message.user(inbound, trace_id="trace_test"))
    assert len(manager.history("default")) == 1

    manager.reset("default")
    assert manager.history("default") == []


def test_session_manager_persists_jsonl(tmp_path):
    store = JSONLSessionStore(tmp_path)
    manager = SessionManager(store=store)
    inbound = InboundMessage.from_cli("hello")
    message = Message.user(inbound, trace_id="trace_test")

    manager.append(message)
    reloaded = SessionManager(store=store)

    history = reloaded.history("default")
    assert len(history) == 1
    assert history[0].message_id == message.message_id
    assert history[0].trace_id == "trace_test"
    assert reloaded.state_deltas("default")[-1]["type"] == "message_appended"


def test_session_manager_persists_sqlite(tmp_path):
    store = SQLiteSessionStore(tmp_path)
    manager = SessionManager(store=store)
    inbound = InboundMessage.from_cli("hello sqlite")
    message = Message.user(inbound, trace_id="trace_sqlite")

    manager.append(message)
    reloaded = SessionManager(store=store)

    history = reloaded.history("default")
    assert len(history) == 1
    assert history[0].message_id == message.message_id
    assert history[0].trace_id == "trace_sqlite"


def test_session_manager_restart_recovery(tmp_path):
    store = JSONLSessionStore(tmp_path)
    manager = SessionManager(store=store, max_messages=10)

    manager.append(Message.user(InboundMessage.from_cli("msg1"), trace_id="t1"))
    manager.append(Message.user(InboundMessage.from_cli("msg2"), trace_id="t2"))

    fresh = SessionManager(store=JSONLSessionStore(tmp_path), max_messages=10)
    history = fresh.history("default")

    assert len(history) == 2
    assert history[0].content == "msg1"
    assert history[1].content == "msg2"
    assert fresh.state_deltas("default")[-1]["type"] == "message_appended"


def test_session_manager_restart_recovery_sqlite(tmp_path):
    store = SQLiteSessionStore(tmp_path)
    manager = SessionManager(store=store, max_messages=10)

    manager.append(Message.user(InboundMessage.from_cli("first"), trace_id="t1"))
    manager.append(Message.user(InboundMessage.from_cli("second"), trace_id="t2"))

    fresh = SessionManager(store=SQLiteSessionStore(tmp_path), max_messages=10)
    history = fresh.history("default")

    assert len(history) == 2
    assert history[0].content == "first"
    assert history[1].content == "second"


def test_subagent_runner_links_child_trace(tmp_path):
    session_manager = SessionManager(store=MemorySessionStore())
    tracer = Tracer(workspace=tmp_path)
    agent = AgentCore(session_manager=session_manager, reasoner=RuleBasedReasoner(), tracer=tracer)
    parent_response = asyncio.run(agent.process(InboundMessage.from_cli("parent task")))
    runner = SubAgentRunner(agent)

    child_response = asyncio.run(
        runner.run(
            SubAgentTask(
                name="analysis",
                content="child task",
                parent_trace_id=parent_response.trace_id,
                parent_session_id=parent_response.session_id,
            )
        )
    )

    child_record = tracer.get_trace_record(child_response.trace_id)
    parent_steps = tracer.get_trace_steps(parent_response.trace_id)

    assert child_record is not None
    assert child_record["metadata"]["parent_trace_id"] == parent_response.trace_id
    assert any(
        step["name"] == "trace_link_created"
        and step["metadata"]["child_trace_id"] == child_response.trace_id
        and step["metadata"]["relation"] == "subagent"
        for step in parent_steps
    )
