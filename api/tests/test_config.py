from app.config import load_settings


def test_defaults_when_values_empty(tmp_path, monkeypatch):
    for k in ["AWS_BEDROCK_ACCESS_KEY_ID", "AWS_BEDROCK_REGION", "AWS_BEDROCK_MODEL",
              "RENDER_QUALITY", "ELEVENLABS_VOICE_ID", "DATA_DIR"]:
        monkeypatch.delenv(k, raising=False)
    env = tmp_path / ".env"
    env.write_text("AWS_BEDROCK_ACCESS_KEY_ID=abc\nAWS_BEDROCK_REGION=\nAWS_BEDROCK_MODEL=\n")
    s = load_settings(env)
    assert s.bedrock_access_key_id == "abc"
    assert s.bedrock_region == "us-east-1"
    assert s.bedrock_model == "zai.glm-5"
    assert s.render_quality == "m"
    assert s.elevenlabs_voice_id == "JBFqnCBsd6RMkjVDRZzb"
    assert s.data_dir.name == "data"


def test_env_values_override(tmp_path, monkeypatch):
    monkeypatch.setenv("RENDER_QUALITY", "l")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "d"))
    s = load_settings(tmp_path / "missing.env")
    assert s.render_quality == "l" and s.data_dir == tmp_path / "d"


def test_assessment_models_and_concurrency(tmp_path, monkeypatch):
    for k in ["AWS_BEDROCK_VISION_MODEL", "AWS_BEDROCK_VERIFY_MODEL", "AWS_BEDROCK_GRADING_MODEL", "GRADING_CONCURRENCY"]:
        monkeypatch.delenv(k, raising=False)
    s = load_settings(tmp_path / "missing.env")
    assert s.vision_model == "qwen.qwen3-vl-235b-a22b"
    assert s.verify_model == "moonshotai.kimi-k2.5"
    assert s.grading_model == "" and s.grading_concurrency == 6
    monkeypatch.setenv("AWS_BEDROCK_VERIFY_MODEL", "")  # set but empty: the second reading is off
    monkeypatch.setenv("GRADING_CONCURRENCY", "3")
    s = load_settings(tmp_path / "missing.env")
    assert s.verify_model == "" and s.grading_concurrency == 3


def test_concurrency_must_be_a_sane_number(tmp_path, monkeypatch):
    import pytest

    monkeypatch.setenv("GRADING_CONCURRENCY", "0")
    with pytest.raises(ValueError, match="GRADING_CONCURRENCY"):
        load_settings(tmp_path / "missing.env")
