"""Webhook catch-all: log sessions started anywhere in the workspace.

The streamer (agent_logger) is the real-time path, but it only sees sessions
you create through it. Webhooks fire for EVERY session in the workspace, so
this server guarantees nothing is missed -- even sessions started from the
Console or another service.

Webhooks carry only {type, id}, not event bodies. So on each webhook we:
  1. Ensure the session's Slack thread exists.
  2. Pull the full event list with events.list and post any events not yet
     posted (de-duplicated via the shared store), preserving order.

The backfill runs on a background thread so the HTTP handler returns 200
immediately -- long histories won't trip Anthropic's delivery timeout/retries.

Register the endpoint at Console > Manage > Webhooks, subscribe to the
session.* events, and set ANTHROPIC_WEBHOOK_SIGNING_KEY to the whsec_ secret.

Run (production):  gunicorn --bind 0.0.0.0:$PORT webhook_server:app
Run (local dev):   python webhook_server.py
Must sit behind HTTPS on port 443 (most PaaS hosts provide this automatically).
"""
from __future__ import annotations

import sys
import threading

from flask import Flask, request

import config
from agent_logger import ensure_thread, log_event
from formatting import to_dict

app = Flask(__name__)

# One shared Anthropic client. Reads ANTHROPIC_API_KEY (and the webhook signing
# key) from the environment.
import anthropic  # noqa: E402

_client = anthropic.Anthropic()


def _backfill_session(session_id: str) -> None:
    """Post any not-yet-posted events for a session into its Slack thread.
    Safe to run concurrently -- the store de-dupes by event id."""
    try:
        channel_id, thread_ts = ensure_thread(_client, session_id)
        # events.list paginates oldest-first; iterate the whole history so a
        # single late webhook still backfills everything.
        for event in _client.beta.sessions.events.list(session_id):
            try:
                log_event(session_id, channel_id, thread_ts, event)
            except Exception as exc:  # noqa: BLE001
                print(f"[webhook] post failed: {exc}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"[webhook] backfill error for {session_id}: {exc}", file=sys.stderr)


@app.route("/webhook", methods=["POST"])
def webhook():
    raw = request.get_data(as_text=True)
    try:
        # unwrap() verifies the X-Webhook-Signature header and rejects stale or
        # forged payloads. Reads ANTHROPIC_WEBHOOK_SIGNING_KEY from env.
        event = _client.beta.webhooks.unwrap(raw, headers=dict(request.headers))
    except Exception:  # noqa: BLE001
        return "invalid signature", 400

    data = to_dict(getattr(event, "data", event))
    etype = data.get("type", "")
    session_id = data.get("id", "")

    # All session.* webhook types reference a session id we can backfill from.
    # Hand off to a background thread and ack immediately.
    if etype.startswith("session.") and session_id:
        threading.Thread(
            target=_backfill_session, args=(session_id,), daemon=True,
            name=f"backfill:{session_id}",
        ).start()

    return "", 200


@app.route("/healthz", methods=["GET"])
def healthz():
    return "ok", 200


if __name__ == "__main__":
    import os

    config.require("ANTHROPIC_API_KEY", "SLACK_BOT_TOKEN", "WEBHOOK_SIGNING_KEY")
    port = int(os.environ.get("PORT", "8080"))
    print(f"[webhook] listening on :{port}  -> #{config.SLACK_CHANNEL}")
    app.run(host="0.0.0.0", port=port)
