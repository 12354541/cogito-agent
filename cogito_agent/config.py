from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _resolve_env(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if value.startswith("${") and value.endswith("}"):
        return os.getenv(value[2:-1], "")
    return os.path.expandvars(value)


def _get_nested(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _choose(env_name: str, config_value: Any, default: Any) -> Any:
    for value in (os.getenv(env_name), config_value, default):
        resolved = _resolve_env(value)
        if resolved not in (None, ""):
            return resolved
    return ""


@dataclass(slots=True)
class ModelRoleConfig:
    enabled: bool = True
    provider: str = "openai_compatible"
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.2
    max_tokens: int = 2048
    enable_thinking: bool = False
    multimodal: bool = False


@dataclass(slots=True)
class LLMConfig:
    provider: str = "openai_compatible"
    model: str = "deepseek-chat"
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    temperature: float = 0.2
    max_tokens: int = 2048
    roles: dict[str, ModelRoleConfig] = field(default_factory=dict)


@dataclass(slots=True)
class AgentConfig:
    max_iterations: int = 8
    memory_window: int = 40


@dataclass(slots=True)
class ToolsConfig:
    enable_filesystem: bool = True
    enable_web: bool = False
    enable_shell: bool = False
    require_approval_for_write: bool = False


@dataclass(slots=True)
class MemoryConfig:
    enabled: bool = True
    top_k: int = 5


@dataclass(slots=True)
class TracingConfig:
    enabled: bool = True
    store: str = "jsonl"
    redact_sensitive: bool = True
    save_prompt_hash: bool = True
    save_prompt_preview: bool = True
    otel_enabled: bool = False
    otel_service_name: str = "cogito-agent"


@dataclass(slots=True)
class ProactiveConfig:
    enabled: bool = False
    threshold: float = 0.6
    daily_limit: int = 5
    cooldown_seconds: int = 3600
    quiet_hours: str = ""


@dataclass(slots=True)
class DriftConfig:
    enabled: bool = False
    max_steps: int = 30
    min_interval_hours: float = 1.0


@dataclass(slots=True)
class AppConfig:
    """Runtime config loaded from config.toml and environment variables."""

    workspace: Path = Path("workspace")
    debug: bool = False
    llm: LLMConfig = field(default_factory=LLMConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    tracing: TracingConfig = field(default_factory=TracingConfig)
    proactive: ProactiveConfig = field(default_factory=ProactiveConfig)
    drift: DriftConfig = field(default_factory=DriftConfig)


def _env_name_for_role(role: str, key: str) -> str:
    if role == "main":
        mapping = {
            "provider": "LLM_PROVIDER",
            "model": "LLM_MODEL",
            "api_key": "LLM_API_KEY",
            "base_url": "LLM_BASE_URL",
            "temperature": "LLM_TEMPERATURE",
            "max_tokens": "LLM_MAX_TOKENS",
        }
        return mapping[key]
    return f"{role.upper()}_LLM_{key.upper()}"


def _role_config(
    *,
    role: str,
    data: dict[str, Any],
    parent_provider: str,
    defaults: dict[str, Any],
) -> ModelRoleConfig:
    provider = str(_choose(_env_name_for_role(role, "provider"), data.get("provider"), defaults.get("provider", parent_provider)))
    model = str(_choose(_env_name_for_role(role, "model"), data.get("model"), defaults.get("model", "")))
    api_key = str(_choose(_env_name_for_role(role, "api_key"), data.get("api_key"), defaults.get("api_key", "")))
    base_url = str(_choose(_env_name_for_role(role, "base_url"), data.get("base_url"), defaults.get("base_url", "")))
    return ModelRoleConfig(
        enabled=bool(data.get("enabled", defaults.get("enabled", True))),
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=float(_choose(_env_name_for_role(role, "temperature"), data.get("temperature"), defaults.get("temperature", 0.2))),
        max_tokens=int(_choose(_env_name_for_role(role, "max_tokens"), data.get("max_tokens"), defaults.get("max_tokens", 2048))),
        enable_thinking=bool(data.get("enable_thinking", defaults.get("enable_thinking", False))),
        multimodal=bool(data.get("multimodal", defaults.get("multimodal", False))),
    )


def load_config(path: Path | str = "config.toml") -> AppConfig:
    path = Path(path)
    data: dict[str, Any] = {}
    if path.exists():
        with path.open("rb") as f:
            data = tomllib.load(f)

    app_data = data.get("app", {})
    llm_data = data.get("llm", {})
    llm_main = llm_data.get("main", {}) if isinstance(llm_data, dict) else {}
    agent_data = data.get("agent", {})
    tools_data = data.get("tools", {})
    memory_data = data.get("memory", {})
    tracing_data = data.get("tracing", {})
    proactive_data = data.get("proactive", {})
    drift_data = data.get("drift", {})

    workspace = Path(_resolve_env(app_data.get("workspace", os.getenv("COGITO_WORKSPACE", "workspace"))))
    if not workspace.is_absolute():
        workspace = Path.cwd() / workspace

    parent_provider = str(_choose("LLM_PROVIDER", llm_data.get("provider"), "openai_compatible"))
    role_defaults: dict[str, dict[str, Any]] = {
        "main": {"model": "deepseek-chat", "base_url": "https://api.deepseek.com", "temperature": 0.2, "max_tokens": 2048},
        "fast": {"enabled": True, "model": "deepseek-chat", "base_url": "https://api.deepseek.com", "temperature": 0.0, "max_tokens": 1024},
        "reasoning": {"enabled": False, "model": "deepseek-reasoner", "base_url": "https://api.deepseek.com", "temperature": 0.2, "max_tokens": 4096},
        "summarizer": {"enabled": True, "model": "deepseek-chat", "base_url": "https://api.deepseek.com", "temperature": 0.1, "max_tokens": 2048},
        "judge": {"enabled": True, "model": "deepseek-chat", "base_url": "https://api.deepseek.com", "temperature": 0.0, "max_tokens": 1024},
        "embedding": {"enabled": False, "model": "text-embedding-v3", "base_url": "", "temperature": 0.0, "max_tokens": 0},
        "multimodal": {"enabled": False, "model": "", "base_url": "", "temperature": 0.2, "max_tokens": 2048, "multimodal": True},
        "vision": {"enabled": False, "model": "", "base_url": "", "temperature": 0.2, "max_tokens": 2048, "multimodal": True},
        "reranker": {"enabled": False, "model": "", "base_url": "", "temperature": 0.0, "max_tokens": 512},
    }
    role_names = sorted(set(role_defaults) | {key for key, value in llm_data.items() if isinstance(value, dict)})
    roles = {
        role: _role_config(
            role=role,
            data=llm_data.get(role, {}) if isinstance(llm_data.get(role), dict) else {},
            parent_provider=parent_provider,
            defaults=role_defaults.get(role, {}),
        )
        for role in role_names
    }
    main_role = roles["main"]
    llm = LLMConfig(
        provider=parent_provider,
        model=main_role.model,
        api_key=main_role.api_key,
        base_url=main_role.base_url,
        temperature=main_role.temperature,
        max_tokens=main_role.max_tokens,
        roles=roles,
    )

    return AppConfig(
        workspace=workspace,
        debug=bool(app_data.get("debug", False)),
        llm=llm,
        agent=AgentConfig(
            max_iterations=int(agent_data.get("max_iterations", 8)),
            memory_window=int(agent_data.get("memory_window", _get_nested(agent_data, "context", "memory_window", default=40))),
        ),
        tools=ToolsConfig(
            enable_filesystem=bool(tools_data.get("enable_filesystem", True)),
            enable_web=bool(tools_data.get("enable_web", False)),
            enable_shell=bool(tools_data.get("enable_shell", False)),
            require_approval_for_write=bool(tools_data.get("require_approval_for_write", False)),
        ),
        memory=MemoryConfig(
            enabled=bool(memory_data.get("enabled", True)),
            top_k=int(memory_data.get("top_k", 5)),
        ),
        tracing=TracingConfig(
            enabled=bool(tracing_data.get("enabled", True)),
            store=str(tracing_data.get("store", "jsonl")),
            redact_sensitive=bool(tracing_data.get("redact_sensitive", True)),
            save_prompt_hash=bool(tracing_data.get("save_prompt_hash", True)),
            save_prompt_preview=bool(tracing_data.get("save_prompt_preview", True)),
            otel_enabled=bool(tracing_data.get("otel_enabled", False)),
            otel_service_name=str(tracing_data.get("otel_service_name", "cogito-agent")),
        ),
        proactive=ProactiveConfig(
            enabled=bool(proactive_data.get("enabled", False)),
            threshold=float(proactive_data.get("threshold", 0.6)),
            daily_limit=int(proactive_data.get("daily_limit", 5)),
            cooldown_seconds=int(proactive_data.get("cooldown_seconds", 3600)),
            quiet_hours=str(proactive_data.get("quiet_hours", "")),
        ),
        drift=DriftConfig(
            enabled=bool(drift_data.get("enabled", False)),
            max_steps=int(drift_data.get("max_steps", 30)),
            min_interval_hours=float(drift_data.get("min_interval_hours", 1.0)),
        ),
    )
