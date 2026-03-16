from pathlib import Path


def test_env_example_mentions_glm_and_openai() -> None:
    content = Path(".env.example").read_text()
    assert "GLM_API_KEY" in content
    assert "OPENAI_API_KEY" not in content
