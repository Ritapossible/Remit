# Remit on PayPal: one image serving the API and the built web app.
# Built from the repository root, because the guard imports Remit's engine
# from contracts/ unchanged:
#
#   docker build -f paypal/Dockerfile -t remit-paypal .
#   docker run -p 8000:8000 -e REMIT_OFFLINE=1 remit-paypal

FROM node:20-slim AS web
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
WORKDIR /src/paypal/web
COPY paypal/web/package.json paypal/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY paypal/web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY paypal/requirements.txt paypal/requirements.txt
RUN pip install -r paypal/requirements.txt
COPY contracts/remit_core.py contracts/remit_prompts.py contracts/jury_common.py contracts/
COPY paypal/remit_paypal paypal/remit_paypal
COPY paypal/mandates paypal/mandates
COPY paypal/contracts paypal/contracts
COPY paypal/verify_anchor.py paypal/verify_anchor.py
COPY paypal/deploy/anchor-studio.json paypal/deploy/anchor-studio.json
COPY --from=web /src/paypal/web/dist paypal/web/dist
RUN useradd --create-home remit && chown -R remit /app
USER remit
WORKDIR /app/paypal
ENV REMIT_STATIC_DIR=/app/paypal/web/dist PORT=8000
EXPOSE 8000
# One worker: decisions for a shop are made one at a time, and the console's
# event stream lives in this process.
CMD ["sh", "-c", "exec uvicorn remit_paypal.web:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
