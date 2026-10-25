import { REPO } from "../components/chrome";

const CLAUDE = `{
  "mcpServers": {
    "remit": {
      "command": "/path/to/remit/paypal/.venv/bin/python",
      "args": ["-m", "remit_paypal.mcp_server"],
      "cwd": "/path/to/remit/paypal",
      "env": { "REMIT_OFFLINE": "1" }
    }
  }
}`;

const TOOLS = [
  ["get_order", "The order as PayPal records it: items, paid, refunded, still refundable."],
  ["get_shipment_tracking", "PayPal's tracking for the payment: shipped, delivered, when."],
  ["list_disputes", "Open PayPal disputes on the payment."],
  ["request_refund", "Ask Remit. Returns the decision, the rules applied, each model's vote, and PayPal's refund id or the reason."],
  ["get_decision", "A past decision and its log entries."],
];

export function How() {
  return (
    <div className="wrap page">
      <span className="eyebrow">How it works</span>
      <h1 className="h2" style={{ marginTop: 12 }}>One guarded path to PayPal's money.</h1>
      <p className="lede">
        Remit runs as an MCP server. Agents get PayPal's read tools and one money-moving tool, <code>request_refund</code>, which
        runs the guard. There is no tool that refunds without it, and the PayPal credentials never leave the server.
      </p>

      <section className="section">
        <div className="grid-2">
          <div className="arch" aria-label="Architecture">
            <div className="box"><b>Any agent</b><span>Our support agent, Claude Desktop, Cursor, your own</span></div>
            <div className="down">↓ MCP</div>
            <div className="box"><b>Remit MCP server</b><span>read tools, and request_refund</span></div>
            <div className="down">↓</div>
            <div className="box"><b>Remit guard</b><span>PayPal facts → code checks → AI panel → log</span></div>
            <div className="down">↓ only if allowed</div>
            <div className="box"><b>PayPal</b><span>Payments v2 refund, with an idempotency key</span></div>
          </div>
          <div className="stack">
            <h2 className="h3">The tools</h2>
            <div className="kv">
              {TOOLS.map(([n, d]) => (
                <div key={n}>
                  <code>{n}</code> <span className="muted small">{d}</span>
                </div>
              ))}
            </div>
            <h2 className="h3" style={{ marginTop: 16 }}>What decides what</h2>
            <div className="kv small">
              <div><span className="badge code">PayPal</span> the order, payment, refunds, tracking and disputes</div>
              <div><span className="badge code">Code</span> amounts, caps, windows, refundable balance, disputes, split detection</div>
              <div><span className="badge ai">AI panel</span> only whether a refund fits the written policy, given PayPal's records</div>
              <div><span className="badge ok">PayPal</span> the refund itself, and only when allowed</div>
            </div>
          </div>
        </div>
      </section>

      <section className="section">
        <h2 className="h3">Connect your own agent</h2>
        <p className="muted">
          Claude Desktop's <code>claude_desktop_config.json</code>. <code>REMIT_OFFLINE=1</code> uses the demo shop without keys; with
          a PayPal sandbox app and a model key, set <code>PAYPAL_CLIENT_ID</code>, <code>PAYPAL_CLIENT_SECRET</code> and{" "}
          <code>REMIT_MODEL_API_KEY</code> instead.
        </p>
        <pre className="code">{CLAUDE}</pre>
        <p className="small muted">
          Setup and the full configuration are in the <a href={REPO}>README</a>.
        </p>
      </section>

      <section className="section">
        <h2 className="h3">The engine underneath</h2>
        <p className="lede">
          The rules engine, the question the models are asked, and the fail-closed reading of their answers are Remit's own code,
          unchanged from Remit on GenLayer, where the same decisions are made by validators no single party runs.
        </p>
      </section>

      <section className="section">
        <h2 className="h3">Honest limits</h2>
        <ul className="limits">
          <li>Whoever runs the Remit server runs the panel and holds the refund keys. The log makes every decision checkable; it does not make the operator trustless.</li>
          <li>The panel judges what PayPal's records and the policy say. It cannot see whether a box really arrived broken.</li>
          <li>This demo uses the PayPal sandbox. No real money moves.</li>
        </ul>
      </section>
    </div>
  );
}
