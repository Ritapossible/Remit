# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import datetime
import json


class RemitAnchor(gl.Contract):
    """Public anchors for Remit on PayPal's decision log.

    Remit's server keeps a hash-chained log of every refund decision: each
    entry stores the hash of the one before it. Here the operator publishes
    the chain's hash at an entry number. Once a hash is here, rewriting any
    earlier entry of the log makes the chain no longer match it, and anyone
    can check that by recomputing the log and reading this contract.

    Deterministic on purpose: no model, no web call. It holds no money and
    decides nothing; it only records what the log said, and when.

    Rules:
    - only the operator set at deployment may anchor;
    - entry numbers strictly increase, so history cannot be re-anchored;
    - a hash is 64 lowercase hex characters (SHA-256).
    """

    operator: str
    log_id: str
    count: u256
    last_seq: u256
    hashes: TreeMap[u256, str]  # entry number -> chain hash
    order: TreeMap[u256, str]  # n-th anchor (from 1) -> {"seq", "hash", "at"}

    def __init__(self, operator: str, log_id: str):
        op = str(operator).strip().lower()
        if len(op) != 42 or not op.startswith("0x") or any(c not in "0123456789abcdef" for c in op[2:]):
            raise Exception("[EXPECTED] operator: not an address")
        self.operator = op
        self.log_id = str(log_id)[:120]
        self.count = u256(0)
        self.last_seq = u256(0)

    @gl.public.write
    def anchor(self, seq: int, chain_hash: str) -> None:
        if str(gl.message.sender_address).lower() != self.operator:
            raise Exception("[EXPECTED] only the operator anchors")
        n = int(seq)
        if n <= int(self.last_seq):
            raise Exception("[EXPECTED] entry %d is not after the last anchored entry %d" % (n, int(self.last_seq)))
        h = str(chain_hash).strip().lower()
        if len(h) != 64 or any(c not in "0123456789abcdef" for c in h):
            raise Exception("[EXPECTED] hash: expected 64 hex characters")
        at = int(datetime.datetime.now().timestamp())
        self.hashes[u256(n)] = h
        self.count = u256(int(self.count) + 1)
        self.order[u256(int(self.count))] = json.dumps({"seq": n, "hash": h, "at": at})
        self.last_seq = u256(n)

    @gl.public.view
    def latest(self) -> str:
        """The newest anchor as JSON, or "{}" before the first."""
        if int(self.count) == 0:
            return "{}"
        return self.order[u256(int(self.count))]

    @gl.public.view
    def hash_at(self, seq: int) -> str:
        """The anchored hash at an entry number, or "" if that entry was not anchored."""
        return self.hashes.get(u256(int(seq)), "")

    @gl.public.view
    def anchors(self, start: int, limit: int) -> str:
        """Anchors ``start`` (from 1) onward, at most ``limit`` (up to 100), as a JSON list."""
        out = []
        i = max(1, int(start))
        end = min(int(self.count), i + max(0, min(int(limit), 100)) - 1)
        while i <= end:
            out.append(json.loads(self.order[u256(i)]))
            i += 1
        return json.dumps(out)

    @gl.public.view
    def status(self) -> str:
        return json.dumps({
            "release": "remit-anchor/1",
            "operator": self.operator,
            "log_id": self.log_id,
            "count": int(self.count),
            "last_seq": int(self.last_seq),
        })
