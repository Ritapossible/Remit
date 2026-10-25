"""PayPal REST, as the guard uses it. Sandbox only.

The guard needs four calls: the order, the trackers on its capture, the
disputes on its capture, and the refund. Two more set up the demo shop: an
order paid by a sandbox test card, and its shipment tracking. Reads are retried on transient
failures (network, 429, 5xx). A refund is retried only with the same
``PayPal-Request-Id``, so PayPal returns the first refund instead of making a
second one.
"""

import base64
import time

import httpx

from .facts import from_paypal

SANDBOX = "https://api-m.sandbox.paypal.com"
LIVE_HOSTS = ("api-m.paypal.com", "api.paypal.com")
TRANSIENT = (429, 500, 502, 503, 504)


class PayPalError(Exception):
    """A PayPal API error, with PayPal's own name and debug id."""

    def __init__(self, status, name, message, debug_id=""):
        super().__init__("%s %s: %s%s" % (status, name, message, " (debug id %s)" % debug_id if debug_id else ""))
        self.status, self.name, self.debug_id = status, name, debug_id


def _error(resp):
    try:
        body = resp.json()
    except Exception:
        body = {}
    return PayPalError(resp.status_code, body.get("name") or body.get("error") or "HTTP_ERROR",
                       body.get("message") or body.get("error_description") or resp.text[:200],
                       body.get("debug_id", ""))


class RestPayPal:
    def __init__(self, client_id, client_secret, base_url=SANDBOX, transport=None, timeout=20.0, sleep=time.sleep,
                 tries=3):
        if any(h in base_url for h in LIVE_HOSTS):
            raise ValueError("Remit on PayPal runs on the sandbox only; refusing %s" % base_url)
        if not client_id or not client_secret:
            raise ValueError("PayPal client id and secret are required")
        self._basic = base64.b64encode(("%s:%s" % (client_id, client_secret)).encode()).decode()
        self.http = httpx.Client(base_url=base_url, transport=transport, timeout=timeout)
        self.sleep, self.tries = sleep, tries
        self._token, self._expires = None, 0.0

    # ---------------------------------------------------------------- auth
    def _bearer(self, fresh=False):
        if fresh or not self._token or time.time() > self._expires:
            r = self.http.post("/v1/oauth2/token", data={"grant_type": "client_credentials"},
                               headers={"Authorization": "Basic " + self._basic})
            if r.status_code != 200:
                raise _error(r)
            body = r.json()
            self._token = body["access_token"]
            self._expires = time.time() + int(body.get("expires_in", 300)) - 60
        return self._token

    def _call(self, method, path, *, retry, **kw):
        """One API call. ``retry`` says whether a transient failure may be
        sent again; a 401 refreshes the token once."""
        refreshed = False
        for attempt in range(self.tries):
            headers = dict(kw.pop("headers", {}) or {})
            headers["Authorization"] = "Bearer " + self._bearer()
            try:
                r = self.http.request(method, path, headers=headers, **kw)
            except httpx.TransportError:
                if not retry or attempt == self.tries - 1:
                    raise
                self.sleep(2 ** attempt)
                kw["headers"] = {k: v for k, v in headers.items() if k != "Authorization"}
                continue
            kw["headers"] = {k: v for k, v in headers.items() if k != "Authorization"}
            if r.status_code == 401 and not refreshed:
                refreshed = True
                self._bearer(fresh=True)
                continue
            if r.status_code in TRANSIENT and retry and attempt < self.tries - 1:
                self.sleep(2 ** attempt)
                continue
            if r.status_code >= 400:
                raise _error(r)
            return r.json() if r.content else {}
        raise PayPalError(0, "RETRIES_EXHAUSTED", "%s %s" % (method, path))

    # --------------------------------------------------------------- reads
    def get_order(self, order_id):
        return self._call("GET", "/v2/checkout/orders/%s" % order_id, retry=True)

    def trackers(self, capture_id):
        return self._call("GET", "/v1/shipping/trackers", params={"transaction_id": capture_id},
                          retry=True).get("trackers", [])

    def disputes(self, capture_id):
        return self._call("GET", "/v1/customer/disputes", params={"disputed_transaction_id": capture_id},
                          retry=True).get("items", [])

    def facts(self, order_id):
        order = self.get_order(order_id)
        captures = order.get("purchase_units", [{}])[0].get("payments", {}).get("captures", [])
        capture_id = captures[0]["id"] if captures else ""
        return from_paypal(order, self.trackers(capture_id) if capture_id else [],
                           self.disputes(capture_id) if capture_id else [])

    # --------------------------------------------------------------- money
    def refund(self, capture_id, amount_cents, currency, request_id, note=""):
        """Refund part or all of a capture. ``request_id`` is PayPal's
        idempotency key: the same id returns the same refund."""
        body = {"amount": {"currency_code": currency, "value": "%d.%02d" % (amount_cents // 100, amount_cents % 100)}}
        if note:
            body["note_to_payer"] = note[:255]
        return self._call("POST", "/v2/payments/captures/%s/refund" % capture_id, retry=True, json=body,
                          headers={"PayPal-Request-Id": request_id, "Prefer": "return=representation",
                                   "Content-Type": "application/json"})

    # ------------------------------------------------ demo shop (sandbox)
    def create_paid_order(self, *, customer_id, items, currency, card, request_id):
        """An order paid in full by a sandbox test card and captured, with no
        buyer approval step. ``customer_id`` is the shop's own customer
        reference, recorded by PayPal on the order as ``custom_id``.
        ``request_id`` makes a retry return the same order, never a second."""
        total = sum(q * c for _, q, c in items)
        body = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "custom_id": customer_id,
                "amount": dict(_money(total, currency), breakdown={"item_total": _money(total, currency)}),
                "items": [{"name": n, "quantity": str(q), "unit_amount": _money(c, currency),
                           "category": "PHYSICAL_GOODS"} for n, q, c in items],
            }],
            "payment_source": {"card": card},
        }
        headers = {"PayPal-Request-Id": request_id, "Prefer": "return=representation",
                   "Content-Type": "application/json"}
        order = self._call("POST", "/v2/checkout/orders", retry=True, json=body, headers=headers)
        if order.get("status") != "COMPLETED":  # created and approved by the card, not yet captured
            order = self._call("POST", "/v2/checkout/orders/%s/capture" % order["id"], retry=True, json={},
                               headers=dict(headers, **{"PayPal-Request-Id": request_id + "-capture"}))
        captures = order.get("purchase_units", [{}])[0].get("payments", {}).get("captures", [])
        if order.get("status") != "COMPLETED" or not captures or captures[0].get("status") != "COMPLETED":
            raise PayPalError(0, "NOT_CAPTURED", "order %s is %s" % (order.get("id"), order.get("status")))
        return order["id"], captures[0]["id"]

    def add_tracker(self, capture_id, *, status, carrier, tracking_number):
        r = self._call("POST", "/v1/shipping/trackers-batch", retry=True, json={"trackers": [{
            "transaction_id": capture_id, "tracking_number": tracking_number, "status": status, "carrier": carrier}]})
        if r.get("errors"):
            e = r["errors"][0]
            raise PayPalError(400, e.get("name", "TRACKER_ERROR"), e.get("message", ""), r.get("debug_id", ""))


def _money(value_cents, currency):
    return {"currency_code": currency, "value": "%d.%02d" % (value_cents // 100, value_cents % 100)}
