#!/usr/bin/env bash
# Put the API back online from your own machine, right now, with no new account.
#
# Railway's free credit ran out and the API went down. The permanent fix is a
# Hugging Face Space (see deploy/hf-space/SETUP.md). This is the stopgap for
# before that is set up: run the API locally and expose it through a Cloudflare
# Quick Tunnel, which needs no Cloudflare account and no port forwarding - it
# dials out and hands back a public HTTPS URL.
#
# What this buys over the static-snapshot alternative: the site keeps ALL of its
# behaviour - sign-in, chat, the visitor network, publishing settings, the
# Financial sliders. A snapshot can only ever be read-only.
#
# What it costs: this machine has to stay on and online, and a Quick Tunnel's
# URL changes every time the tunnel restarts. See "A STABLE URL" at the bottom.
#
#   Usage:  deploy/local-tunnel/serve.sh https://your-site.pages.dev
#
# The argument is the ORIGIN of the deployed dashboard, and it is required
# rather than defaulted: get it wrong and the browser blocks every API call
# under CORS, which shows up as a site that loads but stays empty, with the real
# reason buried in the console. Better to be asked than to debug that.

set -euo pipefail

SITE_ORIGIN="${1:-}"
PORT="${PORT:-8000}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
API_SRC="$REPO_ROOT/nongfab-ems/api/src"
STATE_DIR="$HERE/.state"

if [[ -z "$SITE_ORIGIN" ]]; then
  cat >&2 <<'USAGE'
usage: deploy/local-tunnel/serve.sh <site-origin>

  <site-origin>  the deployed dashboard's origin, scheme included and no
                 trailing slash, e.g. https://nongfab.pages.dev
                 Use http://localhost:5173 if you are also running the web
                 dev server locally.
USAGE
  exit 2
fi

if [[ "$SITE_ORIGIN" == */ ]]; then
  echo "error: drop the trailing slash - CORS compares origins exactly ('${SITE_ORIGIN%/}')" >&2
  exit 2
fi

if [[ ! -d "$API_SRC/nongfab_api" ]]; then
  echo "error: run this from inside the repo (looked for $API_SRC/nongfab_api)" >&2
  exit 1
fi

for bin in python3 cloudflared; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "error: '$bin' not found." >&2
    if [[ "$bin" == cloudflared ]]; then
      cat >&2 <<'INSTALL'
  macOS    brew install cloudflared
  Windows  winget install --id Cloudflare.cloudflared
  Linux    https://github.com/cloudflare/cloudflared/releases  (download the .deb/.rpm)
INSTALL
    fi
    exit 1
  fi
done

mkdir -p "$STATE_DIR"

# The JWT signing key is generated once and kept, not regenerated per run.
# Every issued token is signed with it, so a fresh key on each restart would
# silently log out everyone who was already signed in.
SECRET_FILE="$STATE_DIR/jwt_secret"
if [[ ! -f "$SECRET_FILE" ]]; then
  python3 -c "import secrets; print(secrets.token_hex(32))" > "$SECRET_FILE"
  chmod 600 "$SECRET_FILE"
  echo "==> generated a new JWT secret at $SECRET_FILE"
fi

if command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "error: something is already listening on port $PORT. Stop it, or re-run with PORT=8001" >&2
  exit 1
fi

API_LOG="$STATE_DIR/api.log"
TUNNEL_LOG="$STATE_DIR/tunnel.log"
: > "$API_LOG"
: > "$TUNNEL_LOG"

cleanup() {
  # Only ever kills the two children this script started itself.
  [[ -n "${API_PID:-}" ]] && kill "$API_PID" 2>/dev/null || true
  [[ -n "${TUNNEL_PID:-}" ]] && kill "$TUNNEL_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "==> starting the API on port $PORT"
(
  cd "$API_SRC"
  # SQLite, not the Postgres the defaults assume: there is no database server
  # here, and the file keeps users/settings/chat across restarts - which is
  # actually better than the Hugging Face Space, whose disk is wiped on reboot.
  API_TIMESCALE_DSN="sqlite+aiosqlite:///$STATE_DIR/auth.db" \
  API_SEED_DEMO_USERS=true \
  API_JWT_SECRET_KEY="$(cat "$SECRET_FILE")" \
  API_CORS_ORIGINS="$SITE_ORIGIN" \
  API_ENABLE_BACKGROUND_INGESTION="${API_ENABLE_BACKGROUND_INGESTION:-false}" \
  API_ENABLE_BACKGROUND_RETRAINING=false \
  PYTHONPATH="$API_SRC" \
  python3 -m uvicorn nongfab_api.main:app --host 127.0.0.1 --port "$PORT" --proxy-headers \
    >> "$API_LOG" 2>&1
) &
API_PID=$!

# Importing torch/mlflow/neuralprophet takes a while, so wait on /healthz
# actually answering rather than on a fixed sleep.
printf '    waiting for the API to come up'
for _ in $(seq 1 120); do
  if curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
    echo " - up"
    break
  fi
  if ! kill -0 "$API_PID" 2>/dev/null; then
    echo
    echo "error: the API exited during startup. Last lines of $API_LOG:" >&2
    tail -20 "$API_LOG" >&2
    exit 1
  fi
  printf '.'
  sleep 2
done

if ! curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
  echo
  echo "error: the API never answered /healthz. See $API_LOG" >&2
  exit 1
fi

echo "==> opening a Cloudflare Quick Tunnel (no account needed)"
cloudflared tunnel --url "http://127.0.0.1:$PORT" >> "$TUNNEL_LOG" 2>&1 &
TUNNEL_PID=$!

PUBLIC_URL=""
for _ in $(seq 1 60); do
  PUBLIC_URL="$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" | head -1 || true)"
  [[ -n "$PUBLIC_URL" ]] && break
  if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
    echo "error: cloudflared exited. Last lines of $TUNNEL_LOG:" >&2
    tail -20 "$TUNNEL_LOG" >&2
    exit 1
  fi
  sleep 2
done

if [[ -z "$PUBLIC_URL" ]]; then
  echo "error: could not read a tunnel URL out of $TUNNEL_LOG" >&2
  exit 1
fi

# Prove the whole path works from the outside before claiming it does - the
# tunnel printing a URL is not the same as that URL reaching this API.
printf '    verifying the public URL'
HEALTH=""
for _ in $(seq 1 20); do
  HEALTH="$(curl -fsS --max-time 5 "$PUBLIC_URL/healthz" 2>/dev/null || true)"
  [[ -n "$HEALTH" ]] && break
  printf '.'
  sleep 2
done
echo

# Say which of these two things actually happened. "Live" when the public URL
# was never reached would send someone off to reconfigure Cloudflare Pages
# against a URL that does not work, and the real problem would surface much
# later and much less clearly.
if [[ -n "$HEALTH" ]]; then
  STATUS_LINE="API is live at:  $PUBLIC_URL"
  STATUS_NOTE="  verified from outside: /healthz -> $HEALTH"
else
  STATUS_LINE="Tunnel URL:      $PUBLIC_URL"
  STATUS_NOTE="  ⚠️  NOT verified - the tunnel opened but that URL did not answer /healthz.
  The API itself is up (it answered on 127.0.0.1:$PORT), so this is the tunnel.
  Check $TUNNEL_LOG, and try the URL in a browser before changing VITE_API_URL."
fi

cat <<EOF

──────────────────────────────────────────────────────────────
  $STATUS_LINE
$STATUS_NOTE

  NEXT, so the website uses it:
    Cloudflare Pages -> your project -> Settings ->
      Environment variables -> VITE_API_URL = $PUBLIC_URL
    then Deployments -> Retry deployment

  Demo sign-ins (seeded automatically):
    pttlng / 12345            viewer
    operator / operator-demo-pw
    admin / admin-demo-pw

  Logs:  $API_LOG
         $TUNNEL_LOG
  Data:  $STATE_DIR/auth.db   (kept across restarts)

  Ctrl-C stops both the API and the tunnel.
──────────────────────────────────────────────────────────────

EOF

# ── A STABLE URL ────────────────────────────────────────────────────────────
# A Quick Tunnel gets a new hostname every time it starts, so VITE_API_URL has
# to be updated on each restart. To stop that, use a NAMED tunnel - it needs no
# new signup, only the Cloudflare account already hosting the site:
#
#   cloudflared tunnel login
#   cloudflared tunnel create nongfab-api
#   cloudflared tunnel route dns nongfab-api api.<your-domain>
#   cloudflared tunnel run --url http://127.0.0.1:8000 nongfab-api
#
# Then VITE_API_URL points at api.<your-domain> permanently.
#
# ── LIVE WEATHER ────────────────────────────────────────────────────────────
# Background ingestion is off by default here so startup is quick and this
# machine is not polling GFS and Himawari all day. Without it the 9-variable
# table and the weather strip stay empty. Turn it on with:
#
#   API_ENABLE_BACKGROUND_INGESTION=true deploy/local-tunnel/serve.sh <origin>

wait "$API_PID"
