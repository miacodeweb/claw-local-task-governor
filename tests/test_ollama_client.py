import json
import socket
import urllib.error

import pytest

from governor.ollama_client import (
    OllamaClient,
    OllamaConfig,
    OllamaConnectionError,
    OllamaEmptyResponseError,
    OllamaHTTPError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
    OllamaUnexpectedResponseError,
    check_ollama_available,
    load_ollama_config,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.payload

    def close(self):
        return None


def test_loads_ollama_config_from_yaml(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
        ollama:
          base_url: "http://127.0.0.1:11434"
          model: "tiny-local:test"
          temperature: 0.2
          timeout_seconds: 5
          max_chars_per_file: 40
        """,
        encoding="utf-8",
    )

    config = load_ollama_config(config_path)

    assert config.base_url == "http://127.0.0.1:11434"
    assert config.model == "tiny-local:test"
    assert config.temperature == 0.2
    assert config.timeout_seconds == 5
    assert config.max_chars_per_file == 40


def test_chat_uses_native_ollama_chat_api():
    captured = {}

    def fake_open(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(b'{"message":{"role":"assistant","content":"ok"}}')

    client = OllamaClient(
        OllamaConfig(base_url="http://127.0.0.1:11434", model="demo", timeout_seconds=3),
        opener=fake_open,
    )

    response = client.chat([{"role": "user", "content": "hello"}])

    assert response == "ok"
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert "/v1" not in captured["url"]
    assert captured["timeout"] == 3
    assert captured["payload"]["model"] == "demo"
    assert captured["payload"]["stream"] is False


def test_check_ollama_available_uses_native_tags_api():
    captured = {}

    def fake_open(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        return FakeResponse(b'{"models":[]}')

    client = OllamaClient(OllamaConfig(base_url="http://127.0.0.1:11434"), opener=fake_open)

    assert client.check_ollama_available() is True
    assert captured["url"] == "http://127.0.0.1:11434/api/tags"
    assert captured["method"] == "GET"
    assert "/v1" not in captured["url"]


def test_list_models_returns_names_from_tags_api():
    def fake_open(request, timeout):
        return FakeResponse(
            b'{"models":[{"name":"qwen2.5-coder:7b"},{"name":"llama3.2:3b"},{"size":1}]}'
        )

    client = OllamaClient(OllamaConfig(), opener=fake_open)

    assert client.list_models() == ["qwen2.5-coder:7b", "llama3.2:3b"]


def test_module_check_ollama_available_uses_loaded_config(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, config):
            captured["config"] = config

        def check_ollama_available(self):
            return True

    monkeypatch.setattr("governor.ollama_client.load_ollama_config", lambda config_path: "cfg")
    monkeypatch.setattr("governor.ollama_client.OllamaClient", FakeClient)

    assert check_ollama_available("config.yaml") is True
    assert captured["config"] == "cfg"


def test_analyze_text_with_model_truncates_text():
    captured = {}

    def fake_open(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(b'{"message":{"content":"short"}}')

    client = OllamaClient(
        OllamaConfig(model="demo", max_chars_per_file=5),
        opener=fake_open,
    )

    response = client.analyze_text_with_model("system prompt", "0123456789")

    assert response == "short"
    assert captured["payload"]["messages"][0] == {"role": "system", "content": "system prompt"}
    assert captured["payload"]["messages"][1] == {"role": "user", "content": "01234"}


def test_chat_raises_connection_error_when_ollama_is_off():
    def fake_open(request, timeout):
        raise urllib.error.URLError(ConnectionRefusedError("refused"))

    client = OllamaClient(OllamaConfig(), opener=fake_open)

    with pytest.raises(OllamaConnectionError):
        client.chat([{"role": "user", "content": "hello"}])


def test_chat_raises_model_not_found_for_404():
    def fake_open(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            404,
            "not found",
            hdrs=None,
            fp=FakeResponse(b'{"error":"model not found"}'),
        )

    client = OllamaClient(OllamaConfig(), opener=fake_open)

    with pytest.raises(OllamaModelNotFoundError):
        client.chat([{"role": "user", "content": "hello"}])


def test_chat_raises_timeout_error():
    def fake_open(request, timeout):
        raise socket.timeout("timed out")

    client = OllamaClient(OllamaConfig(), opener=fake_open)

    with pytest.raises(OllamaTimeoutError):
        client.chat([{"role": "user", "content": "hello"}])


def test_chat_raises_empty_response_error():
    def fake_open(request, timeout):
        return FakeResponse(b'{"message":{"content":""}}')

    client = OllamaClient(OllamaConfig(), opener=fake_open)

    with pytest.raises(OllamaEmptyResponseError):
        client.chat([{"role": "user", "content": "hello"}])


def test_chat_raises_unexpected_response_for_invalid_json():
    def fake_open(request, timeout):
        return FakeResponse(b"not-json")

    client = OllamaClient(OllamaConfig(), opener=fake_open)

    with pytest.raises(OllamaUnexpectedResponseError):
        client.chat([{"role": "user", "content": "hello"}])


def test_chat_raises_unexpected_response_for_missing_message():
    def fake_open(request, timeout):
        return FakeResponse(b'{"response":"legacy shape"}')

    client = OllamaClient(OllamaConfig(), opener=fake_open)

    with pytest.raises(OllamaUnexpectedResponseError):
        client.chat([{"role": "user", "content": "hello"}])


def test_list_models_raises_unexpected_response_for_bad_payload():
    def fake_open(request, timeout):
        return FakeResponse(b'{"items":[]}')

    client = OllamaClient(OllamaConfig(), opener=fake_open)

    with pytest.raises(OllamaUnexpectedResponseError):
        client.list_models()


def test_http_error_raises_http_error_for_non_model_failure():
    def fake_open(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            500,
            "server error",
            hdrs=None,
            fp=FakeResponse(b'{"error":"internal"}'),
        )

    client = OllamaClient(OllamaConfig(), opener=fake_open)

    with pytest.raises(OllamaHTTPError):
        client.check_ollama_available()
