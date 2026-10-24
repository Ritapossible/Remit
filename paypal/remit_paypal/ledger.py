"""The guard's memory: past refunds (for the engine's windows) and an
append-only, hash-chained log of every decision.

Each log entry stores the SHA-256 of the entry before it, so editing or
deleting a past entry breaks every hash after it (``verify``). This makes
the operator's record checkable; it does not make the operator trustless.
"""

import hashlib
import json
import sqlite3
import threading

from .engine import core

GENESIS = "0" * 64

SCHEMA = """
CREATE TABLE IF NOT EXISTS refunds (
  request_id TEXT PRIMARY KEY,
  recipient  TEXT NOT NULL,
  payer_id   TEXT NOT NULL,
  capture_id TEXT NOT NULL,
  amount     INTEGER NOT NULL,
  category   TEXT NOT NULL,
  at         INTEGER NOT NULL,
  state      TEXT NOT NULL,
  paypal_refund_id TEXT
);
CREATE TABLE IF NOT EXISTS log (
  seq   INTEGER PRIMARY KEY,
  at    INTEGER NOT NULL,
  kind  TEXT NOT NULL,
  body  TEXT NOT NULL,
  prev  TEXT NOT NULL,
  hash  TEXT NOT NULL
);
"""

# States a refund can end in. Only REFUNDED counts toward the engine's
# windows: a refused or failed request moved no money.
REFUNDED = "refunded"
REFUSED = "refused"
FAILED = "failed"
PENDING = "pending"


def entry_hash(prev, seq, at, kind, body):
    payload = json.dumps([prev, seq, at, kind, body], separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Ledger:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self.lock = threading.RLock()

    # ---------------------------------------------------------------- log
    def append(self, at, kind, body):
        text = json.dumps(body, separators=(",", ":"), sort_keys=True)
        with self.lock:
            row = self.db.execute("SELECT seq, hash FROM log ORDER BY seq DESC LIMIT 1").fetchone()
            seq, prev = (row[0] + 1, row[1]) if row else (1, GENESIS)
            h = entry_hash(prev, seq, int(at), kind, text)
            self.db.execute("INSERT INTO log VALUES (?,?,?,?,?,?)", (seq, int(at), kind, text, prev, h))
        return seq, h

    def entries(self, since=0):
        rows = self.db.execute("SELECT seq, at, kind, body, prev, hash FROM log WHERE seq > ? ORDER BY seq", (since,))
        return [{"seq": s, "at": a, "kind": k, "body": json.loads(b), "prev": p, "hash": h} for s, a, k, b, p, h in rows]

    def verify(self):
        """``(True, None)`` if every entry chains to the one before it, else
        ``(False, seq)`` naming the first entry that does not."""
        prev = GENESIS
        for s, a, k, b, p, h in self.db.execute("SELECT seq, at, kind, body, prev, hash FROM log ORDER BY seq"):
            if p != prev or entry_hash(p, s, a, k, b) != h:
                return False, s
            prev = h
        return True, None

    # ------------------------------------------------------------ refunds
    def start(self, request_id, recipient, payer_id, capture_id, amount, category, at):
        """Record a request before anything is decided. A request ID seen
        before is refused: retries must reuse the earlier outcome."""
        with self.lock:
            try:
                self.db.execute("INSERT INTO refunds VALUES (?,?,?,?,?,?,?,?,NULL)",
                                (request_id, recipient, payer_id, capture_id, int(amount), category, int(at), PENDING))
            except sqlite3.IntegrityError:
                raise core.RemitError("request %s was already submitted" % request_id)

    def finish(self, request_id, state, paypal_refund_id=None):
        with self.lock:
            self.db.execute("UPDATE refunds SET state = ?, paypal_refund_id = ? WHERE request_id = ?",
                            (state, paypal_refund_id, request_id))

    def get(self, request_id):
        row = self.db.execute("SELECT request_id, state, paypal_refund_id FROM refunds WHERE request_id = ?",
                              (request_id,)).fetchone()
        return {"request_id": row[0], "state": row[1], "paypal_refund_id": row[2]} if row else None

    def history(self, exclude=None):
        """Refunds that moved money, as engine spends (oldest first)."""
        rows = self.db.execute(
            "SELECT amount, recipient, category, at FROM refunds WHERE state = ? AND request_id != ? ORDER BY at",
            (REFUNDED, exclude or ""))
        return [core.Spend(amount=a, recipient=r, category=c, at=t) for a, r, c, t in rows]
