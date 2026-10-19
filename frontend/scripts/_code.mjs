import { createClient } from "genlayer-js";
import { studionet, testnetBradbury } from "genlayer-js/chains";
import { createHash } from "node:crypto";
import fs from "node:fs";
const sets = {
  "release1 (deployments-v1.json)": JSON.parse(fs.readFileSync("../deploy/deployments-v1.json")),
  "milestone1-first (archive/deployments-engine4.json)": JSON.parse(fs.readFileSync("../deploy/archive/deployments-engine4.json")),
  "milestone1 (deployments.json)": JSON.parse(fs.readFileSync("../deploy/deployments.json")),
};
const out = {};
for (const [name, d] of Object.entries(sets)) for (const [net, chain] of [["studio", studionet], ["bradbury", testnetBradbury]]) {
  const c = createClient({ chain });
  for (const [k, role] of [["engine", "engine"], ["prompts", "prompts"], ["registry", "registry"], ["address", "guard"], ["rail", "rail"]]) {
    const addr = d[net]?.[k]; if (!addr) continue;
    try {
      const code = await c.getContractCode(addr);
      const h = createHash("sha256").update(code).digest("hex");
      out[`${name}|${net}|${role}`] = { address: addr, sha256: h, bytes: Buffer.byteLength(code) };
      console.log(name.padEnd(52), net.padEnd(9), role.padEnd(9), addr, h.slice(0, 16), Buffer.byteLength(code));
    } catch (e) { console.log(name, net, role, addr, "ERR", String(e.message).slice(0, 80)); }
  }
}
fs.writeFileSync("/tmp/claude-0/onchain.json", JSON.stringify(out, null, 1));
