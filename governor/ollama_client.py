"""Small isolated client for the native Ollama chat API."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


DEFAULT_CONFIG_PATH = Path("config.yaml")
EXAMPLE_CONFIG_PATH = Path("config.example.yaml")


@dataclass(frozen=True)
class OllamaConfig:
    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5-coder:7b"
    temperature: float = 0.1
    timeout_seconds: int = 120
    max_chars_per_file: int = 12000


class OllamaError(RuntimeError):
    """Base error for local Ollama client failures."""


class OllamaConnectionError(OllamaError):
    """Raised when Ollama is not reachable."""


class OllamaModelNotFoundError(OllamaError):
    """Raised when Ollama reports that the configured model is missing."""


class OllamaTimeoutError(OllamaError):
    """Raised when the Ollama request times out."""


class OllamaEmptyResponseError(OllamaError):
    """Raised when Ollama returns no usable assistant content."""


def load_ollama_config(config_path: Path | str | None = None) -> OllamaConfig:
    """Load Ollama config from config.yaml, config.example.yaml, or defaults."""
    path = _select_config_path(config_path)
    if path is None:
        return OllamaConfig()

    parsed = _parse_simple_yaml(path)
    ollama_config = parsed.get("ollama", {})
    return OllamaConfig(
        base_url=str(ollama_config.get("base_url", OllamaConfig.base_url)),
        model=str(ollama_config.get("model", OllamaConfig.model)),
        temperature=float(ollama_config.get("temperature", OllamaConfig.temperature)),
        timeout_seconds=int(ollama_config.get("timeout_seconds", OllamaConfig.timeout_seconds)),
        max_chars_per_file=int(ollama_config.get("max_chars_per_file", OllamaConfig.max_chars_per_file)),
    )


class OllamaClient:
    """Minimal client for http://127.0.0.1:11434/api/chat."""

    def __init__(
        self,
        config: OllamaConfig | None = None,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.config = config or load_ollama_config()
        self._opener = opener or urllib.request.urlopen

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Send chat messages to Ollama and return assistant content."""
        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
            },
        }
        request = urllib.request.Request(
            self._chat_url(),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with self._opener(request, timeout=self.config.timeout_seconds) as response:
                raw_response = response.read()
        except urllib.error.HTTPError as error:
            raise _http_error_to_ollama_error(error) from error
        except TimeoutError as error:
            raise OllamaTimeoutError("Ollama request timed out") from error
        except socket.timeout as error:
            raise OllamaTimeoutError("Ollama request timed out") from error
        except urllib.error.URLError as error:
            raise _url_error_to_ollama_error(error) from error
        except OSError as error:
            raise OllamaConnectionError(f"Ollama is not reachable: {error}") from error

        if not raw_response:
            raise OllamaEmptyResponseError("Ollama returned an empty response")

        try:
            response_data = json.loads(raw_response.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise OllamaEmptyResponseError("Ollama returned invalid JSON") from error

        content = response_data.get("message", {}).get("content")
        if not isinstance(content, str) or content.strip() == "":
            raise OllamaEmptyResponseError("Ollama returned no assistant content")

        return content

    def analyze_text_with_model(self, prompt: str, text: str) -> str:
        """Send a prompt plus bounded text to the configured local model."""
        bounded_text = text[: self.config.max_chars_per_file]
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": bounded_text},
        ]
        return self.chat(messages)

    def _chat_url(self) -> str:
        return f"{self.config.base_url.rstrip('/')}/api/chat"


def chat(messages: list[dict[str, str]], config_path: Path | str | None = None) -> str:
    """Convenience wrapper for one-off chat calls."""
    return OllamaClient(load_ollama_config(config_path)).chat(messages)


def analyze_text_with_model(
    prompt: str,
    text: str,
    config_path: Path | str | None = None,
) -> str:
    """Convenience wrapper for one-off text analysis calls."""
    return OllamaClient(load_ollama_config(config_path)).analyze_text_with_model(prompt, text)


def _select_config_path(config_path: Path | str | None) -> Path | None:
    if config_path is not None:
        path = Path(config_path)
        return path if path.exists() else None
    if DEFAULT_CONFIG_PATH.exists():
        return DEFAULT_CONFIG_PATH
    if EXAMPLE_CONFIG_PATH.exists():
        return EXAMPLE_CONFIG_PATH
    return None


def _parse_simple_yaml(path: Path) -> dict[str, dict[str, Any]]:
    """Parse the small nested key/value YAML subset used by config files."""
    data: dict[str, dict[str, Any]] = {}
    current_section: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.endswith(":") and stripped.count(":") == 1:
            current_section = stripped[:-1].strip()
            data[current_section] = {}
            continue

        if ":" not in stripped or current_section is None:
            continue

        key, value = stripped.split(":", 1)
        data[current_section][key.strip()] = _parse_scalar(value.strip())

    return data


def _parse_scalar(value: str) -> Any:
    if value.startswith(("'", '"')) and value.endswith(("'", '"')):
        return value[1:-1]
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _http_error_to_ollama_error(error: urllib.error.HTTPError) -> OllamaError:
    body = error.read().decode("utf-8", errors="replace")
    lowered = body.lower()
    if error.code == 404 or "not found" in lowered or "pull model" in lowered:
        return OllamaModelNotFoundError("Configured Ollama model was not found")
    return OllamaConnectionError(f"Ollama HTTP error {error.code}: {body}")


def _url_error_to_ollama_error(error: urllib.error.URLError) -> OllamaError:
    reason = error.reason
    if isinstance(reason, socket.timeout):
        return OllamaTimeoutError("Ollama request timed out")
    return OllamaConnectionError(f"Ollama is not reachable: {reason}")
