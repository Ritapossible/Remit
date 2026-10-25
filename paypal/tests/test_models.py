import json

import httpx
import pytest

from remit_paypal.models import ChatModel
from remit_paypal.panel import Panel


def transport(answer=None, status=200):
    seen = []

    def handle(request):
        seen.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer k"
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "rate limited"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": answer}}]})
    return httpx.MockTransport(handle), seen


def test_a_chat_model_sends_the_prompt_at_temperature_zero():
    t, seen = transport('{"verdict": "in_remit", "confidence": 80}')
    m = ChatModel("vendor/model-x", "k", base_url="https://example.test/v1", transport=t)
    assert "in_remit" in m("the prompt")
    assert seen[0]["model"] == "vendor/model-x" and seen[0]["temperature"] == 0
    assert seen[0]["messages"] == [{"role": "user", "content": "the prompt"}]


def test_a_failing_model_is_a_doubt_on_the_panel_not_a_crash():
    bad, _ = transport(status=429)
    good, _ = transport('{"verdict": "in_remit", "confidence": 90}')
    panel = Panel({"a": ChatModel("a", "k", base_url="https://example.test/v1", transport=bad),
                   "b": ChatModel("b", "k", base_url="https://example.test/v1", transport=good)}, quorum=2)
    verdict, votes = panel.decide("q")
    assert verdict == "undetermined" and votes[0].error.startswith("HTTPStatusError")


def test_a_model_needs_a_key():
    with pytest.raises(ValueError):
        ChatModel("m", "")
