from __future__ import annotations
import json, os, time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from .base import ProviderError, ProviderTimeoutError

class OllamaProvider:
    """Minimal Ollama /api/generate adapter using stdlib only."""
    def __init__(self, base_url: str | None = None, model: str | None = None,
                 connect_timeout: float | None = None, inference_timeout: float | None = None,
                 retries: int | None = None, max_output_chars: int | None = None):
        self.base_url = (base_url or os.getenv("SENTINEL_OLLAMA_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.model = model or os.getenv("SENTINEL_MODEL", "qwen2.5-coder:7b")
        self.connect_timeout = connect_timeout or float(os.getenv("SENTINEL_CONNECT_TIMEOUT", "3"))
        self.inference_timeout = inference_timeout or float(os.getenv("SENTINEL_INFERENCE_TIMEOUT", "280"))
        self.retries = retries if retries is not None else int(os.getenv("SENTINEL_PROVIDER_RETRIES", "0"))
        self.max_output_chars = max_output_chars or int(os.getenv("SENTINEL_MAX_OUTPUT_CHARS", "40000"))
        if not self.base_url.startswith(("http://", "https://")) or not self.model.strip():
            raise ValueError("Invalid Ollama URL or model configuration")
        if min(self.connect_timeout, self.inference_timeout) <= 0 or self.retries < 0:
            raise ValueError("Timeouts must be positive and retries non-negative")

    def health(self) -> bool:
        try:
            req = Request(self.base_url + "/api/tags", headers={"Accept": "application/json"})
            with urlopen(req, timeout=self.connect_timeout) as response:
                return response.status == 200
        except Exception:
            return False

    def generate(self, prompt: str, format_schema: dict | None = None) -> str:
        proposal_schema = format_schema or {
            "type": "object", "additionalProperties": False,
            "properties": {
                "root_cause": {"type": "string"},
                "explanation": {"type": "string"},
                "patch_format": {"type": "string", "const": "unified_diff"},
                "patch_text": {"type": "string"},
                "files_changed": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["root_cause", "explanation", "patch_format", "patch_text", "files_changed"],
        }
        body = json.dumps({"model": self.model, "prompt": prompt, "stream": False,
                           "format": proposal_schema,
                           "options": {"num_predict": int(os.getenv("SENTINEL_MAX_TOKENS", "350")),
                                       "repeat_penalty": 1.1,
                                       "temperature": 0}}).encode()
        req = Request(self.base_url + "/api/generate", data=body,
                      headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
        # urllib's timeout covers socket operations; bounded retries only for likely transient failures.
        for attempt in range(self.retries + 1):
            try:
                with urlopen(req, timeout=self.inference_timeout) as response:
                    raw = response.read(self.max_output_chars * 4 + 1)
                if len(raw) > self.max_output_chars * 4:
                    raise ProviderError("Provider response exceeded configured size limit")
                payload = json.loads(raw.decode("utf-8"))
                result = payload.get("response") if isinstance(payload, dict) else None
                if not isinstance(result, str) or not result.strip():
                    raise ProviderError("Provider returned an empty or malformed response")
                if len(result) > self.max_output_chars:
                    raise ProviderError("Provider response exceeded configured size limit")
                return result
            except HTTPError as exc:
                if exc.code not in (408, 425, 429, 500, 502, 503, 504) or attempt >= self.retries:
                    raise ProviderError(f"Ollama request failed (HTTP {exc.code})") from None
            except TimeoutError:
                if attempt >= self.retries:
                    raise ProviderTimeoutError("Ollama inference timed out") from None
            except URLError as exc:
                if attempt >= self.retries:
                    if isinstance(exc.reason, TimeoutError):
                        raise ProviderTimeoutError("Ollama inference timed out") from None
                    raise ProviderError("Ollama unavailable") from None
            except (ConnectionError, OSError):
                if attempt >= self.retries:
                    raise ProviderError("Ollama unavailable") from None
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ProviderError("Ollama returned malformed JSON") from None
            time.sleep(min(0.25 * (2 ** attempt), 1.0))
        raise ProviderError("Ollama request failed")
