"""Log every Claude Managed Agents session to a Slack channel, one thread per
session, one threaded reply per event.

Three ways to use it:

  1. Drop-in session creation (recommended -- real-time, every event):

        from agent_logger import create_logged_session
        session = create_logged_session(
            client, agent=AGENT_ID, environment_id=ENV_ID, title="Nightly job"
        )
        # ... send events / stream as usual; logging runs in the background.

  2. Attach to a session you already created elsewhere:

        from agent_logger import attach
        attach(client, session_id)          # blocks, streaming to Slack
        attach(client, session_id, background=True)   # non-blocking

  3. CLI tail:

        python agent_logger.py <session_id>

The logger opens its own SSE stream, so it never consumes events your
application also needs -- each consumer gets the full stream independently.
"""
from __future__ import annotations

import sys
import threading
from typing import Any

import config
from formatting import format_event, parent_text, to_dict
from slack_client import post_parent, post_reply, resolve_channel_id
from store import get_thread, mark_posted, save_thread


def _should_post(event_type: str) -> bool:
    if config.EVENT_FILTER is None:
        return True
    return event_type in config.EVENT_FILTER


def ensure_thread(client: Any, session_id: str) -> tuple[str, str]:
    """Return (channel_id, thread_ts) for a session, creating the Slack thread
    (parent message) on first sight. Idempotent across processes."""
    existing = get_thread(session_id)
    if existing:
        return existing

    channel_id = resolve_channel_id(config.SLACK_CHANNEL)
    # Fetch session metadata for a richer header; fall back to bare id.
    try:
        session = client.beta.sessions.retrieve(session_id)
        header = parent_text(session)
    except Exception:  # noqa: BLE001
        header = parent_text({"id": session_id})

    thread_ts = post_parent(channel_id, header)
    save_thread(session_id, channel_id, thread_ts)
    return channel_id, thread_ts


def log_event(session_id: str, channel_id: str, thread_ts: str, event: Any) -> None:
    """Post a single event as a threaded reply, de-duplicated by event id."""
    e = to_dict(event)
    etype = e.get("type", "event")
    if not _should_post(etype):
        return

    text = format_event(event)
    if text is None:
        return

    event_id = e.get("id")
    # De-dupe only when an id is present (streamed deltas may lack one).
    if event_id and not mark_posted(session_id, event_id):
        return  # already posted by another consumer

    post_reply(channel_id, thread_ts, text)


def stream_to_slack(client: Any, session_id: str) -> None:
    """Open the SSE event stream for a session and mirror every event into the
    session's Slack thread until the session ends."""
    channel_id, thread_ts = ensure_thread(client, session_id)

    with client.beta.sessions.events.stream(session_id) as stream:
        for event in stream:
            try:
                log_event(session_id, channel_id, thread_ts, event)
            except Exception as exc:  # noqa: BLE001 -- never kill the stream on a Slack hiccup
                print(f"[agent-logger] failed to post event: {exc}", file=sys.stderr)

            etype = to_dict(event).get("type", "")
            if etype in ("session.status_idle", "session.status_idled"):
                stop = to_dict(event).get("stop_reason")
                stop_type = stop.get("type") if isinstance(stop, dict) else stop
                # Keep streaming through tool-confirmation pauses; stop on end_turn.
                if stop_type in (None, "end_turn", "max_turns", "completed"):
                    break


def attach(client: Any, session_id: str, background: bool = False) -> threading.Thread | None:
    """Start mirroring an existing session to Slack.

    background=False blocks until the session ends. background=True returns a
    daemon thread immediately.
    """
    config.require("SLACK_BOT_TOKEN")
    if background:
        t = threading.Thread(
            target=stream_to_slack, args=(client, session_id), daemon=True,
            name=f"agent-logger:{session_id}",
        )
        t.start()
        return t
    stream_to_slack(client, session_id)
    return None


def create_logged_session(client: Any, **kwargs: Any):
    """Drop-in replacement for `client.beta.sessions.create(...)` that also
    opens a Slack thread and starts background logging for the new session.

    Pass the same arguments you'd pass to sessions.create (agent,
    environment_id, title, vault_ids, ...). Returns the created session.
    """
    config.require("SLACK_BOT_TOKEN")
    session = client.beta.sessions.create(**kwargs)
    # Create the thread immediately so the parent message exists before any
    # events arrive, then stream in the background.
    ensure_thread(client, session.id)
    attach(client, session.id, background=True)
    return session


def _cli() -> None:
    if len(sys.argv) < 2:
        print("usage: python agent_logger.py <session_id>", file=sys.stderr)
        raise SystemExit(2)

    config.require("ANTHROPIC_API_KEY", "SLACK_BOT_TOKEN")
    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    session_id = sys.argv[1]
    print(f"[agent-logger] streaming {session_id} -> #{config.SLACK_CHANNEL} …")
    stream_to_slack(client, session_id)
    print("[agent-logger] session ended.")


if __name__ == "__main__":
    _cli()
