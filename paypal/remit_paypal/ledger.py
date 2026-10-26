"""The guard's memory: past refunds (for the engine's windows) and an
append-only, hash-chained log of every decision.

Each log entry stores the SHA-256 of the entry before it, so editing or
deleting a past entry breaks every hash after it (``verify``). This makes
the operator's record checkable; it does not make the operator trustless.

Storage is SQLite (a file, or ``:memory:`` for tests) or Postgres (a
``postgresql://`` URL, for hosts whose disk does not persist). Both go
through one small adapter, ``ledger.db``: ``execute(sql, params)`` with
``?`` placeholders, and ``script(sql)``.
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
  amount     BIGINT NOT NULL,
  category   TEXT NOT NULL,
  at         BIGINT NOT NULL,
  state      TEXT NOT NULL,
  paypal_refund_id TEXT
);
CREATE TABLE IF NOT EXISTS log (
  seq   BIGINT PRIMARY KEY,
  at    BIGINT NOT NULL,
  kind  TEXT NOT NULL,
  body  TEXT NOT NULL,
  prev  TEXT NOT NULL,
  hash  TEXT NOT NULL
);
"""

# States a refund can be in. The engine's windows count every request that
# moved money or may have: REFUNDED; UNKNOWN, when PayPal may have refunded
# before the call failed; and PENDING, a decision a crash cut off (decisions
# are made one at a time, so any pending request but the current one is one).
# REFUSED and FAILED (PayPal declined) moved nothing. Failing closed: an
# unknown refund lowers what the caps still allow, never raises it.
REFUNDED = "refunded"
REFUSED = "refused"
FAILED = "failed"
UNKNOWN = "unknown"
PENDING = "pending"
COUNTED = (REFUNDED, UNKNOWN, PENDING)


def entry_hash(prev, seq, at, kind, body):
    payload = json.dumps([prev, seq, at, kind, body], separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class _Sqlite:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.integrity = sqlite3.IntegrityError
        self.lock = threading.RLock()

    def execute(self, sql, params=()):
        with self.lock:
            return self.conn.execute(sql, params)

    def script(self, sql):
        with self.lock:
            self.conn.executescript(sql)


class _Postgres:
    """Postgres through psycopg, autocommit. A dropped connection (a hosted
    database sleeping when idle) is reopened once and the statement retried."""

    def __init__(self, url):
        import psycopg

        self.psycopg, self.url = psycopg, url
        self.integrity = psycopg.errors.IntegrityError
        self.lock = threading.RLock()
        self.conn = psycopg.connect(url, autocommit=True)

    def execute(self, sql, params=()):
        sql = sql.replace("?", "%s")
        with self.lock:
            try:
                return self.conn.execute(sql, params)
            except self.psycopg.OperationalError:
                self.conn = self.psycopg.connect(self.url, autocommit=True)
                return self.conn.execute(sql, params)

    def script(self, sql):
        for statement in sql.split(";"):
            if statement.strip():
                self.execute(statement)


def open_store(path):
    if str(path).startswith(("postgres://", "postgresql://")):
        return _Postgres(path)
    return _Sqlite(path)


class Ledger:
    def __init__(self, path=":memory:"):
        self.db = open_store(path)
        self.db.script(SCHEMA)
        self.lock = threading.RLock()

    # ---------------------------------------------------------------- log
    def append(self, at, kind, body):
        text = json.dumps(body, separators=(",", ":"), sort_keys=True)
        with self.lock:
            row = self.db.execute("SELECT seq, hash FROM log ORDER BY seq DESC LIMIT 1").fetchone()
            seq, prev = (row[0] + 1, row[1]) if row else (1, GENESIS)
            h = entry_hash(prev, seq, int(at), kind, text)
            try:
                self.db.execute("INSERT INTO log VALUES (?,?,?,?,?,?)", (seq, int(at), kind, text, prev, h))
            except self.db.integrity:
                # A reconnect retried an insert that had already been written:
                # the entry is there, and it is this one.
                if self.hash_at(seq) != h:
                    raise
        return seq, h

    def entries(self, since=0, limit=None):
        """Entries after ``since``, oldest first, at most ``limit`` of them."""
        sql = "SELECT seq, at, kind, body, prev, hash FROM log WHERE seq > ? ORDER BY seq"
        params = (int(since),)
        if limit is not None:
            sql, params = sql + " LIMIT ?", params + (int(limit),)
        rows = self.db.execute(sql, params)
        return [{"seq": s, "at": a, "kind": k, "body": json.loads(b), "prev": p, "hash": h} for s, a, k, b, p, h in rows]

    def head(self):
        """The newest entry's ``seq`` and ``hash``, or None for an empty log."""
        row = self.db.execute("SELECT seq, hash FROM log ORDER BY seq DESC LIMIT 1").fetchone()
        return {"seq": row[0], "hash": row[1]} if row else None

    def hash_at(self, seq):
        row = self.db.execute("SELECT hash FROM log WHERE seq = ?", (int(seq),)).fetchone()
        return row[0] if row else None

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
            except self.db.integrity:
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
        """Refunds that moved money or may have, as engine spends (oldest first)."""
        rows = self.db.execute(
            "SELECT amount, recipient, category, at FROM refunds WHERE state IN (?,?,?) AND request_id != ? "
            "ORDER BY at", (*COUNTED, exclude or ""))
        return [core.Spend(amount=a, recipient=r, category=c, at=t) for a, r, c, t in rows]
