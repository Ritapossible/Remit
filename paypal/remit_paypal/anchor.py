"""Anchoring the decision log on GenLayer.

After each decision, the newest ``(seq, hash)`` of the hash-chained log is
published to the ``RemitAnchor`` contract (``paypal/contracts``). Anyone can
then recompute the log and compare it with the chain: a rewrite of any entry
at or before an anchored one no longer matches.

The anchorer runs in the background and is never on the refund path. While
one anchor is in flight, later decisions are covered by the next one: only
the newest head is ever sent. A GenLayer outage queues anchoring; it never
delays or changes a refund.

Anchor records are kept in their own table, not in the hash chain:
logging "anchored entry N" as entry N+1 would itself need anchoring.
"""

import json
import threading
import time

from .ledger import entry_hash

EXPLORER = "https://explorer-studio.genlayer.com"

SCHEMA = """
CREATE TABLE IF NOT EXISTS anchors (
  seq     BIGINT PRIMARY KEY,
  hash    TEXT NOT NULL,
  tx      TEXT NOT NULL,
  at      BIGINT NOT NULL
);
"""


class GenLayerAnchor:
    """``RemitAnchor`` on GenLayer, through the official Python SDK."""

    def __init__(self, private_key, contract, endpoint=None):
        from genlayer_py import create_account, create_client
        from genlayer_py.chains import studionet

        self.account = create_account(private_key)
        self.client = create_client(chain=studionet, endpoint=endpoint, account=self.account)
        self.contract = contract

    def anchor(self, seq, chain_hash):
        from genlayer_py.types import TransactionStatus

        tx = self.client.write_contract(address=self.contract, function_name="anchor", args=[int(seq), chain_hash],
                                        account=self.account)
        receipt = self.client.wait_for_transaction_receipt(transaction_hash=tx, status=TransactionStatus.ACCEPTED,
                                                           interval=3000, retries=60)
        result = str(receipt.get("result_name") or receipt.get("resultName") or "")
        if "AGREE" not in result or "DISAGREE" in result:
            raise RuntimeError("the anchor transaction did not reach agreement: %s" % (result or "unknown"))
        # Validators can agree on a call the contract refused (an entry number
        # not after the last one, a different log). Only what the contract
        # now holds counts.
        held = self.hash_at(seq)
        if held != chain_hash:
            raise RuntimeError("the contract refused entry %d (it holds %r there); is it anchoring another log?"
                               % (seq, held[:16]))
        return str(tx)

    def latest(self):
        return json.loads(str(self.client.read_contract(address=self.contract, function_name="latest")) or "{}")

    def hash_at(self, seq):
        return str(self.client.read_contract(address=self.contract, function_name="hash_at", args=[int(seq)]))


class FakeAnchor:
    """An in-memory RemitAnchor, with the contract's rules, for tests.

    ``agree_on_refusal`` mimics GenLayer reaching agreement on a call the
    contract refused: the send returns a transaction, and nothing is stored.
    ``GenLayerAnchor`` must notice by reading the hash back."""

    def __init__(self):
        self.anchored = {}
        self.last = 0
        self.calls = 0
        self.fail = 0  # fail this many sends, then work
        self.gate = None  # a threading.Event to hold sends, for tests

    def anchor(self, seq, chain_hash):
        self.calls += 1
        if self.gate is not None:
            self.gate.wait(5)
        if self.fail:
            self.fail -= 1
            raise ConnectionError("GenLayer unavailable")
        if seq <= self.last:
            if getattr(self, "agree_on_refusal", False):
                return "0xrefused%d" % seq
            raise RuntimeError("entry %d is not after %d" % (seq, self.last))
        self.anchored[seq], self.last = chain_hash, seq
        return "0xtx%d" % seq

    def latest(self):
        return {"seq": self.last, "hash": self.anchored[self.last], "at": 0} if self.last else {}

    def hash_at(self, seq):
        return self.anchored.get(seq, "")


class Anchorer:
    def __init__(self, ledger, chain, contract="", clock=time.time, retry_seconds=15):
        self.ledger, self.chain, self.contract, self.clock = ledger, chain, contract, clock
        self.retry_seconds = retry_seconds
        self.ledger.db.script(SCHEMA)
        self.wake = threading.Event()
        self.stop_flag = threading.Event()
        self.thread = None
        self.last_error = ""
        self.lock = threading.Lock()

    # ------------------------------------------------------------ worker
    def notify(self):
        """A decision was logged: anchor the newest head when the worker is free."""
        self.wake.set()

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, name="remit-anchorer", daemon=True)
            self.thread.start()
        return self

    def stop(self):
        self.stop_flag.set()
        self.wake.set()
        if self.thread is not None:
            self.thread.join(timeout=10)

    def _run(self):
        while not self.stop_flag.is_set():
            self.wake.wait(timeout=self.retry_seconds)
            self.wake.clear()
            if self.stop_flag.is_set():
                break
            self.anchor_once()

    def anchor_once(self):
        """Anchor the newest head if it is newer than the last anchor.
        Returns the new anchor, or None. Errors are kept, never raised."""
        with self.lock:
            head = self.ledger.head()
            last = self.last_anchor()
            if head is None or (last and last["seq"] >= head["seq"]):
                return None
            try:
                tx = self.chain.anchor(head["seq"], head["hash"])
            except Exception as exc:
                self.last_error = "%s: %s" % (type(exc).__name__, str(exc)[:200])
                return None
            self.last_error = ""
            row = (head["seq"], head["hash"], tx, int(self.clock()))
            self.ledger.db.execute("INSERT INTO anchors VALUES (?,?,?,?)", row)
            return dict(zip(("seq", "hash", "tx", "at"), row))

    # ------------------------------------------------------------ reading
    def last_anchor(self):
        row = self.ledger.db.execute("SELECT seq, hash, tx, at FROM anchors ORDER BY seq DESC LIMIT 1").fetchone()
        return dict(zip(("seq", "hash", "tx", "at"), row)) if row else None

    def anchor_covering(self, seq):
        """The first anchor at or after ``seq``: it covers that entry."""
        row = self.ledger.db.execute("SELECT seq, hash, tx, at FROM anchors WHERE seq >= ? ORDER BY seq LIMIT 1",
                                     (int(seq),)).fetchone()
        return dict(zip(("seq", "hash", "tx", "at"), row)) if row else None

    def status(self, check_chain=True):
        """The log's head, the last anchor, and, read from GenLayer itself,
        whether the log still matches what was anchored."""
        head, last = self.ledger.head(), self.last_anchor()
        out = {
            "contract": self.contract,
            "explorer": ("%s/address/%s" % (EXPLORER, self.contract)) if self.contract else "",
            "head_seq": head["seq"] if head else 0,
            "anchor": last,
            "pending": bool(head and (not last or last["seq"] < head["seq"])),
            "last_error": self.last_error,
        }
        if check_chain:
            out["check"] = verify(self.ledger, self.chain)
        return out


def verify(ledger, chain):
    """Recompute the log and compare it with the newest anchor on chain.

    ``matches`` is True only if the local chain is unbroken *and* the hash at
    the anchored entry equals the one GenLayer holds. Because each entry
    includes the hash of the one before, that one comparison covers every
    entry up to the anchor."""
    ok, broken = ledger.verify()
    try:
        on_chain = chain.latest()
    except Exception as exc:
        return {"matches": None, "reason": "could not read GenLayer: %s" % type(exc).__name__}
    if not on_chain:
        return {"matches": None, "reason": "nothing anchored yet"}
    seq, anchored = int(on_chain["seq"]), on_chain["hash"]
    if not ok:
        return {"matches": False, "seq": seq, "reason": "the log's chain breaks at entry %d" % broken}
    local = ledger.hash_at(seq)
    if local is None:
        return {"matches": False, "seq": seq, "reason": "entry %d is missing from the log" % seq}
    if local != anchored:
        return {"matches": False, "seq": seq, "reason": "entry %d differs from what was anchored" % seq}
    return {"matches": True, "seq": seq, "hash": anchored}


def recompute(entries):
    """Recompute a chain from entries as ``/api/log`` serves them, without
    trusting the hashes the server reports. Returns ``{seq: hash}``."""
    from .ledger import GENESIS

    prev, out = GENESIS, {}
    for e in sorted(entries, key=lambda x: x["seq"]):
        body = json.dumps(e["body"], separators=(",", ":"), sort_keys=True)
        h = entry_hash(prev, e["seq"], e["at"], e["kind"], body)
        out[e["seq"]] = h
        prev = h
    return out
