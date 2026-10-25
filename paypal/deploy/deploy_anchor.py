"""Deploy RemitAnchor on GenLayer Studio and record it.

    REMIT_KEYS_DIR=<private dir> python deploy/deploy_anchor.py [log_id] [record name]

Each log needs its own contract: RemitAnchor refuses an entry number that is
not after the last one it holds, so a fresh log cannot reuse a contract that
anchors another.

The operator key is read from ``$REMIT_KEYS_DIR/anchor-operator.key``, or
made there (mode 0600) on first use. It never enters the repository. The
account is funded from Studio's faucet, the contract is deployed with that
account as its operator, and ``deploy/anchor-studio.json`` records the
address, the deploy transaction and the SHA-256 of the deployed code.
"""

import hashlib
import json
import os
import stat
import sys
import time

import httpx
from genlayer_py import create_account, create_client
from genlayer_py.chains import studionet
from genlayer_py.types import TransactionStatus

HERE = os.path.dirname(os.path.abspath(__file__))
CONTRACT = os.path.join(os.path.dirname(HERE), "contracts", "remit_anchor.py")
RECORD = os.path.join(HERE, "anchor-studio.json")  # the default record
RPC = "https://studio.genlayer.com/api"


def operator_key():
    keys = os.environ.get("REMIT_KEYS_DIR") or os.path.expanduser("~/.remit-keys")
    os.makedirs(keys, mode=0o700, exist_ok=True)
    path = os.path.join(keys, "anchor-operator.key")
    if not os.path.exists(path):
        from genlayer_py.accounts import generate_private_key

        key = generate_private_key()
        with open(path, "w") as f:
            f.write(key.hex())
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        print("made a new operator key at", path)
    with open(path) as f:
        key = f.read().strip()
    return key if key.startswith("0x") else "0x" + key


def fund(address, gen=10):
    """Studio's faucet. The address must be checksummed: a lower-case one is
    accepted and credited to an address nobody reads."""
    r = httpx.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": "sim_fundAccount",
                              "params": [address, gen * 10**18]}, timeout=60)
    r.raise_for_status()
    if "error" in r.json():
        raise RuntimeError("faucet: %s" % r.json()["error"])


def main():
    log_id = sys.argv[1] if len(sys.argv) > 1 else "remit-paypal demo log"
    record_path = os.path.join(HERE, sys.argv[2]) if len(sys.argv) > 2 else RECORD
    account = create_account(operator_key())
    print("operator", account.address)
    fund(account.address)
    client = create_client(chain=studionet, account=account)
    with open(CONTRACT) as f:
        code = f.read()
    tx = client.deploy_contract(code=code, account=account, args=[account.address, log_id])
    print("deploy tx", tx)
    receipt = client.wait_for_transaction_receipt(transaction_hash=tx, status=TransactionStatus.ACCEPTED,
                                                  interval=3000, retries=100)
    data = receipt.get("data") or {}
    address = data.get("contract_address") or receipt.get("recipient") or receipt.get("to_address")
    result = receipt.get("result_name") or receipt.get("resultName")
    if not address:
        raise RuntimeError("no contract address in the receipt: %s" % json.dumps(receipt, default=str)[:600])
    status = json.loads(str(client.read_contract(address=address, function_name="status")))
    record = {
        "network": "studio",
        "contract": address,
        "operator": account.address,
        "log_id": log_id,
        "deploy_tx": str(tx),
        "consensus": result,
        "code_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
        "status_after_deploy": status,
        "deployed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "explorer": "https://explorer-studio.genlayer.com/address/%s" % address,
    }
    with open(record_path, "w") as f:
        json.dump(record, f, indent=2)
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
