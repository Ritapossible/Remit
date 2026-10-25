"""Build the guard from the environment.

    PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET   sandbox REST app (required unless REMIT_OFFLINE=1)
    REMIT_MODEL_API_KEY                      key for an OpenAI-compatible API (required unless REMIT_OFFLINE=1)
    REMIT_MODEL_BASE_URL                     default https://openrouter.ai/api/v1
    REMIT_PANEL_MODELS                       comma-separated model ids, one per panel seat
    REMIT_PANEL_QUORUM                       default: a strict majority of the seats
    REMIT_MANDATE                            default mandates/demo-shop.json
    REMIT_DB                                 default remit.sqlite3
    REMIT_OFFLINE=1                          fake PayPal and stand-in models, for trying the MCP server without keys
    REMIT_ANCHOR_CONTRACT, REMIT_ANCHOR_KEY  RemitAnchor on GenLayer Studio and the operator's private key;
                                             both unset: the log is not anchored
    REMIT_ANCHOR_ENDPOINT                    default https://studio.genlayer.com/api
"""

import os

from .guard import Guard, load_mandate
from .ledger import Ledger
from .panel import Panel

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PANEL = "openai/gpt-4o-mini,anthropic/claude-3.5-haiku,google/gemini-2.0-flash-001"


def build_guard(env=os.environ):
    with open(env.get("REMIT_MANDATE", os.path.join(HERE, "mandates", "demo-shop.json"))) as f:
        mandate = load_mandate(f.read())
    ledger = Ledger(env.get("REMIT_DB", "remit.sqlite3"))
    if env.get("REMIT_OFFLINE") == "1":
        from .offline import offline_paypal, offline_models
        paypal, models = offline_paypal(), offline_models()
    else:
        from .models import DEFAULT_BASE, ChatModel
        from .paypal_api import RestPayPal
        paypal = RestPayPal(env.get("PAYPAL_CLIENT_ID", ""), env.get("PAYPAL_CLIENT_SECRET", ""))
        names = [m.strip() for m in env.get("REMIT_PANEL_MODELS", DEFAULT_PANEL).split(",") if m.strip()]
        base, key = env.get("REMIT_MODEL_BASE_URL", DEFAULT_BASE), env.get("REMIT_MODEL_API_KEY", "")
        models = {n: ChatModel(n, key, base) for n in names}
    quorum = int(env.get("REMIT_PANEL_QUORUM", len(models) // 2 + 1))
    return Guard(paypal, ledger, mandate, Panel(models, quorum=quorum))


def build_anchorer(ledger, env=os.environ):
    """The GenLayer anchorer, or None when anchoring is not configured."""
    contract, key = env.get("REMIT_ANCHOR_CONTRACT", ""), env.get("REMIT_ANCHOR_KEY", "")
    if not contract or not key:
        return None
    from .anchor import Anchorer, GenLayerAnchor

    chain = GenLayerAnchor(key, contract, endpoint=env.get("REMIT_ANCHOR_ENDPOINT") or None)
    return Anchorer(ledger, chain, contract=contract)
