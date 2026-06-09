"""Turn Managed Agents events into readable Slack thread replies.

Events follow a `{domain}.{action}` naming convention. The SDK delivers them
as objects; webhooks/`events.list` deliver dicts. `to_dict` normalizes both so
the same formatter handles either source.
"""
from __future__ import annotations

import json
from typing import Any

# Emoji prefix per event type for quick visual scanning in the thread.
_EMOJI = {
    "user.message": "🧑",
    "user.tool_confirmation": "✅",
    "user.custom_tool_result": "↩️",
    "agent.message": "🤖",
    "agent.thinking": "💭",
    "agent.tool_use": "🛠️",
    "agent.tool_result": "📤",
    "agent.mcp_tool_use": "🔌",
    "agent.custom_tool_use": "🧩",
    "session.status_running": "▶️",
    "session.status_idle": "⏸️",
    "session.status_idled": "⏸️",
    "session.error": "🔴",
    "session.outcome_evaluation_ended": "🎯",
    "span.started": "·",
    "span.ended": "·",
}


def to_dict(event: Any) -> dict:
    """Normalize an SDK event object or a raw dict into a plain dict."""
    if isinstance(event, dict):
        return event
    for attr in ("model_dump", "to_dict", "dict"):
        fn = getattr(event, attr, None)
        if callable(fn):
            try:
                return fn()
            except TypeError:
                return fn(mode="json") if attr == "model_dump" else fn()
    # Last resort: shallow vars()
    return {k: v for k, v in vars(event).items() if not k.startswith("_")}


def _text_blocks(content: Any) -> str:
    """Join the `text` of any text content blocks."""
    if not content:
        return ""
    parts = []
    for block in content:
        b = block if isinstance(block, dict) else to_dict(block)
        if b.get("type") == "text" and b.get("text"):
            parts.append(b["text"])
        elif b.get("type") == "thinking" and b.get("thinking"):
            parts.append(b["thinking"])
    return "\n".join(parts).strip()


def _code(value: Any, limit: int = 1500) -> str:
    # Render plain strings verbatim; only JSON-encode structured values so we
    # don't show escaped "\n" for ordinary text output.
    if isinstance(value, str):
        s = value
    else:
        try:
            s = json.dumps(value, indent=2, ensure_ascii=False, default=str)
        except Exception:  # noqa: BLE001
            s = str(value)
    if len(s) > limit:
        s = s[:limit] + "\n…"
    return f"```\n{s}\n```"


def format_event(event: Any) -> str | None:
    """Return Slack text for an event, or None to skip posting it."""
    e = to_dict(event)
    etype = e.get("type", "event")
    emoji = _EMOJI.get(etype, "•")
    head = f"{emoji} *{etype}*"

    if etype in ("user.message", "agent.message"):
        body = _text_blocks(e.get("content"))
        return f"{head}\n{body}" if body else head

    if etype == "agent.thinking":
        body = _text_blocks(e.get("content")) or e.get("thinking", "")
        return f"{head}\n_{body}_" if body else head

    if etype in ("agent.tool_use", "agent.mcp_tool_use", "agent.custom_tool_use"):
        name = e.get("name", "?")
        server = e.get("server_name") or e.get("server")
        label = f"{name}" + (f" @ {server}" if server else "")
        tool_input = e.get("input", e.get("arguments"))
        text = f"{head}: `{label}`"
        if tool_input:
            text += "\n" + _code(tool_input)
        return text

    if etype == "agent.tool_result":
        content = e.get("content")
        is_err = e.get("is_error")
        body = _text_blocks(content) if isinstance(content, list) else str(content)
        prefix = "🔴 error" if is_err else "result"
        return f"{head} ({prefix})\n{_code(body) if body else '_empty_'}"

    if etype == "session.error":
        err = e.get("error") or e.get("message") or e
        return f"{head}\n{_code(err)}"

    if etype == "session.status_idle" or etype == "session.status_idled":
        stop = e.get("stop_reason")
        if isinstance(stop, dict):
            return f"{head} — stop_reason: `{stop.get('type', stop)}`"
        return f"{head}" + (f" — stop_reason: `{stop}`" if stop else "")

    if etype == "session.outcome_evaluation_ended":
        return f"{head}\n{_code(e.get('outcome', e))}"

    # Spans are very chatty; skip by default unless explicitly enabled upstream.
    if etype.startswith("span."):
        return None

    # Fallback: dump a compact view of unknown event types so nothing is lost.
    slim = {k: v for k, v in e.items() if k not in ("processed_at",)}
    return f"{head}\n{_code(slim)}"


def parent_text(session: Any) -> str:
    """Header message for the thread root."""
    s = to_dict(session)
    sid = s.get("id", "unknown")
    return f":large_purple_circle: Managed Agent session {sid}"
