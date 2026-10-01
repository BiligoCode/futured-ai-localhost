from app.config import load_settings


def test_defaults_when_values_empty(tmp_path, monkeypatch):
    for k in ["AWS_BEDROCK_ACCESS_KEY_ID", "AWS_BEDROCK_REGION", "AWS_BEDROCK_MODEL",
              "RENDER_QUALITY", "ELEVENLABS_VOICE_ID", "DATA_DIR"]:
        monkeypatch.delenv(k, raising=False)
    env = tmp_path / ".env"
    env.write_text("AWS_BEDROCK_ACCESS_KEY_ID=abc\nAWS_BEDROCK_REGION=\nAWS_BEDROCK_MODEL=\n")
    s = load_settings(env)
    assert s.bedrock_access_key_id == "abc"
    assert s.bedrock_region == "eu-central-1"
    assert s.bedrock_model == "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"
    assert s.render_quality == "m"
    assert s.elevenlabs_voice_id == "JBFqnCBsd6RMkjVDRZzb"
    assert s.data_dir.name == "data"


def test_env_values_override(tmp_path, monkeypatch):
    monkeypatch.setenv("RENDER_QUALITY", "l")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "d"))
    s = load_settings(tmp_path / "missing.env")
    assert s.render_quality == "l" and s.data_dir == tmp_path / "d"
