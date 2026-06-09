"""Central configuration, loaded from environment variables.

Copy .env.example to .env and fill it in, or export these in your shell.
"""
from __future__ import annotations

import os
from pathlib import Path

# Load a local .env if python-dotenv is installed (optional convenience).
try:  # pragma: no cover - convenience only
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: BLE001
    pass


# --- Anthropic / Managed Agents -------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Beta header required by the Managed Agents API. The SDK sets this
# automatically, but we keep it here for the raw-HTTP paths (webhook backfill).
MANAGED_AGENTS_BETA = os.environ.get("MANAGED_AGENTS_BETA", "managed-agents-2026-04-01")

# Signing secret for inbound webhooks (whsec_...). Only needed for the
# webhook_server. The Anthropic SDK reads this from ANTHROPIC_WEBHOOK_SIGNING_KEY.
WEBHOOK_SIGNING_KEY = os.environ.get("ANTHROPIC_WEBHOOK_SIGNING_KEY", "")


# --- Slack -----------------------------------------------------------------
# Bot token (xoxb-...). The bot must be invited to the target channel.
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")

# Channel to log into. Accepts a name ("agent-sessions" or "#agent-sessions")
# or a channel ID ("C0123ABCD").
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "agent-sessions")


# --- Logger behavior -------------------------------------------------------
# Which event type strings get posted as thread replies. "*" means everything.
# Override with a comma-separated list, e.g. "agent.message,agent.tool_use".
_raw_filter = os.environ.get("LOGGER_EVENT_FILTER", "*").strip()
EVENT_FILTER: set[str] | None = (
    None if _raw_filter in ("", "*") else {t.strip() for t in _raw_filter.split(",")}
)

# Max characters posted per Slack message (Slack hard limit is ~40k; we keep
# replies readable). Longer content is truncated with an ellipsis marker.
MAX_TEXT = int(os.environ.get("LOGGER_MAX_TEXT", "2800"))

# SQLite file mapping session_id -> slack thread + already-posted event ids.
# When hosting, point this at a mounted volume, e.g. /data/state.db.
STATE_DB = os.environ.get(
    "LOGGER_STATE_DB", str(Path(__file__).resolve().parent / "state.db")
)


def require(*names: str) -> None:
    """Raise a clear error if any required env var is missing."""
    missing = [n for n in names if not globals().get(n)]
    if missing:
        raise RuntimeError(
            "Missing required configuration: "
            + ", ".join(missing)
            + ". Set them in your environment or .env file."
        )
