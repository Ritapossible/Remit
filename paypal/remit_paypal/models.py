"""Models behind any OpenAI-compatible chat API (OpenRouter, OpenAI, Qwen's
Model Studio, a local server). One key can give the panel several models."""

import re
import time

import httpx

DEFAULT_BASE = "https://openrouter.ai/api/v1"
THINK = re.compile(r"<think>.*?(</think>|$)", re.S)


MAX_WAIT = 20.0  # seconds a rate-limited call may wait before trying again


def retry_after(response):
    """How long a rate-limited API asks us to wait, in seconds, or None if it
    asks for longer than we will wait. Read from the Retry-After header, or
    from the message ("Please try again in 10.9s"), as Groq writes it."""
    if response.status_code != 429:
        return None
    wait = None
    try:
        wait = float(response.headers.get("retry-after", ""))
    except ValueError:
        m = re.search(r"try again in ([0-9.]+)\s*(ms|s)\b", response.text)
        if m:
            wait = float(m.group(1)) / (1000 if m.group(2) == "ms" else 1)
    wait = 2.0 if wait is None else wait + 0.5
    return wait if wait <= MAX_WAIT else None


def without_thinking(text):
    """A reasoning model's answer without its ``<think>`` block (Qwen3 and
    others write one before the answer). An unclosed block is all thinking."""
    return THINK.sub("", text or "").strip()


class ChatModel:
    """A callable: prompt in, the model's raw text out. Temperature 0, so a
    re-run of the same case is as close to repeatable as the model allows.
    Errors propagate; the panel counts them as doubt."""

    def __init__(self, model, api_key, base_url=DEFAULT_BASE, timeout=45.0, transport=None, max_tokens=2000,
                 sleep=None):
        if not api_key:
            raise ValueError("a model API key is required")
        self.model, self.max_tokens = model, max_tokens
        self.sleep = sleep or time.sleep
        self.http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport,
                                 headers={"Authorization": "Bearer " + api_key})

    def __call__(self, prompt):
        body = {"model": self.model, "temperature": 0, "max_tokens": self.max_tokens,
                "messages": [{"role": "user", "content": prompt}]}
        r = self.http.post("/chat/completions", json=body)
        for _ in range(2):  # rate limited: wait as asked, twice at most
            wait = retry_after(r)
            if wait is None:
                break
            self.sleep(wait)
            r = self.http.post("/chat/completions", json=body)
        r.raise_for_status()
        return without_thinking(r.json()["choices"][0]["message"]["content"])
