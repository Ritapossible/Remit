// Computes the sha256 the contract will check. Validators fetch the same URL
// and hash the same bytes, so this lets a user confirm BEFORE committing that
// the artifact will verify rather than land as "unverified".

export async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function digestOfUrl(url: string): Promise<{ digest: string; bytes: number }> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`Fetch failed: HTTP ${res.status}. Validators would see the same.`);
  const buf = await res.arrayBuffer();
  return { digest: await sha256Hex(buf), bytes: buf.byteLength };
}

export const isSha256Hex = (v: string) => /^[0-9a-f]{64}$/i.test(v.trim());
