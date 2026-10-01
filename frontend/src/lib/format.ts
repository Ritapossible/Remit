export function shortAddr(addr: string | undefined, head = 6, tail = 4): string {
  if (!addr) return "-";
  return addr.length <= head + tail + 2 ? addr : `${addr.slice(0, head)}…${addr.slice(-tail)}`;
}

export function shortHash(h: string | undefined): string {
  return h ? `${h.slice(0, 10)}…${h.slice(-6)}` : "-";
}

export function duration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60 ? `${s % 60}s` : ""}`.trim();
  if (s < 86400) {
    const m = Math.floor((s % 3600) / 60);
    return `${Math.floor(s / 3600)}h${m ? ` ${m}m` : ""}`;
  }
  const h = Math.floor((s % 86400) / 3600);
  return `${Math.floor(s / 86400)}d${h ? ` ${h}h` : ""}`;
}

export function ago(unixSeconds: number, now = Date.now() / 1000): string {
  const d = now - unixSeconds;
  return d < 0 ? "just now" : `${duration(d)} ago`;
}

export function sameAddr(a?: string, b?: string): boolean {
  return !!a && !!b && a.toLowerCase() === b.toLowerCase();
}
