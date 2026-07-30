# Moving the API off Railway onto a free Hugging Face Space

Written 2026-07-30, after the Railway trial on the project's Google account ran
out. Only the **API** moves. The website (Cloudflare Pages) and the GitHub repo
are unaffected and stay free.

## What is and is not at risk

- **GitHub is not at risk.** Free accounts do not expire, and sharing an email
  address with Railway does not connect the two billing-wise. The repo,
  branches and Actions keep working.
- **Cloudflare Pages is not at risk.** Its free tier is separate. When the API
  is down the site still loads; only the data panels fail.
- **Railway cannot charge a card it does not have.** Verify under
  Railway → Settings → Billing that no payment method is stored, and remove it
  if one is. After the trial, Railway drops the project to the free plan
  ($1/month of credit) and stops the container rather than invoicing.
- **Do not open a second Railway account to get another trial.** That breaks
  their terms of service and risks losing the project entirely.

## Why Hugging Face Spaces for this app specifically

Free HF hardware is 2 vCPU / 16 GB RAM with no credit card. The 16 GB matters:
this API imports `torch` (via `neuralforecast`/`neuralprophet`), `lightgbm` and
`mlflow`, which does not fit the 512 MB that most free tiers offer.

The usual dealbreaker with Spaces — **no persistent disk** — costs this app
almost nothing, because it already runs that way: `API_REAL_DATA_DB_PATH`
defaults to an in-memory store, and `create_tables_on_startup` rebuilds the
auth table on boot.

Two real downsides, stated plainly:

- The Space **sleeps after 48 hours with no visitors**; the next visitor waits
  through a cold start.
- Accumulated real weather history and any trained model are **lost on every
  restart**. That was already true between Railway redeploys unless a Volume
  was attached, but on a free Space it is unconditional. The site falls back to
  its physics baseline and labels itself as such, so it degrades honestly
  rather than showing stale numbers.

## Steps

### 1. Create the Space

<https://huggingface.co/new-space> → SDK **Docker** → blank template.
Note the id, e.g. `your-name/nongfab-solar-api`.

Public is fine and simpler; the code is already on GitHub and no secret lives
in the repo. Choose Private if you would rather, it does not change the setup.

### 2. Push the code

From the source repo root:

```bash
deploy/hf-space/push.sh your-name/nongfab-solar-api
```

Git will ask for a password — paste a **Write** token from
<https://huggingface.co/settings/tokens>. HF does not accept the account
password over git.

Build takes a while the first time (it compiles nothing, but the wheels are
large). Watch it at `https://huggingface.co/spaces/<id>?logs=build`.

The API's public base URL is then:

```
https://<your-name>-<space-name>.hf.space
```

(username and space name joined with a hyphen, lowercased.)

### 3. Set the Space's variables and secrets

Space → **Settings** → *Variables and secrets*.

As **Secrets** (values must not be public):

| Name | Value |
| --- | --- |
| `API_JWT_SECRET_KEY` | a long random string — **required**; the built-in default is an insecure dev placeholder and must never be used on a live deploy |

As **Variables**:

| Name | Value | Why |
| --- | --- | --- |
| `API_CORS_ORIGINS` | the Cloudflare Pages site URL, e.g. `https://nongfab.pages.dev` | The browser blocks every API call without this. Comma-separated for more than one origin, no spaces needed. |
| `API_TIMESCALE_DSN` | `sqlite+aiosqlite:///./auth.db` | The default points at a Postgres that does not exist here. This keeps the zero-setup SQLite auth store the demo already relies on. |
| `API_SEED_DEMO_USERS` | `true` | The auth DB is rebuilt on every restart, so the demo logins have to be re-seeded or nobody can sign in. |
| `API_ENABLE_BACKGROUND_RETRAINING` | `false` | Training inside the request process is what makes a small instance fall over. Leave off. |
| `API_ENABLE_BACKGROUND_INGESTION` | `false` to start | Turn on later if you want live weather accumulation. It costs memory and outbound requests, and its results are wiped on restart anyway. |

### 4. Point the website at the new API

`nongfab-ems/web/.env.production`:

```
VITE_API_URL=https://your-name-nongfab-solar-api.hf.space
```

Commit and push — Cloudflare Pages rebuilds on its own. If the URL is set as a
Cloudflare build environment variable instead of in this file, change it there.

### 5. Check it end to end

```bash
curl -sS https://your-name-nongfab-solar-api.hf.space/healthz
```

Expect `{"status":"ok"}`. (The path is `/healthz`, not `/health` — `/health`
returns 404, verified against a real boot on 2026-07-30.)

Then open the site and confirm a data panel fills in, and that signing in
works. A CORS error in the browser console means step 3's `API_CORS_ORIGINS`
does not exactly match the site's origin (scheme included, no trailing slash).

### 6. Only then, shut Railway down

Once the site works against the Space, delete the Railway service so nothing
can accrue against it. Keep the old URL written down until you are confident.

## Keeping it awake (optional)

A free uptime pinger (e.g. UptimeRobot) hitting `/healthz` every few minutes
prevents the 48-hour sleep. Reasonable for a demo that needs to be presentable
on demand; skip it if occasional cold starts are acceptable.

## If the build fails

- **Out of space / very slow:** check the CPU-only torch step in the Dockerfile
  actually ran. If pip fetched the CUDA build instead, the image jumps by about
  2.5 GB.
- **Permission denied on startup:** every `COPY` needs `--chown=user`; the
  container runs as uid 1000.
- **Space starts then immediately 500s:** almost always `API_TIMESCALE_DSN`
  still pointing at Postgres. Check the runtime logs, not the build logs.
