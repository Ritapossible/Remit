"""Models behind any OpenAI-compatible chat API (OpenRouter, OpenAI, Qwen's
Model Studio, a local server). One key can give the panel several models."""

import httpx

DEFAULT_BASE = "https://openrouter.ai/api/v1"


class ChatModel:
    """A callable: prompt in, the model's raw text out. Temperature 0, so a
    re-run of the same case is as close to repeatable as the model allows.
    Errors propagate; the panel counts them as doubt."""

    def __init__(self, model, api_key, base_url=DEFAULT_BASE, timeout=45.0, transport=None, max_tokens=300):
        if not api_key:
            raise ValueError("a model API key is required")
        self.model, self.max_tokens = model, max_tokens
        self.http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport,
                                 headers={"Authorization": "Bearer " + api_key})

    def __call__(self, prompt):
        r = self.http.post("/chat/completions", json={
            "model": self.model,
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        })
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"] or ""
