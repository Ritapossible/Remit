"""The ledger's storage: SQLite always; Postgres when REMIT_TEST_DB is set."""

import os

import pytest

from remit_paypal.ledger import Ledger

PG = os.environ.get("REMIT_TEST_DB")


def test_the_chain_survives_a_reopened_store(tmp_path):
    path = PG or str(tmp_path / "remit.sqlite3")
    a = Ledger(path)
    a.append(1, "requested", {"request_id": "r1"})
    a.append(2, "refused", {"request_id": "r1"})
    b = Ledger(path)  # a restart: same store, new process state
    assert [e["kind"] for e in b.entries()] == ["requested", "refused"] and b.verify() == (True, None)
    b.append(3, "requested", {"request_id": "r2"})
    assert b.head()["seq"] == 3 and b.verify() == (True, None)


@pytest.mark.skipif(not PG, reason="Postgres only: set REMIT_TEST_DB")
def test_a_dropped_postgres_connection_is_reopened():
    import psycopg

    led = Ledger(PG)
    led.append(1, "requested", {"request_id": "r1"})
    pid = led.db.execute("SELECT pg_backend_pid()").fetchone()[0]
    with psycopg.connect(PG, autocommit=True) as admin:
        admin.execute("SELECT pg_terminate_backend(%s)", (pid,))
    led.append(2, "refused", {"request_id": "r1"})  # the first try fails; the store reconnects
    assert led.head()["seq"] == 2 and led.verify() == (True, None)
