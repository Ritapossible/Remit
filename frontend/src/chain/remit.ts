import contractSource from "../../../contracts/build/remit.py?raw";
import type { Client } from "./wallet";
import type { MandateInfo } from "../lib/mandate";
import { parseLossless } from "../lib/money";
import type { ArtifactState, Authorization, SpendState, Verdict } from "../lib/constants";

/** The exact artifact the test suite verified. Imported, never copied. */
export const CONTRACT_CODE = contractSource;

export interface SpendView {
  id: number;
  amount: string;
  recipient: string;
  category: string;
  at: number;
  state: SpendState;
  rules: string[];
  memo_uri: string;
  memo_digest: string;
  claim: string;
  held_at: number;
  verdict: Verdict | "";
  reason: string;
  confidence: number;
  artifact: ArtifactState | "";
  outcome: "allowed" | "refused" | "";
  tier: number;
  authorization: Authorization;
  shadow: boolean;
}

export interface Preview {
  state: SpendState | "invalid";
  rules: string[];
  reason: string;
}

/**
 * What a transaction actually did.
 *
 * A receipt's leader status reads "return" even when the validators disagree
 * and the state change is rolled back, so success is never inferred from the
 * leader, and never from a transaction merely being accepted. `result_name` is
 * the consensus outcome and is the only field that says whether anything
 * happened.
 */
export interface TxOutcome {
  hash: string;
  consensus: string;
  leaderStatus: string;
  /** Validators agreed with the leader. */
  agreed: boolean;
  /** Agreed, and the leader's execution returned normally: state changed. */
  applied: boolean;
  /** Agreed that the contract refused. A network success, and a refusal. */
  refused: boolean;
  address?: string;
}

type Addr = `0x${string}`;

export async function readMandate(c: Client, guard: string): Promise<MandateInfo> {
  const raw = await c.readContract({ address: guard as Addr, functionName: "mandate_info", args: [] });
  return parseLossless<MandateInfo>(raw);
}

export async function readDocket(c: Client, guard: string): Promise<SpendView[]> {
  const raw = await c.readContract({ address: guard as Addr, functionName: "docket", args: [] });
  return parseLossless<SpendView[]>(raw);
}

export async function readSpend(c: Client, guard: string, id: number): Promise<SpendView> {
  const raw = await c.readContract({ address: guard as Addr, functionName: "get_spend", args: [id] });
  return parseLossless<SpendView>(raw);
}

/** The contract's own classifier, run as a view. Costs nothing, signs nothing. */
export async function previewSpend(
  c: Client,
  guard: string,
  recipient: string,
  amount: bigint,
  category: string,
): Promise<Preview> {
  const raw = await c.readContract({
    address: guard as Addr,
    functionName: "preview_spend",
    args: [recipient, amount, category],
  });
  return parseLossless<Preview>(raw);
}

/**
 * Two receipt shapes exist in the wild, and they spell the same facts
 * differently:
 *
 *   Studio (older gateway)   result_name: MAJORITY_AGREE
 *                            consensus_data.leader_receipt[0].result.status: return
 *   Bradbury (SDK 1.1.8)     resultName: AGREE
 *                            txExecutionResultName: FINISHED_WITH_RETURN
 *
 * Both are read here, so nothing else in the app has to know. Left unhandled,
 * every Bradbury transaction would read as "no consensus".
 */
function interpret(hash: string, receipt: unknown): TxOutcome {
  const r = receipt as {
    result_name?: string;
    resultName?: string;
    txExecutionResultName?: string;
    data?: { contract_address?: string };
    txDataDecoded?: { contractAddress?: string };
    consensus_data?: { leader_receipt?: { result?: { status?: string } }[] };
  };
  const consensus = r?.result_name ?? r?.resultName ?? "UNKNOWN";
  const exec = r?.txExecutionResultName ?? "";
  const leaderStatus =
    r?.consensus_data?.leader_receipt?.[0]?.result?.status ??
    (/RETURN/.test(exec) ? "return" : /ERROR|ROLLBACK/.test(exec) ? "contract_error" : exec || "unknown");
  const agreed = /AGREE/.test(consensus) && !/DISAGREE/.test(consensus);
  return {
    hash,
    consensus,
    leaderStatus,
    agreed,
    applied: agreed && leaderStatus === "return",
    refused: agreed && leaderStatus === "contract_error",
    address: r?.data?.contract_address ?? r?.txDataDecoded?.contractAddress,
  };
}

async function settle(c: Client, hash: string, pollMs: number): Promise<TxOutcome> {
  // Remit binds on acceptance, not finality, so ACCEPTED is what the UI waits
  // for. If a gateway returns a receipt without a consensus result yet, fall
  // through to finality rather than guessing.
  const accepted = await c.waitForTransactionReceipt({
    hash: hash as never,
    status: "ACCEPTED" as never,
    interval: pollMs,
    retries: 400,
  });
  const first = interpret(hash, accepted);
  if (first.consensus !== "UNKNOWN") return first;
  const finalised = await c.waitForTransactionReceipt({
    hash: hash as never,
    status: "FINALIZED" as never,
    interval: pollMs,
    retries: 400,
  });
  return interpret(hash, finalised);
}

export async function write(
  c: Client,
  guard: string,
  functionName: string,
  args: unknown[],
  pollMs: number,
  onHash?: (hash: string) => void,
): Promise<TxOutcome> {
  const hash = (await c.writeContract({
    address: guard as Addr,
    functionName,
    args: args as never,
    value: 0n,
  })) as string;
  onHash?.(hash);
  return settle(c, hash, pollMs);
}

export async function deployGuard(
  c: Client,
  p: { agent: string; mandateText: string; maxTier: number; shadow: boolean },
  pollMs: number,
  onHash?: (hash: string) => void,
): Promise<TxOutcome> {
  // The mandate is passed as the exact text the user wrote. Re-serialising it
  // in JS would round every amount past 2^53; Python parses the text exactly.
  const hash = (await c.deployContract({
    code: CONTRACT_CODE,
    args: [p.agent, p.mandateText, p.maxTier, p.shadow],
    leaderOnly: false,
  } as never)) as string;
  onHash?.(hash);
  return settle(c, hash, pollMs);
}
