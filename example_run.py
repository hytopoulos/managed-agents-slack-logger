"""End-to-end example: create a logged agent session and watch it appear in
your Slack channel as a thread, with each event as a reply.

Prereqs: pip install -r requirements.txt, and a filled-in .env (or exported
env vars). See README.md.
"""
from __future__ import annotations

import time

import anthropic

from agent_logger import create_logged_session

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY

# 1. Define an agent (or reuse an existing agent id).
agent = client.beta.agents.create(
    name="Demo Logged Agent",
    model={"id": "claude-opus-4-8"},
    system="You are a helpful coding assistant.",
    tool=[{"type": "agent_toolset_20260401"}],
)

# 2. Define an environment (or reuse an existing environment id).
env = client.beta.environments.create(
    name="demo-env",
    config={"type": "cloud", "networking": {"type": "unrestricted"}},
)

# 3. Create the session through the logger. This opens a Slack thread and
#    starts background logging of every event for this session.
session = create_logged_session(
    client,
    agent=agent.id,
    environment_id=env.id,
    title="demo session",
)
print("session:", session.id)

# 4. Kick off some work. Every event the agent emits is mirrored to Slack.
client.beta.sessions.events.send(
    session.id,
    events=[
        {
            "type": "user.message",
            "content": [
                {
                    "type": "text",
                    "text": "Create fibonacci.txt with the first 20 Fibonacci numbers, then read it back.",
                }
            ],
        }
    ],
)

# 5. Keep the process alive while the background logger streams to Slack.
#    In a real app this is just your normal program lifetime.
print("logging to Slack… (Ctrl-C to stop)")
try:
    while True:
        time.sleep(2)
except KeyboardInterrupt:
    pass
