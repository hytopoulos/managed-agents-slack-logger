# Deploying the webhook server

The webhook catch-all needs a **public HTTPS endpoint on port 443** (Anthropic's
webhooks require it) and a **persistent disk** for the SQLite state. Any
container host that provides both works — Railway, Fly.io, Render, a VM with
nginx + Let's Encrypt, etc. Railway is used below as the worked example because
it provides HTTPS and a volume with the least setup.

## Two things that matter on any host

**1. Persistent volume.** `webhook_server.py` stores `session_id → Slack thread`
and the de-dupe ledger in a SQLite file. Most containers have ephemeral disk
that resets on redeploy — without a volume, the server forgets which thread
belongs to which session and starts fresh ones. Mount a volume and point
`LOGGER_STATE_DB` at it (e.g. `/data/state.db`).

**2. Single instance.** SQLite is local to one container. Run **1 replica**, or
swap the store for a managed database if you need to scale out. The included
`railway.json` pins `numReplicas: 1`.

---

## Railway (worked example)

### 1. Get the code in
Push the repo to GitHub, then in Railway: **New Project → Deploy from GitHub
repo**. Railway detects the `Dockerfile` and builds from it. (Or use the CLI:
`npm i -g @railway/cli && railway login && railway init && railway up`.)

### 2. Add a volume
Service → **Settings → Volumes → New Volume**. Mount path `/data`, 1 GB.

### 3. Set environment variables
Service → **Variables**:

| Variable | Value |
|----------|-------|
| `ANTHROPIC_API_KEY` | your `sk-ant-…` key |
| `SLACK_BOT_TOKEN` | `xoxb-…` |
| `SLACK_CHANNEL` | `agent-sessions` |
| `LOGGER_STATE_DB` | `/data/state.db` |
| `ANTHROPIC_WEBHOOK_SIGNING_KEY` | `whsec_…` (fill in after step 5) |

Don't set `PORT` — the host injects it and the Dockerfile reads it.

### 4. Get the public URL
Service → **Settings → Networking → Generate Domain**. Your endpoint is that
URL + `/webhook`. Check it's alive:
```bash
curl https://YOUR-DOMAIN/healthz   # -> ok
```

### 5. Register the webhook
Console → **Manage → Webhooks → Add endpoint**:
- **URL:** your `/webhook` URL
- **Event types:** subscribe to the `session.*` events
- Save, copy the **signing secret** (`whsec_…`), and put it in the
  `ANTHROPIC_WEBHOOK_SIGNING_KEY` variable. The service redeploys.

### 6. Test
Send a **test event** from the Console webhook page and confirm a `200` in the
logs. Then start a real session anywhere — within seconds a thread appears in
`#agent-sessions` and fills with events.

---

## Other hosts

- **Fly.io** — `fly launch` (it reads the Dockerfile), `fly volumes create data`,
  mount at `/data`, set the same env vars with `fly secrets set`. Keep
  `min_machines_running = 1` and a single machine.
- **Render** — Web Service from the repo (Docker), add a Disk mounted at `/data`,
  set env vars. Render provides HTTPS automatically.
- **Your own VM** — run the container (or `gunicorn ... webhook_server:app`)
  behind nginx with a Let's Encrypt cert on 443; bind-mount a host directory for
  `/data`.

## Troubleshooting

- **Endpoint auto-disabled in Console.** Anthropic disables an endpoint after
  ~20 consecutive failures, or immediately on a redirect or private-IP hostname.
  Fix the cause, check logs, re-enable in the Console.
- **`invalid signature` (400).** `ANTHROPIC_WEBHOOK_SIGNING_KEY` doesn't match
  the endpoint's secret. Re-copy it.
- **Nothing posts, no errors.** Bot isn't in the channel or missing
  `chat:write` / `channels:read`. Invite it and recheck scopes.
- **New thread after each redeploy.** Volume not mounted or `LOGGER_STATE_DB`
  not pointing at it.
- **Duplicate replies.** Shouldn't happen — the store de-dupes by event id. If
  you run the streamer and webhook server separately, point both at the same
  `LOGGER_STATE_DB`, or run only one.
