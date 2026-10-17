# Loom for AWS: no IdP configured => super-admin (CVE-2026-103956)

When neither an Amazon Cognito user pool nor an active external identity provider (IdP) was configured, Loom's `get_current_user` (`backend/app/dependencies/auth.py`) returned a fixed `local-dev` identity in `t-admin` / `g-admins-super` with every scope, for any request, with no credentials. That is also the state of a fresh deployment before IdP setup. Advisory [GHSA-vgmj-998f-r8mp](https://github.com/awslabs/loom/security/advisories/GHSA-vgmj-998f-r8mp), CVSS 10.0, published 2026-10-02.

The first fix (1.6.1, 2026-08-04) required `LOOM_ALLOW_UNAUTHENTICATED_LOCAL_DEV` plus a loopback `request.client`. uvicorn derives `request.client` from `X-Forwarded-For` when `FORWARDED_ALLOW_IPS` is widened past loopback, so with the opt-in left on and `FORWARDED_ALLOW_IPS='*'`, a remote `X-Forwarded-For: 127.0.0.1` passed. [1.8.1](https://github.com/awslabs/loom/releases/tag/v1.8.1) (2026-10-06) refuses the bypass for any request with forwarding headers and refuses to start with the opt-in in a deployed-looking environment.

| Releases | Status |
|---|---|
| < 1.6.1 (first tag 1.6.0, 2026-07-10) | vulnerable: every request is super-admin |
| 1.6.1 to < 1.8.1 | partial: spoofable if opt-in set + proxy trust widened |
| ≥ 1.8.1 (2026-10-06) | patched |

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python reproduce.py            # BEFORE
.venv/bin/python fix.py                  # AFTER: follow-up fix, scoped proxy trust, setup-token design
.venv/bin/python detect.py --source upstream/auth_v1.6.1.py
.venv/bin/python detect.py --env samples/task.env
.venv/bin/python detect.py --url https://YOUR-OWN-DEPLOYMENT   # read-only probe; only systems you operate
.venv/bin/python -m pytest -q            # 18 tests
```

## Files

- `loom_model.py`: Loom's decision logic per release (`auth_before`, `auth_loopback_fix`, `auth_header_fix`, `assert_bypass_not_deployed`) and the proposed `auth_bootstrap_token`, in a FastAPI app behind uvicorn's real `ProxyHeadersMiddleware`. In-process only, no AWS.
- `upstream/`: Loom's `auth.py` at v1.6.0, v1.6.1, v1.8.1 (Apache-2.0, AWS Labs), used by `detect.py` tests.
- `tests/test_guard_template.py`: copy into your own service: with no IdP, every route must refuse.
- `OUTPUTS.txt`: the outputs quoted in the article.

The reproduction uses the documentation address `203.0.113.9` and never contacts a real service.
