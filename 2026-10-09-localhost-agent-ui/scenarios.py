"""Shared harness: serve a real Pydantic AI agent through `Agent.to_web()` and send it
the three requests a browser could send to `http://127.0.0.1:7932`.

No browser and no network are involved. Starlette's in-process `TestClient` sends each
request straight to the ASGI app with exactly the headers a browser would be *allowed*
to send in that situation (see the docstring of each scenario). The model is Pydantic
AI's offline `TestModel`, which calls every registered tool, so no API key is needed.

Functions, in article order:
    build_agent()       a dev agent with one side-effecting tool (writes a file)
    build_app()         the Starlette app from `agent.to_web()`, optionally wrapped
    run_scenarios()     sends the three requests, reports whether the tool ran
    print_report()      prints the table used in the article
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Callable

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from starlette.testclient import TestClient

LOCAL_URL = 'http://127.0.0.1:7932'
REBIND_URL = 'http://attacker.example:7932'  # a name the attacker re-points at 127.0.0.1

CHAT_BODY = json.dumps(
    {
        'trigger': 'submit-message',
        'id': 'chat-1',
        'messages': [{'id': 'm1', 'role': 'user', 'parts': [{'type': 'text', 'text': 'tidy my notes'}]}],
    }
)


@dataclass
class Scenario:
    name: str
    who: str
    base_url: str
    headers: dict[str, str]


SCENARIOS = [
    Scenario(
        # The bundled chat UI, served from the same origin, sends JSON.
        name='A. your own chat tab',
        who='same origin, Content-Type: application/json',
        base_url=LOCAL_URL,
        headers={'content-type': 'application/json'},
    ),
    Scenario(
        # Any web page can POST text/plain cross-origin with NO preflight: it is a
        # CORS "simple request". The page cannot read the reply, but it does not need to.
        name='B. any website (simple request)',
        who='cross-site, Content-Type: text/plain, no preflight',
        base_url=LOCAL_URL,
        headers={'content-type': 'text/plain', 'origin': 'https://attacker.example'},
    ),
    Scenario(
        # After DNS rebinding the browser thinks the page and the UI share an origin,
        # so it sends JSON freely. The one thing it cannot hide is the Host header.
        name='C. any website (DNS rebinding)',
        who='looks same-origin, Host: attacker.example:7932',
        base_url=REBIND_URL,
        headers={'content-type': 'application/json', 'origin': REBIND_URL},
    ),
]


def build_agent(notes_dir: Path) -> Agent:
    """A typical dev agent: one tool with a real side effect on the developer's disk."""
    agent = Agent(TestModel(), instructions='You manage my local notes.')

    @agent.tool_plain
    def write_note(text: str) -> str:
        """Write a note to the developer's notes folder."""
        path = notes_dir / f'note-{len(list(notes_dir.iterdir())) + 1}.txt'
        path.write_text(text)
        return f'wrote {path.name}'

    return agent


def build_app(agent: Agent, wrap: Callable | None = None):
    app = agent.to_web()
    return wrap(app) if wrap else app


def run_scenarios(wrap: Callable | None = None) -> list[dict]:
    results = []
    for s in SCENARIOS:
        with tempfile.TemporaryDirectory() as d:
            notes = Path(d)
            app = build_app(build_agent(notes), wrap)
            with TestClient(app, base_url=s.base_url) as client:
                r = client.post('/api/chat', content=CHAT_BODY, headers=s.headers)
            tool_ran = any(notes.iterdir())
            results.append({'scenario': s.name, 'who': s.who, 'status': r.status_code, 'tool_ran': tool_ran})
    return results


# Releases are named by publication date in the printed report, so the output can be
# quoted in the article without version numbers. The README maps dates to versions.
RELEASES = {
    '2.27.1': 'last release before the fixes, 11 Aug 2026',
    '2.28.0': 'content-type fix only, 12 Aug 2026',
    '2.30.0': 'both fixes, 14 Aug 2026',
}


def print_report(label: str, results: list[dict]) -> None:
    v = version('pydantic-ai-slim')
    print(f'{label}  ({RELEASES.get(v, "pydantic-ai-slim " + v)})')
    for r in results:
        verdict = 'TOOL RAN' if r['tool_ran'] else 'blocked '
        print(f"  {r['scenario']:<34} HTTP {r['status']}  {verdict}")
