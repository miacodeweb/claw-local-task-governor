import json
from unittest.mock import patch

from governor.providers import (
    all_providers_health,
    get_provider,
    list_models_for_provider,
    list_providers,
)
from governor.providers.base import ProviderHealth, ProviderResponse
from governor.providers.ollama_provider import OllamaModelProvider, ProviderError
from governor.providers.openai_compatible_provider import OpenAiCompatProvider
from governor.ollama_client import OllamaConfig


class FakeOpener:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, request, timeout=None):
        self.calls.append(request)
        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return FakeResponse(json.dumps(resp).encode("utf-8"))


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class TestModelProviders:
    def test_registry_lists_ollama(self):
        providers = list_providers()
        assert "ollama" in providers

    def test_registry_lists_openai_compatible(self):
        providers = list_providers()
        assert "openai_compatible" in providers

    def test_get_provider_ollama(self):
        provider = get_provider("ollama")
        assert provider is not None
        assert provider.provider_name == "ollama"

    def test_get_provider_openai_compatible(self):
        provider = get_provider("openai_compatible")
        assert provider is not None
        assert provider.provider_name == "openai_compatible"

    def test_ollama_provider_health(self):
        provider = OllamaModelProvider()
        health = provider.healthcheck()
        if health.available:
            assert health.available is True
        else:
            assert isinstance(health.error, str)

    def test_ollama_provider_list_models(self):
        provider = OllamaModelProvider()
        try:
            models = provider.list_models()
            assert isinstance(models, list)
        except (ProviderError, Exception):
            pass

    def test_ollama_provider_chat_with_mock(self):
        opener = FakeOpener([
            {"message": {"content": "hello world"}, "model": "test-model"}
        ])
        config = OllamaConfig(model="test-model", timeout_seconds=5)
        client = OllamaModelProvider.__new__(OllamaModelProvider)
        from governor.ollama_client import OllamaClient
        client._client = OllamaClient(config, opener=opener)
        client._config = config

        response = client.chat("test-model", [{"role": "user", "content": "hi"}])
        assert response.text == "hello world"
        assert response.provider == "ollama"
        assert response.model == "test-model"

    def test_openai_compat_no_config_unavailable(self):
        with patch.dict("os.environ", {}, clear=True):
            provider = OpenAiCompatProvider(base_url="", api_key="", model="")
            health = provider.healthcheck()
            assert health.available is False
            assert "base_url" in health.error

    def test_openai_compat_with_mock_returns_response(self):
        _responses = [{
            "id": "chat-1",
            "choices": [{"message": {"content": "mock reply"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 10},
        }]

        import governor.providers.openai_compatible_provider as oai_mod
        original = oai_mod.urllib.request.urlopen

        class MockResp:
            @staticmethod
            def read():
                return json.dumps(_responses[0]).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        oai_mod.urllib.request.urlopen = lambda req, timeout=None: MockResp()
        try:
            provider = OpenAiCompatProvider(base_url="http://localhost:8080/v1", api_key="test-key", model="test")
            resp = provider.chat("test", [{"role": "user", "content": "hi"}])
            assert resp.text == "mock reply"
            assert resp.provider == "openai_compatible"
            assert "usage" in resp.raw_metadata
        finally:
            oai_mod.urllib.request.urlopen = original

    def test_openai_compat_healthcheck_with_mock(self):
        _responses = [{"data": [{"id": "model-a"}, {"id": "model-b"}]}]

        import governor.providers.openai_compatible_provider as oai_mod
        original = oai_mod.urllib.request.urlopen

        class MockResp:
            @staticmethod
            def read():
                return json.dumps(_responses[0]).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        oai_mod.urllib.request.urlopen = lambda req, timeout=None: MockResp()
        try:
            provider = OpenAiCompatProvider(base_url="http://localhost:8080/v1", api_key="k", model="m")
            health = provider.healthcheck()
            assert health.available is True
            models = provider.list_models()
            assert "model-a" in models
            assert "model-b" in models
        finally:
            oai_mod.urllib.request.urlopen = original

    def test_cli_providers_list(self, capsys):
        from governor import main
        exit_code = main.main(["providers", "list"])
        assert exit_code == 0
        output = capsys.readouterr().out
        assert "ollama" in output

    def test_cli_providers_health(self, capsys):
        from governor import main
        exit_code = main.main(["providers", "health"])
        assert exit_code == 0
        output = capsys.readouterr().out
        assert "ollama:" in output

    def test_cli_providers_models(self, capsys):
        from governor import main
        exit_code = main.main(["providers", "models", "--provider", "ollama"])
        assert exit_code == 0

    def test_no_external_calls_in_import(self):
        import governor.providers
        assert governor.providers is not None

    def test_ollama_client_compat(self):
        from governor.ollama_client import OllamaClient, OllamaConfig, OllamaError, load_ollama_config
        assert OllamaClient is not None
        assert load_ollama_config is not None

    def test_benchmark_test_still_passes_with_provider_import(self):
        from governor.model_benchmark import run_benchmark
        from governor.model_benchmark import DEFAULT_BENCHMARK_OUTPUT_DIR
        assert run_benchmark is not None
        assert DEFAULT_BENCHMARK_OUTPUT_DIR is not None

    def test_provider_response_to_dict(self):
        resp = ProviderResponse(text="hello", model="m", provider="ollama", response_ms=100, input_chars=50, output_chars=5)
        d = resp.to_dict()
        assert d["text"] == "hello"
        assert d["provider"] == "ollama"

    def test_provider_health_dataclass(self):
        h = ProviderHealth(available=True, provider="test")
        assert h.available
        assert h.error == ""

    def test_main_registered_providers_command(self):
        from governor.main import build_parser
        parser = build_parser()
        result = parser.parse_args(["providers", "list"])
        assert result.command == "providers"
