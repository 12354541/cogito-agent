from __future__ import annotations

from cogito_agent.config import load_config


def test_load_config_reads_model_roles(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[llm]
provider = "openai_compatible"

[llm.main]
model = "deepseek-chat"
api_key = "${LLM_API_KEY}"
base_url = "https://api.deepseek.com"

[llm.embedding]
enabled = false
model = "text-embedding-v3"
api_key = "${EMBEDDING_API_KEY}"
base_url = "${EMBEDDING_BASE_URL}"

[llm.multimodal]
enabled = false
model = "${MULTIMODAL_LLM_MODEL}"
api_key = "${MULTIMODAL_LLM_API_KEY}"
base_url = "${MULTIMODAL_LLM_BASE_URL}"
multimodal = true

[tracing]
store = "sqlite"
save_prompt_preview = false
otel_enabled = true
otel_service_name = "cogito-test"

[tools]
enable_web = true
enable_shell = false

[proactive]
enabled = true
threshold = 0.75
daily_limit = 2
cooldown_seconds = 60
quiet_hours = "22:00-07:00"

[drift]
enabled = true
max_steps = 12
min_interval_hours = 0.5
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.llm.model == "deepseek-chat"
    assert config.llm.api_key == "test-key"
    assert config.llm.roles["embedding"].model == "text-embedding-v3"
    assert config.llm.roles["multimodal"].multimodal is True
    assert config.tracing.store == "sqlite"
    assert config.tracing.save_prompt_preview is False
    assert config.tracing.otel_enabled is True
    assert config.tracing.otel_service_name == "cogito-test"
    assert config.tools.enable_web is True
    assert config.tools.enable_shell is False
    assert config.proactive.enabled is True
    assert config.proactive.threshold == 0.75
    assert config.proactive.daily_limit == 2
    assert config.proactive.cooldown_seconds == 60
    assert config.proactive.quiet_hours == "22:00-07:00"
    assert config.drift.enabled is True
    assert config.drift.max_steps == 12
    assert config.drift.min_interval_hours == 0.5
