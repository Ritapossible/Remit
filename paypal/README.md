# Remit on PayPal

A spending policy for AI agents' PayPal tools. The plan is
[docs/PAYPAL-PLAN.md](../docs/PAYPAL-PLAN.md).

The agent never refunds. It asks the guard (`remit_paypal/guard.py`):

1. Facts are read from PayPal (order, capture, refunds, tracking, disputes).
2. Checks code can decide run next, then Remit's engine
   (`contracts/remit_core.py`, imported unchanged).
3. The panel of AI models is asked only when a judgment rule fires, and
   fails closed.
4. Only then does PayPal refund, with the request ID as its idempotency key.
5. Every step is written to a hash-chained log.

```bash
cd paypal
python3 -m pytest tests -q     # the six demo cases offline: fake PayPal, stand-in models
```
