// Amounts are atto-GEN (value x 10^18) and are handled as bigint end to end.
//
// A JS number holds integers exactly only up to 2^53, about 0.009 GEN in atto.
// Every amount in this product is larger than that, so a single Number() on the
// path would silently corrupt it. There are no floats anywhere in this file.

export const DECIMALS = 18n;
const UNIT = 10n ** DECIMALS;

/** Parse "0.15" -> 150000000000000000n with string arithmetic only. */
export function parseGen(input: string): bigint {
  const text = input.trim();
  if (!/^\d+(\.\d+)?$/.test(text)) throw new Error("Enter an amount like 0.15");
  const [whole, frac = ""] = text.split(".");
  if (frac.length > Number(DECIMALS)) throw new Error("At most 18 decimal places");
  return BigInt(whole) * UNIT + BigInt(frac.padEnd(Number(DECIMALS), "0") || "0");
}

/** Format atto -> "0.15". Trims trailing zeros, never rounds. */
export function formatGen(atto: bigint | string | number, maxFrac = 6): string {
  const v = BigInt(atto);
  const neg = v < 0n;
  const abs = neg ? -v : v;
  const whole = abs / UNIT;
  let frac = (abs % UNIT).toString().padStart(Number(DECIMALS), "0").slice(0, maxFrac);
  frac = frac.replace(/0+$/, "");
  return `${neg ? "-" : ""}${whole}${frac ? "." + frac : ""}`;
}

/**
 * JSON.parse for contract views, without losing precision.
 *
 * The contract renders its views with Python's json.dumps, so every integer is
 * exact in the TEXT. JSON.parse would round anything past 2^53 before a reviver
 * ever saw it, so long integers are quoted first and arrive as strings.
 */
export function parseLossless<T = unknown>(raw: unknown): T {
  if (typeof raw !== "string") return raw as T;
  const quoted = raw.replace(/([:\[,]\s*)(-?\d{16,})(?=\s*[,}\]])/g, '$1"$2"');
  return JSON.parse(quoted) as T;
}
