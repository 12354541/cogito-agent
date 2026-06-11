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
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.llm.model == "deepseek-chat"
    assert config.llm.api_key == "test-key"
    assert config.llm.roles["embedding"].model == "text-embedding-v3"
    assert config.llm.roles["multimodal"].multimodal is True
