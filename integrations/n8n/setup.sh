#!/usr/bin/env bash
# Start local n8n, import the Karsa intake workflow and publish it so its webhook is live.
# Local only. No n8n Cloud account; the owner account below exists only inside this container.
set -euo pipefail
cd "$(dirname "$0")"

compose() { if docker compose version >/dev/null 2>&1; then docker compose "$@"; else docker-compose "$@"; fi; }

if [ ! -f .env ]; then
  cp .env.example .env
  rand() { openssl rand -hex 24; }
  sed -i.bak -e "s/^N8N_ENCRYPTION_KEY=.*/N8N_ENCRYPTION_KEY=$(rand)/" \
             -e "s/^KARSA_INTAKE_SECRET=.*/KARSA_INTAKE_SECRET=$(rand)/" \
             -e "s/^N8N_OWNER_PASSWORD=.*/N8N_OWNER_PASSWORD=Owner-$(rand)/" .env && rm -f .env.bak
  echo "Created .env with random secrets."
fi
mkdir -p files

compose up -d
echo -n "Waiting for n8n"
until curl -fs http://127.0.0.1:5678/healthz >/dev/null 2>&1; do echo -n "."; sleep 2; done; echo " up."

compose exec -T n8n n8n import:workflow --input=/workflows/karsa-intake.json
compose exec -T n8n n8n publish:workflow --id=KarsaIntake00001
compose restart n8n >/dev/null
until curl -fs http://127.0.0.1:5678/healthz >/dev/null 2>&1; do sleep 2; done

# Owner account for the local editor (needed only to look at the workflow in the browser).
set -a; . ./.env; set +a
owner_body="{\"email\":\"$N8N_OWNER_EMAIL\",\"firstName\":\"Local\",\"lastName\":\"Owner\",\"password\":\"$N8N_OWNER_PASSWORD\"}"
for _ in $(seq 1 15); do  # the REST API answers a few seconds after /healthz
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:5678/rest/owner/setup \
    -H 'Content-Type: application/json' -d "$owner_body")
  case "$code" in
    200) echo "Local owner account created ($N8N_OWNER_EMAIL)."; break ;;
    400) echo "Local owner account already exists."; break ;;
    *) sleep 2 ;;
  esac
done

echo "Webhook: POST http://127.0.0.1:5678/webhook/karsa-intake  (header X-Intake-Secret from .env)"
echo "Editor:  http://127.0.0.1:5678  (sign in with N8N_OWNER_EMAIL / N8N_OWNER_PASSWORD from .env)"
