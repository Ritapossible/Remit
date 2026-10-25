"""The PayPal REST client against a simulated PayPal (httpx MockTransport):
request shapes, token handling, retries, idempotency, and the facts built
from PayPal's own response shapes."""

import json

import httpx
import pytest

from remit_paypal.paypal_api import PayPalError, RestPayPal

ORDER = {
    "id": "5O190127TN364715T",
    "status": "COMPLETED",
    "payer": {"payer_id": "QYR5Z8XDVJNXQ", "name": {"given_name": "John", "surname": "Doe"}},
    "purchase_units": [{
        "items": [{"name": "T-Shirt", "quantity": "1", "unit_amount": {"currency_code": "USD", "value": "45.00"}}],
        "payments": {
            "captures": [{"id": "3C679366HH908993F", "status": "COMPLETED",
                          "amount": {"currency_code": "USD", "value": "45.00"}, "create_time": "2026-10-20T10:00:00Z"}],
            "refunds": [{"id": "R1", "status": "COMPLETED", "amount": {"currency_code": "USD", "value": "5.00"}}],
        },
    }],
}


class FakeServer:
    def __init__(self):
        self.calls = []
        self.token_calls = 0
        self.fail = {}  # path -> list of status codes to answer first
        self.refunds = {}

    def __call__(self, request):
        path = request.url.path
        self.calls.append((request.method, path, dict(request.url.params), dict(request.headers),
                           request.content.decode() if request.content else ""))
        if path == "/v1/oauth2/token":
            self.token_calls += 1
            assert request.headers["authorization"].startswith("Basic ")
            return httpx.Response(200, json={"access_token": "T%d" % self.token_calls, "expires_in": 32400})
        assert request.headers["authorization"].startswith("Bearer ")
        queue = self.fail.get(path)
        if queue:
            code = queue.pop(0)
            return httpx.Response(code, json={"name": "SERVICE_UNAVAILABLE", "message": "try later", "debug_id": "abc"})
        if path == "/v2/checkout/orders/5O190127TN364715T":
            return httpx.Response(200, json=ORDER)
        if path == "/v1/shipping/trackers":
            assert request.url.params["transaction_id"] == "3C679366HH908993F"
            return httpx.Response(200, json={"trackers": [{"transaction_id": "3C679366HH908993F", "status": "DELIVERED",
                                                           "carrier": "USPS", "last_updated_time": "2026-10-22T10:00:00Z"}]})
        if path == "/v1/customer/disputes":
            return httpx.Response(200, json={"items": []})
        if path == "/v2/payments/captures/3C679366HH908993F/refund":
            rid = request.headers["paypal-request-id"]
            body = json.loads(request.content)
            self.refunds.setdefault(rid, {"id": "REF-%d" % (len(self.refunds) + 1), "status": "COMPLETED",
                                          "amount": body["amount"]})
            return httpx.Response(201, json=self.refunds[rid])
        if path.startswith("/v2/checkout/orders/"):
            return httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND", "message": "The specified resource does not exist.",
                                             "debug_id": "d1"})
        return httpx.Response(500)


def client(server):
    return RestPayPal("id", "secret", transport=httpx.MockTransport(server), sleep=lambda s: None)


def test_facts_come_from_paypals_response_shapes():
    s = FakeServer()
    f = client(s).facts("5O190127TN364715T")
    assert (f.capture_id, f.payer_id, f.payer_name) == ("3C679366HH908993F", "QYR5Z8XDVJNXQ", "John Doe")
    assert (f.captured_cents, f.refunded_cents, f.refundable_cents) == (4500, 500, 4000)
    assert f.delivered and f.shipments[0].carrier == "USPS" and f.open_disputes == 0
    assert s.token_calls == 1  # the token is cached across the three reads


def test_a_refund_carries_the_request_id_and_a_retry_does_not_refund_twice():
    s = FakeServer()
    p = client(s)
    s.fail["/v2/payments/captures/3C679366HH908993F/refund"] = [503]
    r = p.refund("3C679366HH908993F", 4000, "USD", "req-1", note="Refund authorized by Remit")
    again = p.refund("3C679366HH908993F", 4000, "USD", "req-1")
    assert r["id"] == again["id"] == "REF-1" and len(s.refunds) == 1
    posts = [c for c in s.calls if c[0] == "POST" and c[1].endswith("/refund")]
    assert all(c[3]["paypal-request-id"] == "req-1" for c in posts) and len(posts) == 3
    assert json.loads(posts[0][4]) == {"amount": {"currency_code": "USD", "value": "40.00"},
                                       "note_to_payer": "Refund authorized by Remit"}


def test_errors_carry_paypals_name_and_debug_id():
    with pytest.raises(PayPalError) as e:
        client(FakeServer()).get_order("NOPE")
    assert e.value.status == 404 and e.value.name == "RESOURCE_NOT_FOUND" and e.value.debug_id == "d1"


def test_transient_failures_are_retried_then_reported():
    s = FakeServer()
    s.fail["/v2/checkout/orders/5O190127TN364715T"] = [503, 429]
    assert client(s).get_order("5O190127TN364715T")["id"] == ORDER["id"]
    s.fail["/v2/checkout/orders/5O190127TN364715T"] = [503, 503, 503]
    with pytest.raises(PayPalError):
        client(s).get_order("5O190127TN364715T")


def test_an_expired_token_is_refreshed_once():
    s = FakeServer()
    s.fail["/v2/checkout/orders/5O190127TN364715T"] = [401]
    assert client(s).get_order("5O190127TN364715T")["id"] == ORDER["id"] and s.token_calls == 2


def test_live_paypal_is_refused():
    with pytest.raises(ValueError):
        RestPayPal("id", "secret", base_url="https://api-m.paypal.com")
    with pytest.raises(ValueError):
        RestPayPal("", "secret")
