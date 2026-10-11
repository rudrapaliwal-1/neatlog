import json
from unittest.mock import patch
from agent.providers.ollama import OllamaProvider
from agent.providers.base import ProviderError

class FakeResponse:
    status = 200
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, n=-1): return self.body

def test_ollama_parses_realistic_response():
    p = OllamaProvider(base_url="http://localhost:11434", model="qwen2.5-coder:7b", retries=0)
    with patch("agent.providers.ollama.urlopen", return_value=FakeResponse(json.dumps({"response":"{\"ok\":true}"}).encode())):
        assert p.generate("prompt") == '{"ok":true}'

def test_ollama_sanitizes_connection_error():
    p = OllamaProvider(base_url="http://localhost:11434", retries=0)
    with patch("agent.providers.ollama.urlopen", side_effect=OSError("secret prompt leaked")):
        try: p.generate("prompt")
        except ProviderError as e: assert "secret prompt" not in str(e)
        else: assert False

def test_ollama_requests_structured_json_output():
    seen = {}
    def fake_urlopen(request, timeout):
        seen.update(json.loads(request.data.decode("utf-8")))
        return FakeResponse(json.dumps({"response": '{"ok":true}'}).encode())
    provider = OllamaProvider(base_url="http://localhost:11434", model="qwen2.5-coder:7b", retries=0)
    with patch("agent.providers.ollama.urlopen", side_effect=fake_urlopen):
        provider.generate("sanitized prompt")
    assert seen["format"]["additionalProperties"] is False
    assert set(seen["format"]["required"]) == {
        "root_cause", "explanation", "patch_format", "patch_text", "files_changed"}
    assert seen["options"]["temperature"] == 0
