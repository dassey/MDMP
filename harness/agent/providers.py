"""Pluggable option providers.

Four providers, one contract. Every one of them answers the same question —
"give me N candidate options for this field" — and returns the same shape, so
the rest of the harness never learns which one ran.

  offline    doctrinal templates. No model, no network, no GPU. Always works.
  ollama     a local Ollama server (http://localhost:11434).
  openai     any OpenAI-compatible local server: LM Studio, llama.cpp's
             server, vLLM, GPT4All's API server.
  anthropic  the Claude API via the official `anthropic` SDK.

The first three are what you use on a disconnected laptop. The fourth is for
when the machine has internet and you want the strongest drafting.

Configuration lives in the database (Settings page) or these environment
variables:

  MDMP_PROVIDER        offline | ollama | openai | anthropic
  MDMP_MODEL           model name for the selected provider
  MDMP_BASE_URL        base URL for ollama / openai providers
  ANTHROPIC_API_KEY    for the anthropic provider
"""

import json
import os
import urllib.error
import urllib.request

from harness.mdmp import generators

# Model defaults. Local models are chosen for CPU-first laptops: 7-8B
# parameters at 4-bit quantisation, which fits in about 5 GB of RAM and
# generates faster than a person reads.
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b-instruct"
DEFAULT_OPENAI_MODEL = "local-model"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"

OPTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "options": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "value": {"type": "string"},
                    "rationale": {"type": "string"},
                    "flags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["label", "value", "rationale", "flags"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["options"],
    "additionalProperties": False,
}


class ProviderError(Exception):
    pass


class Provider:
    name = "base"

    def available(self):
        return False

    def describe(self):
        return self.name

    def options(self, system, user, n):
        raise NotImplementedError


# ----------------------------------------------------------------- offline --

class OfflineProvider(Provider):
    name = "offline"

    def available(self):
        return True

    def describe(self):
        return "Offline doctrinal templates"

    def options(self, system, user, n):
        # Not used: the engine calls generators directly for this provider.
        return []


# ------------------------------------------------------------------ ollama --

def _http_json(url, payload, timeout=180, headers=None):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        raise ProviderError("HTTP %s from %s: %s" % (e.code, url, body))
    except Exception as e:
        raise ProviderError("%s: %s" % (url, e))


def _http_get(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        raise ProviderError("%s: %s" % (url, e))


class OllamaProvider(Provider):
    """Local Ollama server. Fully offline once the model is pulled."""

    name = "ollama"

    def __init__(self, base_url=None, model=None):
        self.base = (base_url or "http://localhost:11434").rstrip("/")
        self.model = model or DEFAULT_OLLAMA_MODEL

    def available(self):
        try:
            _http_get(self.base + "/api/tags", timeout=3)
            return True
        except ProviderError:
            return False

    def describe(self):
        return "Ollama %s (%s)" % (self.model, self.base)

    def models(self):
        try:
            data = json.loads(_http_get(self.base + "/api/tags", timeout=5))
            return [m.get("name") for m in data.get("models", [])]
        except Exception:
            return []

    def options(self, system, user, n):
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "options": {"num_predict": 2048},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        data = _http_json(self.base + "/api/chat", payload)
        return _parse_options(data.get("message", {}).get("content", ""))


# ---------------------------------------------------- OpenAI-compatible ----

class OpenAICompatProvider(Provider):
    """LM Studio, llama.cpp server, vLLM, GPT4All API server."""

    name = "openai"

    def __init__(self, base_url=None, model=None, api_key=None):
        self.base = (base_url or "http://localhost:1234/v1").rstrip("/")
        self.model = model or DEFAULT_OPENAI_MODEL
        self.api_key = api_key or os.environ.get("MDMP_API_KEY", "not-needed")

    def available(self):
        try:
            _http_get(self.base + "/models", timeout=3)
            return True
        except ProviderError:
            return False

    def describe(self):
        return "OpenAI-compatible %s (%s)" % (self.model, self.base)

    def options(self, system, user, n):
        payload = {
            "model": self.model,
            "max_tokens": 2048,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        data = _http_json(self.base + "/chat/completions", payload,
                          headers={"Authorization": "Bearer " + self.api_key})
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("no choices returned")
        return _parse_options(choices[0].get("message", {}).get("content", ""))


# --------------------------------------------------------------- anthropic --

class AnthropicProvider(Provider):
    """Claude API through the official SDK.

    Requires `pip install anthropic` and an API key. The rest of the harness
    has no third-party dependencies; this provider is the one opt-in.
    """

    name = "anthropic"

    def __init__(self, model=None, api_key=None):
        self.model = model or DEFAULT_ANTHROPIC_MODEL
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = None

    def _sdk(self):
        try:
            import anthropic  # noqa: F401
            return anthropic
        except ImportError:
            raise ProviderError(
                "the anthropic package is not installed — run "
                "`pip install anthropic`, or use a local provider")

    def available(self):
        try:
            self._sdk()
        except ProviderError:
            return False
        return bool(self.api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def describe(self):
        return "Claude API (%s)" % self.model

    def client(self):
        if self._client is None:
            anthropic = self._sdk()
            if self.api_key:
                self._client = anthropic.Anthropic(api_key=self.api_key)
            else:
                self._client = anthropic.Anthropic()
        return self._client

    def options(self, system, user, n):
        try:
            resp = self.client().messages.create(
                model=self.model,
                max_tokens=8000,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={
                    "effort": "medium",
                    "format": {"type": "json_schema", "schema": OPTIONS_SCHEMA},
                },
            )
        except Exception as e:
            raise ProviderError(str(e))
        if getattr(resp, "stop_reason", None) == "refusal":
            raise ProviderError("request was declined by the model provider")
        text = ""
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                text += block.text
        return _parse_options(text)


# ------------------------------------------------------------------ shared --

def _parse_options(text):
    """Pull the options array out of whatever the model returned."""
    if not text:
        raise ProviderError("empty response")
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ProviderError("response was not JSON")
        try:
            data = json.loads(text[start:end + 1])
        except ValueError as e:
            raise ProviderError("could not parse JSON: %s" % e)
    items = data.get("options") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ProviderError("no options array in response")
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        value = it.get("value", "")
        out.append({
            "label": (str(it.get("label") or "").strip()[:120]
                      or "Option"),
            "value": value,
            "rationale": str(it.get("rationale") or ""),
            "flags": [str(f) for f in (it.get("flags") or [])][:5],
        })
    if not out:
        raise ProviderError("options array was empty")
    return out


def build(name=None, base_url=None, model=None, api_key=None):
    name = (name or os.environ.get("MDMP_PROVIDER") or "offline").lower()
    base_url = base_url or os.environ.get("MDMP_BASE_URL")
    model = model or os.environ.get("MDMP_MODEL")
    if name == "ollama":
        return OllamaProvider(base_url, model)
    if name in ("openai", "openai_compat", "lmstudio", "llamacpp"):
        return OpenAICompatProvider(base_url, model, api_key)
    if name in ("anthropic", "claude"):
        return AnthropicProvider(model, api_key)
    return OfflineProvider()


def detect():
    """Probe for locally reachable providers. Used by the settings page."""
    found = [{"name": "offline", "describe": "Offline doctrinal templates",
              "available": True}]
    oll = OllamaProvider()
    found.append({"name": "ollama", "describe": oll.describe(),
                  "available": oll.available(), "models": oll.models()})
    for url in ("http://localhost:1234/v1", "http://localhost:8080/v1",
                "http://localhost:4891/v1"):
        p = OpenAICompatProvider(url)
        if p.available():
            found.append({"name": "openai", "describe": p.describe(),
                          "available": True, "base_url": url})
            break
    else:
        found.append({"name": "openai",
                      "describe": "OpenAI-compatible server (not detected)",
                      "available": False,
                      "base_url": "http://localhost:1234/v1"})
    ant = AnthropicProvider()
    found.append({"name": "anthropic", "describe": ant.describe(),
                  "available": ant.available()})
    return found


def offline_options(gen_key, ctx, n):
    return generators.generate(gen_key, ctx, n)
