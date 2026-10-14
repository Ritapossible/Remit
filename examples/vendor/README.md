# Example evidence sources

Milestone 1 pins, per vendor, the URL prefixes its evidence must come from.

- `vendor/northlight/` stands for the vendor's own invoice host. The demo
  mandates (`mandates/demo-*.json`) pin it for the vendor
  `0x3F55971f7fd2594A90871Db489fBb82f1DB4d747`.
- `../agent-uploads/` stands for anywhere the agent can publish. It holds the
  **same bytes** as the vendor's invoice. The guard refuses it, because only
  where a document comes from - not what it says - is the difference between
  evidence and a forgery the agent wrote itself.
