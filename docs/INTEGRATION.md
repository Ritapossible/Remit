# Integration

Remit authorizes; something else pays. This page is for whoever builds that
something else — a treasury contract, a payment service, or an agent
framework's wallet — and for agents that call Remit directly.

## The one call a rail needs

```python
authorization_of(spend_id: int) -> str   # "authorized" | "refused" | "pending"
```

Pay only on `authorized`. Treat `pending` as *not yet* and poll; treat anything
else, including an error, as *no*.

### From a GenLayer contract

```python
remit = gl.get_contract_at(Address(REMIT_GUARD))
if remit.view().authorization_of(spend_id) != "authorized":
    raise gl.vm.UserError("[EXPECTED] spend is not authorized")
# ... move funds ...
```

### From anywhere else

```ts
import { createClient } from "genlayer-js";
import { studionet } from "genlayer-js/chains";

const client = createClient({ chain: studionet });
const status = await client.readContract({
  address: REMIT_GUARD,
  functionName: "authorization_of",
  args: [spendId],
});
```

On the testnet, pass `endpoint: "https://rpc-asimov.genlayer.com"`. The SDK's
built-in testnet endpoint is plain HTTP to a raw IP, which a browser served over
HTTPS will refuse.

## Contract reference

### Constructor

| Argument | Type | Meaning |
| --- | --- | --- |
| `agent` | `str` | The only address that may request spends. |
| `mandate_json` | `str` | The mandate, as JSON text. See [Mandate format](#/docs/mandate-format). |
| `max_tier` | `int` | The most authority granted. Every rule's tier must be at or below it. |
| `shadow` | `bool` | Record refusals without withholding authorization. |

The deployer becomes the **principal**. A mandate that fails validation makes
the deployment fail.

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
| `preview_spend(recipient, amount, category)` | JSON `{state, rules}` — what `request_spend` would do right now. Runs the same classifier; costs nothing. |
| `get_spend(spend_id)` | JSON summary of one spend, including verdict, reason, evidence state and the agent's claim. |
| `docket()` | JSON list of every spend. |
| `mandate_info()` | JSON: principal, agent, tier, mode, defaults, typed rules, vendor lists. |

Views return JSON text rendered by Python, so integers are exact in the text.
Amounts in atto-GEN exceed 2^53 — parse them as big integers, not as JavaScript
numbers.

## Reading outcomes correctly

A write can be accepted by the network and still change nothing. Read
`result_name` on the receipt, not the leader's own status:

| `result_name` | Leader status | Meaning |
| --- | --- | --- |
| `MAJORITY_AGREE` | `return` | Applied. |
| `MAJORITY_AGREE` | `contract_error` | The contract refused; validators agreed. Nothing changed. |
| `MAJORITY_DISAGREE` | anything | No consensus. Rolled back. Safe to retry. |

The leader's status reads `return` even when validators disagree and the change
is rolled back. Code that checks it will report success on a transaction that
did nothing.

Refusals carry no reason string on chain — the receipt says only
`exit_code 1`. Use `preview_spend` and the documented guards to explain a
refusal before sending, rather than after.
