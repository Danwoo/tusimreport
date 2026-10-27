# Security

## Credentials committed in early revisions

Early revisions of this repository contained two API keys as hardcoded
defaults: an OpenDART key in `data/dart_api_client.py` and a DeepSearch
key in `config/settings.py`. Both were removed from the code, and the git
history was rewritten on 2026-10-27 to remove the literal values from
every branch.

Treat both keys as compromised. Copies made before the rewrite (forks,
clones, cached views of old pull requests) can still contain them, and a
history rewrite cannot reach those copies. The owner is responsible for
revoking and reissuing them at the provider:

- OpenDART: <https://opendart.fss.or.kr/> → 인증키 관리
- DeepSearch: the account that issued the key

All keys are now read only from the environment or a local `.env` file,
which is listed in `.gitignore`. CI runs gitleaks on every push and pull
request to `main`.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting (Security tab → Report a
vulnerability). If that option is not available, open an issue asking
for a private contact, without including any details of the problem or
any credential you found.
