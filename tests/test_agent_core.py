from __future__ import annotations

import asyncio

from cogito_agent.agent.core import AgentCore
from cogito_agent.agent.reasoner import RuleBasedReasoner
from cogito_agent.agent.session import SessionManager
from cogito_agent.agent.state import InboundMessage, Message
from cogito_agent.tracing.tracer import Tracer


def test_agent_process_returns_echo_and_trace_id(tmp_path):
    session_manager = SessionManager()
    tracer = Tracer(workspace=tmp_path)
    agent = AgentCore(session_manager=session_manager, reasoner=RuleBasedReasoner(), tracer=tracer)

    response = asyncio.run(agent.process(InboundMessage.from_cli("你好")))

    assert response.content == "我收到了你的消息：你好"
    assert response.trace_id.startswith("trace_")
    assert response.status == "ok"


def test_session_history_keeps_user_and_assistant(tmp_path):
    session_manager = SessionManager()
    tracer = Tracer(workspace=tmp_path)
    agent = AgentCore(session_manager=session_manager, reasoner=RuleBasedReasoner(), tracer=tracer)

    asyncio.run(agent.process(InboundMessage.from_cli("第一条")))

    history = session_manager.history("default")
    assert [m.role for m in history] == ["user", "assistant"]
    assert history[0].content == "第一条"
    assert history[1].content == "我收到了你的消息：第一条"


def test_session_reset():
    manager = SessionManager()
    inbound = InboundMessage.from_cli("hello")

    manager.append(Message.user(inbound, trace_id="trace_test"))
    assert len(manager.history("default")) == 1

    manager.reset("default")
    assert manager.history("default") == []
