# Hosting Remit on PayPal for free

The GenLayer app stays on Vercel (`frontend/`). Remit on PayPal is a
server, not a static site: it holds secrets (PayPal, the models, the
GenLayer operator key), keeps the live console's event stream open, anchors
the log in the background, and stores the decision log. It runs on
**Render's free web service** with the log in a **free Neon Postgres**
database. Neither asks for a card.

| Piece | Free tier | Why it is needed |
| --- | --- | --- |
| Render web service (`render.yaml`, `paypal/Dockerfile`) | 750 hours a month; sleeps after 15 minutes idle | Runs the server and serves the web app |
| Neon Postgres | No expiry | Render's free disk does not persist; the log must survive sleep and redeploys, or anchoring breaks |
| A keep-awake ping (for example cron-job.org) | Free | Calls `/api/health` every 10 minutes so judges never wait for a cold start; one service awake all month is about 744 hours, inside the 750 |

## Steps

1. **Neon.** Sign up at neon.tech with GitHub. Create a project. Copy the
   connection string; it looks like
   `postgresql://user:password@host/dbname?sslmode=require`.
2. **A RemitAnchor for the hosted log.** Done: `0xD48D5034184B1e78a36403905515fEcA4e56F6D6`
   on GenLayer Studio (`deploy/anchor-studio-hosted.json`), with the same
   operator as the other Remit anchors. Each log needs its own contract,
   because the contract refuses entry numbers that are not after the last
   one it holds; a new log would need a new one:
   ```bash
   cd paypal
   REMIT_KEYS_DIR=<private folder holding anchor-operator.key> \
     .venv/bin/python deploy/deploy_anchor.py "<log name>" <record>.json
   ```
3. **Render.** Sign up at render.com with GitHub and allow access to the
   Remit repository. Choose **New → Blueprint**, pick the repository and the
   branch, and Render reads `render.yaml`. Choose the **Free** plan if
   asked. Do not add a disk: disks are what make Render ask for a card.
4. **Environment variables**, in the service's Environment tab:
   | Key | Value |
   | --- | --- |
   | `REMIT_DB` | the Neon connection string |
   | `REMIT_ANCHOR_CONTRACT` | `0xD48D5034184B1e78a36403905515fEcA4e56F6D6` |
   | `REMIT_ANCHOR_KEY` | `0x` + the operator key |
   | `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` | the sandbox REST app, on a **US** sandbox business account (the demo shop pays by card, which other countries' sandbox accounts refuse); then set `REMIT_OFFLINE` to `0` |
   | `REMIT_MODEL_API_KEY`, `REMIT_MODEL_BASE_URL`, `REMIT_AGENT_MODEL`, `REMIT_PANEL_MODELS` | the model key, the API's address and the model ids (the hosted demo: Groq, `https://api.groq.com/openai/v1`, `openai/gpt-oss-120b`, `qwen/qwen3.8-27b,openai/gpt-oss-20b`) |

   Until the PayPal and model keys are set, `REMIT_OFFLINE=1` runs the demo
   shop on a fake PayPal with stand-in models, so the site works from day
   one. The demo page says so in a banner while it does.
5. **Keep it awake.** At cron-job.org, add a job that calls
   `https://<service>.onrender.com/api/health` every 10 minutes.
6. **Check it.** Open the site and the decision log, then from any machine:
   ```bash
   .venv/bin/python verify_anchor.py https://<service>.onrender.com 0xD48D5034184B1e78a36403905515fEcA4e56F6D6
   ```

## Tested before it was written

The image was built and run here as Render runs it: free-plan settings,
the hosted-demo mandate, the log in Postgres, live anchoring on GenLayer
Studio.

- The browser test passed in full.
- After a restart, all 21 log entries were still there and still matched
  the contract (`deploy/anchor-studio-container-test.json`).
- Run against a contract that already anchored another log, the server
  refused to count the anchor and said why.
