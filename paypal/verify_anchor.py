"""Check a Remit server's decision log against its anchor on GenLayer,
without trusting the server.

    python verify_anchor.py https://<remit server> [contract address]

1. Downloads the whole log from the server (GET /api/log, page by page).
2. Recomputes every hash itself; the hashes the server reports are ignored.
3. Reads the newest anchor directly from the RemitAnchor contract on GenLayer
   Studio (address from the argument, else deploy/anchor-studio.json).
4. Compares: the recomputed hash at the anchored entry must equal the one on
   GenLayer. Each hash covers every entry before it, so that one comparison
   checks the whole log up to the anchor.

Exit code 0 when the log matches GenLayer, 1 otherwise.
"""

import json
import os
import sys

import httpx
from genlayer_py import create_account, create_client
from genlayer_py.chains import studionet

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from remit_paypal.anchor import recompute  # noqa: E402


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    server = sys.argv[1].rstrip("/")
    if len(sys.argv) > 2:
        contract = sys.argv[2]
    else:
        with open(os.path.join(HERE, "deploy", "anchor-studio.json")) as f:
            contract = json.load(f)["contract"]

    entries, since = [], 0
    while since is not None:
        page = httpx.get(server + "/api/log", params={"since": since}, timeout=60).json()
        entries += page["entries"]
        since = page.get("next")
    hashes = recompute(entries)
    reported = {e["seq"]: e["hash"] for e in entries}
    mismatched = [s for s in hashes if hashes[s] != reported.get(s)]
    print("log:      %d entries from %s" % (len(entries), server))
    print("          recomputed here; %s" % ("every reported hash agrees" if not mismatched else
                                             "reported hashes disagree from entry %d" % mismatched[0]))

    # The SDK wants an account even to read; a throwaway one with no funds is
    # enough, so checking needs no key.
    reader = create_account()
    client = create_client(chain=studionet, account=reader)
    latest = json.loads(str(client.read_contract(address=contract, function_name="latest")) or "{}")
    if not latest:
        print("genlayer: nothing anchored yet on", contract)
        sys.exit(1)
    seq, anchored = int(latest["seq"]), latest["hash"]
    print("genlayer: %s holds entry %d = %s" % (contract, seq, anchored))

    local = hashes.get(seq)
    if local is None:
        print("RESULT:   does not match. Entry %d is missing from the log." % seq)
        sys.exit(1)
    if local != anchored:
        print("RESULT:   does not match. The log up to entry %d is not what was anchored." % seq)
        sys.exit(1)
    later = len([s for s in hashes if s > seq])
    print("RESULT:   matches. Entries 1 to %d are exactly what was anchored on GenLayer%s." % (
        seq, "" if not later else "; %d later entr%s not anchored yet" % (later, "y is" if later == 1 else "ies are")))


if __name__ == "__main__":
    main()
