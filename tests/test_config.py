from docintel.config import Settings


def test_settings_load_without_env(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    s = Settings(_env_file=None, data_dir=tmp_path)
    assert s.openai_api_key is None
    assert s.data_dir == tmp_path


def test_api_key_is_masked(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
    s = Settings(_env_file=None)
    assert s.openai_api_key.get_secret_value() == "sk-test-123"
    assert "sk-test-123" not in repr(s)  # never leaks into logs
