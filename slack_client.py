"""Minimal Slack Web API client for posting a parent message and threaded
replies. No third-party Slack SDK required -- just `requests`.

Required bot scopes: chat:write, channels:read (and groups:read if the
channel is private). The bot must be a member of the target channel.
"""
from __future__ import annotations

import time

import requests

from config import MAX_TEXT, SLACK_BOT_TOKEN

_API = "https://slack.com/api"
_channel_cache: dict[str, str] = {}


class SlackError(RuntimeError):
    pass


def _post(method: str, payload: dict) -> dict:
    resp = requests.post(
        f"{_API}/{method}",
        json=payload,
        headers={
            "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
            "Content-Type": "application/json; charset=utf-8",
        },
        timeout=30,
    )
    data = resp.json()
    if not data.get("ok"):
        err = data.get("error", "unknown_error")
        # Respect Slack rate limits with a single polite retry.
        if err == "ratelimited":
            time.sleep(int(resp.headers.get("Retry-After", "1")))
            return _post(method, payload)
        raise SlackError(f"Slack {method} failed: {err}")
    return data


def _get(method: str, params: dict) -> dict:
    resp = requests.get(
        f"{_API}/{method}",
        params=params,
        headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
        timeout=30,
    )
    data = resp.json()
    if not data.get("ok"):
        raise SlackError(f"Slack {method} failed: {data.get('error')}")
    return data


def resolve_channel_id(channel: str) -> str:
    """Accept a channel ID, '#name', or 'name' and return the channel ID."""
    channel = channel.strip()
    if channel.startswith("#"):
        channel = channel[1:]
    # Looks like an ID already (C…, G…, D…).
    if channel[:1] in {"C", "G", "D"} and channel.isupper() and len(channel) >= 9:
        return channel
    if channel in _channel_cache:
        return _channel_cache[channel]

    cursor = ""
    while True:
        data = _get(
            "conversations.list",
            {
                "limit": 1000,
                "types": "public_channel,private_channel",
                "cursor": cursor,
            },
        )
        for ch in data.get("channels", []):
            if ch.get("name") == channel:
                _channel_cache[channel] = ch["id"]
                return ch["id"]
        cursor = data.get("response_metadata", {}).get("next_cursor", "")
        if not cursor:
            break
    raise SlackError(
        f"Channel '{channel}' not found. Create it and invite the bot, "
        "or set SLACK_CHANNEL to the channel ID."
    )


def _truncate(text: str) -> str:
    if len(text) <= MAX_TEXT:
        return text
    return text[: MAX_TEXT - 20] + "\n…(truncated)"


def post_parent(channel_id: str, text: str) -> str:
    """Post the thread-root message. Returns its `ts` (the thread id)."""
    data = _post(
        "chat.postMessage",
        {"channel": channel_id, "text": _truncate(text), "unfurl_links": False},
    )
    return data["ts"]


def post_reply(channel_id: str, thread_ts: str, text: str) -> str:
    """Post a threaded reply under thread_ts. Returns the reply `ts`."""
    data = _post(
        "chat.postMessage",
        {
            "channel": channel_id,
            "thread_ts": thread_ts,
            "text": _truncate(text),
            "unfurl_links": False,
        },
    )
    return data["ts"]
