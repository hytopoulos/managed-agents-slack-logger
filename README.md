# managed-agents-slack-logger

Mirror every [Claude Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview)
session to Slack — **one thread per session, one threaded reply per event**
(user/agent messages, tool calls, tool results, thinking, status changes,
errors, outcomes).

![status: beta](https://img.shields.io/badge/status-beta-orange)
![license: MIT](https://img.shields.io/badge/license-MIT-blue)
![python: 3.10+](https://img.shields.io/badge/python-3.10%2B-green)

> Built for the Managed Agents public beta (`managed-agents-2026-04-01`).

## Why

Managed Agents run autonomously on Anthropic's infrastructure. This gives your
team a live, readable audit trail in Slack without standing up an observability
stack: open the channel, see every session as its own thread, and expand it to
watch the agent's messages and tool calls unfold.

## How it works

The Managed Agents API exposes session activity two ways, and this project uses
both so nothing is missed:

| Mechanism | Granularity | Covers |
|-----------|-------------|--------|
| **SSE event stream** (`sessions.events.stream`) | every event, real-time | sessions you stream |
| **Webhooks** | coarse milestones (`{type, id}` only) | every session in the workspace |

- **`agent_logger.py`** — real-time path. Streams a session's full event feed
  and posts each event as a thread reply. Use it as a drop-in wrapper around
  session creation, attach to an existing session, or run as a CLI tail. It
  opens its own stream, so it never steals events from your app.
- **`webhook_server.py`** — catch-all. Receives workspace webhooks and backfills
  the full event list of any session into its thread — including sessions
  started from the Console or another service. A shared SQLite store
  (`store.py`) de-dupes so a session logged by both paths never double-posts.

Pick the streamer alone if every session is created in your own code. Add the
webhook server if sessions can originate anywhere.

## Quick start

```bash
git clone https://github.com/<you>/managed-agents-slack-logger
cd managed-agents-slack-logger
pip install -r requirements.txt
cp .env.example .env        # then fill it in
```

**Anthropic:** create an API key in the [Console](https://platform.claude.com/settings/keys)
with Managed Agents access.

**Slack app** (https://api.slack.com/apps → *From scratch*): under **OAuth &
Permissions** add bot scopes `chat:write` and `channels:read` (add `groups:read`
for a private channel). Install to the workspace, copy the **Bot User OAuth
Token** (`xoxb-…`), then **invite the bot to the channel**: `/invite @your-bot`.

Sanity-check auth:
```bash
python -c "import config; from slack_client import resolve_channel_id; print('channel:', resolve_channel_id(config.SLACK_CHANNEL))"
```
A `C…` channel ID means token + channel are good.

## Usage

### A. Drop-in session creation (real-time)
Replace `client.beta.sessions.create(...)` with `create_logged_session(...)`:
```python
import anthropic
from agent_logger import create_logged_session

client = anthropic.Anthropic()
session = create_logged_session(
    client, agent=AGENT_ID, environment_id=ENV_ID, title="Nightly job"
)
```
Runnable demo: `python example_run.py`.

### B. Attach to an existing session
```python
from agent_logger import attach
attach(client, session_id)                    # blocks until the session ends
attach(client, session_id, background=True)   # non-blocking daemon thread
```

### C. CLI tail
```bash
python agent_logger.py sesn_01ABC...
```

### D. Webhook catch-all (every session, anywhere)
Needs a public HTTPS endpoint, so it runs as a hosted service. See
**[DEPLOY.md](DEPLOY.md)** for a step-by-step guide (Railway is used as the
worked example, but any container host with a persistent volume works).

Local dev:
```bash
python webhook_server.py        # Flask dev server on :8080
# expose with a tunnel for testing only, e.g.: ngrok http 8080
```

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `ANTHROPIC_API_KEY` | — | Managed Agents auth (required) |
| `SLACK_BOT_TOKEN` | — | Slack bot token `xoxb-…` (required) |
| `SLACK_CHANNEL` | `agent-sessions` | Channel name or ID |
| `ANTHROPIC_WEBHOOK_SIGNING_KEY` | — | Webhook verification `whsec_…` (webhook server only) |
| `LOGGER_STATE_DB` | `./state.db` | SQLite path (use a mounted volume when hosting) |
| `LOGGER_EVENT_FILTER` | `*` | Comma-separated event types, or `*` for all |
| `LOGGER_MAX_TEXT` | `2800` | Truncate replies beyond this many chars |

## Verifying locally

No live credentials required — the event formatter is pure:
```python
from formatting import format_event
print(format_event({"type": "agent.tool_use", "name": "bash", "input": {"command": "ls"}}))
# 🛠️ *agent.tool_use*: `bash`
# ```
# { "command": "ls" }
# ```
```

## Project layout

```
config.py          env-driven configuration
slack_client.py    Slack Web API (channel resolution, parent + replies)
store.py           SQLite: session_id -> thread_ts and posted-event de-dupe
formatting.py      event -> Slack text, per-type emoji and code blocks
agent_logger.py    streamer, drop-in wrapper, attach, CLI
webhook_server.py  Flask webhook receiver + background backfill
example_run.py     end-to-end demo
Dockerfile         container image (gunicorn)
railway.json       deploy config (1 replica, healthcheck)
DEPLOY.md          hosting walkthrough
```

## Notes & limits

- **`span.*` events are skipped by default** (high-volume tracing spans).
  Include them via `LOGGER_EVENT_FILTER`.
- The webhook server backfills on a background thread and acks `200`
  immediately, so large session histories don't trip Anthropic's retry timeout.
- The SQLite store is local to one process/container — run the webhook service
  at **1 replica** (set in `railway.json`), or swap the store for a managed DB
  if you need to scale out.
- Event field names track the `managed-agents-2026-04-01` beta; the formatter
  degrades gracefully (dumps unknown event types verbatim) if the schema shifts.

## License

[MIT](LICENSE). Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

> Not an official Anthropic project.
