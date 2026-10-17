"""Am I affected? Two checks, standard library only.

    python detect.py                              # check installed pydantic-ai packages
    python detect.py --probe http://127.0.0.1:7932  # probe a local server you are running

The probe sends two harmless requests to YOUR OWN local server and never starts an
agent run: a GET with a foreign Host header, and a POST whose body is not a valid chat
request, sent as text/plain. A fixed server answers 421 and 415. Any other answer means
that server will accept the matching request from a web page. The Host probe works on
any local HTTP server, not only Pydantic AI.
"""

from __future__ import annotations

import http.client
import re
import sys
from importlib.metadata import PackageNotFoundError, version
from urllib.parse import urlsplit

PACKAGES = ('pydantic-ai', 'pydantic-ai-slim')
# (first affected, first fixed) per line: content-type advisory, Host advisory
CSRF = [((1, 34, 0), (1, 107, 4)), ((2, 0, 0), (2, 28, 0))]
REBIND = [((1, 34, 0), (1, 107, 5)), ((2, 0, 0), (2, 30, 0))]


def _parse(v: str) -> tuple[int, int, int]:
    nums = [int(n) for n in re.findall(r'\d+', v)[:3]]
    return tuple(nums + [0] * (3 - len(nums)))  # 2.0.0b1 parses as (2, 0, 0)


def _in(v, ranges) -> bool:
    return any(lo <= v < hi for lo, hi in ranges)


def check_installed() -> list[str]:
    findings = []
    for pkg in PACKAGES:
        try:
            raw = version(pkg)
        except PackageNotFoundError:
            continue
        v = _parse(raw)
        holes = [name for name, rng in (('web pages can POST to it', CSRF), ('DNS rebinding', REBIND)) if _in(v, rng)]
        findings.append(f'{pkg} {raw}: ' + ('AFFECTED (' + ', '.join(holes) + ')' if holes else 'not affected'))
    return findings or ['pydantic-ai is not installed in this environment']


def probe(url: str) -> list[str]:
    u = urlsplit(url)
    def send(method, path, headers, body=None):
        c = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=5)
        c.request(method, path, body=body, headers=headers)
        status = c.getresponse().status
        c.close()
        return status

    host = send('GET', '/', {'Host': f'rebind-check.invalid:{u.port or 80}'})
    out = [f'foreign Host header -> HTTP {host}: ' +
           ('ok, refused' if host in (400, 403, 421) else 'EXPOSED to DNS rebinding')]
    ctype = send('POST', '/api/chat', {'Host': u.netloc, 'Content-Type': 'text/plain'}, body=b'{}')
    verdict = {415: 'ok, refused', 404: 'no /api/chat endpoint here'}.get(
        ctype, 'EXPOSED: parsed a text/plain body, so any web page can POST to it')
    out.append(f'text/plain POST /api/chat -> HTTP {ctype}: {verdict}')
    return out


if __name__ == '__main__':
    if '--probe' in sys.argv:
        lines = probe(sys.argv[sys.argv.index('--probe') + 1])
    else:
        lines = check_installed()
    print('\n'.join(lines))
