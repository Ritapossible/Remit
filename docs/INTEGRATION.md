# Integration

Remit authorizes; something else pays. This page is for whoever builds that
something else - a treasury contract, a payment service, or an agent
framework's wallet - and for agents that call Remit directly.

## Use the rail

The safest integration is to not write one: deploy **`RemitRail`**
(`contracts/rail.py`) next to the guard and fund it instead of the agent's
wallet.

```text
deploy  RemitRail(guard_address, finality_seconds)   # by the guard's principal
fund()                payable; anyone may top it up
pay(spend_id)         anyone may call; pays the authorized recipient the
                      authorized amount, once, or reverts
withdraw(amount)      principal only
status()              balance, funded, paid_total, paid_count
payment_of(spend_id)  {"paid": bool, "amount": int, "paid_at": int}
```

`pay` reverts unless the guard's `settlement_of` says `authorized`, the spend is
unpaid, the rail holds enough, and the decision is at least `finality_seconds`
old. Set `finality_seconds` to at least the network's appeal window. The rail
refuses to bind to a shadow-mode guard, or to a guard whose principal is not
the deployer. `deploy/rail_scenario.mjs` exercises every one of these on chain.

## The call a rail needs

```python
settlement_of(spend_id: int) -> str   # JSON
# {"authorization": "authorized" | "refused" | "pending",
#  "recipient": "0x...", "amount": int, "decided_at": int,
#  "shadow": bool, "principal": "0x...", "agent": "0x..."}
```

Pay only on `authorized`, only the `amount` to the `recipient`, and only after
`decided_at` is older than your finality delay. Treat `pending` as *not yet*;
treat anything else, including an error, as *no*. `settlement_of` reports the
real outcome even in shadow mode; `authorization_of(spend_id)` returns only the
status and reports `authorized` for every spend under shadow mode (it is for
observers, not payers).

### From a GenLayer contract

```python
s = json.loads(gl.get_contract_at(Address(REMIT_GUARD)).view().settlement_of(spend_id))
if s["authorization"] != "authorized":
    raise gl.vm.UserError("[EXPECTED] spend is not authorized")
# check s["decided_at"] against a finality delay, mark it paid, then pay
# s["amount"] to s["recipient"] - see contracts/rail.py
```

### From anywhere else

```ts
import { createClient } from "genlayer-js";
import { studionet } from "genlayer-js/chains";

const client = createClient({ chain: studionet });
const status = await client.readContract({
  address: REMIT_GUARD,
  functionName: "settlement_of",
  args: [spendId],
});
```

Use **genlayer-js 1.1.8 or later**, and name the network explicitly
(`studionet`, `testnetBradbury`). Version 0.15 shipped a plain-HTTP testnet
endpoint, a retired consensus contract and a hardcoded 21000 gas limit, so every
testnet write failed. Asimov and Bradbury share chain id 4221 but route through
different consensus contracts, so the chain id alone does not identify the
network.

## Contract reference

### Constructor

| Argument | Type | Meaning |
| --- | --- | --- |
| `agent` | `str` | The only address that may request spends. |
| `mandate_json` | `str` | The mandate, as JSON text. See [Mandate format](#/docs/mandate-format). |
| `max_tier` | `int` | The most authority granted. Every rule's tier must be at or below it. |
| `shadow` | `bool` | Record refusals without withholding authorization. |
| `engine` | `str` | The network's shared engine (`engine` in `deploy/deployments.json`). Fixed for the guard's life. |

The deployer becomes the **principal**. A mandate that fails validation makes
the deployment fail. Deploy the bytes in `contracts/build/guard.min.py`, and send
the mandate without whitespace: on Bradbury the code and the arguments together
must stay under about 20 KB (2^24 gas). The app's *New guard* page shows the
estimate before you sign.

### Writes

| Method | Who | What it does |
| --- | --- | --- |
| `request_spend(recipient, amount, category, memo_uri, memo_digest, claim)` | agent | Classifies the spend in this transaction: settled, refused, or held. `amount` is atto-GEN. `memo_uri` and `memo_digest` are optional; if a URI is given the digest must be a sha256 hex string. `claim` is shown to the jury as untrusted. |
| `commit_artifact(spend_id, uri, digest)` | agent | Pins evidence to a held spend. |
| `adjudicate(spend_id)` | anyone | Convenes the jury on a held spend. Refused while the response window is open and no evidence is committed. |
| `resolve_deadline(spend_id)` | anyone | After the hold deadline, applies the registered default. |
| `override_release(spend_id)` / `override_refuse(spend_id)` | principal | Decides a held spend directly. The principal always outranks Remit. |

### Views

| Method | Returns |
| --- | --- |
| `authorization_of(spend_id)` | `"authorized"`, `"refused"` or `"pending"`. |
| `preview_spend(recipient, amount, category)` | JSON `{state, rules}` - what `request_spend` would do right now. Runs the same classifier; costs nothing. |
| `get_spend(spend_id)` | JSON summary of one spend, including verdict, reason, evidence state and the agent's claim. |
| `docket()` | JSON list of every spend. |
| `mandate_info()` | JSON: principal, agent, tier, mode, defaults, typed rules, vendor lists. |

Views return JSON text rendered by Python, so integers are exact in the text.
Amounts in atto-GEN exceed 2^53 - parse them as big integers, not as JavaScript
numbers.

## Reading outcomes correctly

A write can be accepted by the network and still change nothing. Read the
consensus outcome, not the leader's own status. The two networks spell it
differently:

| | Studio | Bradbury (SDK 1.1.8) |
| --- | --- | --- |
| Consensus outcome | `result_name: MAJORITY_AGREE` | `resultName: AGREE` |
| Leader execution | `leader_receipt[0].result.status: return` | `txExecutionResultName: FINISHED_WITH_RETURN` |
| New contract address | `data.contract_address` | `txDataDecoded.contractAddress` |

| Consensus | Leader | Meaning |
| --- | --- | --- |
| agreed | returned normally | Applied. |
| agreed | error | The contract refused; validators agreed. Nothing changed. |
| disagreed | anything | No consensus. Rolled back. Safe to retry. |

The leader's status reads `return` even when validators disagree and the change
is rolled back. Code that checks it will report success on a transaction that
did nothing.

Refusals carry no reason string on chain - the receipt says only
`exit_code 1`. Use `preview_spend` and the documented guards to explain a
refusal before sending, rather than after.
