"""Reading a jury's answer: shared by the guard and the court (rail).

Inlined into both builds by deploy/build_contract.py. Pure Python; the guard's
and the court's consensus closures call these on the model's output and on the
leader's payload.
"""

import json

from remit_core import *


def _is_sha256_hex(value) -> bool:
    text = str(value).strip().lower()
    if len(text) != 64:
        return False
    for ch in text:
        if ch not in "0123456789abcdef":
            return False
    return True


def _as_dict(value) -> dict:
    """Decode a consensus payload into a dict, however it arrives.

    A leader's return value reaches the validator JSON-encoded, so a single
    ``json.loads`` yields a *string* rather than an object. Calling ``.get`` on
    that raises, the validator closure errors, and the error counts as a
    disagreement - which is how a correct verdict came to be rejected by every
    validator with nothing in the receipt pointing at the cause.

    So decode until it is a dict, and return an empty dict rather than raising.
    """
    data = value
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8", "replace")
    elif not isinstance(data, (dict, str)):
        # A leader's value does not arrive as a plain str. Measured on Studio
        # with a per-predicate consensus readout: isinstance(x, str) is False,
        # yet "verified" in str(x) is True - the payload is reachable only
        # through str(). Returning {} for anything unrecognised is what made a
        # correct verdict look like unanimous disagreement.
        data = str(data)
    for _ in range(4):
        if isinstance(data, dict):
            return data
        if not isinstance(data, str):
            return {}
        text = data.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start and not text.startswith('"'):
            text = text[start : end + 1]
        try:
            data = json.loads(text)
        except Exception:
            return {}
    return data if isinstance(data, dict) else {}


def _read_verdict(raw) -> dict:
    """Defensive parsing of an LLM response.

    Models return unpredictable shapes. Accept a dict or a string, strip
    wrapping prose, alias the keys models actually use, and coerce the
    confidence. Anything that cannot be read as one of the three verdicts is
    UNDETERMINED, which resolves to the registered default rather than to a
    guess.
    """
    data = _as_dict(raw)

    verdict = ""
    for alias in ("verdict", "answer", "decision", "result", "label"):
        if alias in data and isinstance(data[alias], str):
            verdict = data[alias].strip().lower().replace("-", "_").replace(" ", "_")
            break
    if verdict in ("in_remit", "inremit", "within_remit", "allowed", "yes"):
        verdict = VERDICT_IN_REMIT
    elif verdict in ("out_of_remit", "outofremit", "outside_remit", "refused", "no"):
        verdict = VERDICT_OUT_OF_REMIT
    else:
        verdict = VERDICT_UNDETERMINED

    reason = ""
    for alias in ("reason", "reason_code", "code", "rationale"):
        if alias in data and isinstance(data[alias], str):
            reason = data[alias].strip().lower()[:64]
            break

    confidence = 0
    for alias in ("confidence", "certainty", "score"):
        if alias in data:
            try:
                confidence = int(float(str(data[alias]).strip().rstrip("%")))
            except Exception:
                confidence = 0
            break
    if confidence < 0:
        confidence = 0
    if confidence > 100:
        confidence = 100

    # Not hardened here: the guard and the court each apply their own rule for
    # a hesitant answer (harden_verdict, harden_challenge).
    return {"verdict": verdict, "reason": reason, "confidence": confidence}
