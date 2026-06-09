# Contributing

Thanks for your interest in improving managed-agents-slack-logger!

## Development setup

```bash
git clone https://github.com/<you>/managed-agents-slack-logger
cd managed-agents-slack-logger
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your own keys
```

## Ground rules

- **Never commit secrets.** `.env` and `*.db` are gitignored; keep it that way.
- Keep modules small and dependency-light (stdlib + the few pins in
  `requirements.txt`). The point of this project is to be easy to read and host.
- Match the existing style: type hints, short docstrings explaining *why*, and
  graceful failure (a Slack/API hiccup should never crash a logging loop).

## Before opening a PR

- `python -m py_compile *.py` should pass.
- If you change event formatting, update the sample-event check in the README's
  "Verifying locally" section and confirm output still looks right.
- Describe the change and the motivation in the PR. Screenshots of the Slack
  output are welcome for formatting changes.

## Adding event types

Event formatting lives in `formatting.py`. Add an emoji to `_EMOJI` and a branch
in `format_event`. Unknown event types already fall back to a JSON dump, so the
logger never silently drops anything.

## Reporting issues

Open a GitHub issue with the Managed Agents beta version
(`managed-agents-2026-04-01` or newer), the event type involved, and a redacted
snippet of what was/wasn't posted. Don't paste API keys, tokens, or signing
secrets.
