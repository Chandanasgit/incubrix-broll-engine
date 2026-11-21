import os
import re

import httpx

PROMPT_VERSION = "q1"


class LLMError(Exception):
    """The query-writing LLM failed or returned something unusable."""


SYSTEM = (
    "You write search phrases for a stock-footage library. Given one sentence of narration, "
    "reply with 2 or 3 short phrases (2 to 5 words each) describing concrete things a camera could film "
    "that illustrate the sentence. Rules: describe visuals, not ideas; never use the name of a real person "
    "or brand, describe a generic visual instead; for sad or sensitive news use calm, respectful visuals "
    "such as a quiet street or rain on a window, never graphic ones; pick the right meaning of words with "
    "double meanings (bank, cloud, mouse, python). Output one phrase per line and nothing else."
)


def build_prompt(text, avoid=None):
    p = "Sentence: " + text.strip()
    if avoid:
        p += "\nNever show or mention: " + ", ".join(avoid)
    return p


def parse_queries(raw, avoid=None, max_queries=3):
    out = []
    for line in (raw or "").splitlines():
        q = re.sub(r"^[\s\-\*\d\.\)\"'`]+", "", line).strip().strip("\"'`").lower()
        q = " ".join(re.sub(r"[^a-z0-9 ]", " ", q).split())
        n = len(q.split())
        if n < 1 or n > 6:
            continue
        if any(t.lower().strip() and t.lower().strip() in q for t in (avoid or [])):
            continue
        if q not in out:
            out.append(q)
    return out[:max_queries]


def merge_queries(llm_queries, rule_queries, keep_rules=1):
    out = []
    for q in list(llm_queries) + list(rule_queries)[:keep_rules]:
        if q and q not in out:
            out.append(q)
    return out


class GeminiQueryWriter:
    name = "gemini"

    def __init__(self, api_key=None, model=None, transport=None, timeout=None):
        self.api_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")
        self.model = model or os.getenv("GEMINI_MODEL", "")
        self.base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
        self.timeout = float(timeout or os.getenv("LLM_TIMEOUT_SECONDS", "15"))
        self._client = httpx.Client(timeout=self.timeout, transport=transport)

    def _clean(self, s):
        return s.replace(self.api_key, "***") if self.api_key else s

    def write(self, text, avoid=None):
        if not self.api_key or not self.model:
            raise LLMError("GEMINI_API_KEY or GEMINI_MODEL is not set")
        body = {
            "systemInstruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"parts": [{"text": build_prompt(text, avoid)}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 300},
        }
        url = "%s/models/%s:generateContent" % (self.base_url, self.model)
        try:
            resp = self._client.post(url, headers={"x-goog-api-key": self.api_key}, json=body)
            resp.raise_for_status()
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        except httpx.HTTPError as exc:
            raise LLMError(self._clean("request failed: " + str(exc)))
        except (KeyError, IndexError, TypeError, ValueError):
            raise LLMError("unexpected response format")
        queries = parse_queries(raw, avoid)
        if not queries:
            raise LLMError("no usable queries in the response")
        return {"queries": queries, "model": self.model, "prompt_version": PROMPT_VERSION, "raw": raw[:200]}


class MockQueryWriter:
    name = "mock"
    model = "mock"

    def write(self, text, avoid=None):
        words = re.findall(r"[a-z]+", text.lower())[:2]
        return {"queries": [" ".join(words) or "abstract background"], "model": "mock",
                "prompt_version": PROMPT_VERSION, "raw": ""}


REGISTRY = {"gemini": GeminiQueryWriter, "mock": MockQueryWriter}


def build_query_writer(name=None):
    name = (name or os.getenv("QUERY_LLM_PROVIDER", "none")).strip().lower()
    if name in ("", "none"):
        return None
    if name not in REGISTRY:
        raise ValueError("unknown QUERY_LLM_PROVIDER: " + name)
    return REGISTRY[name]()
