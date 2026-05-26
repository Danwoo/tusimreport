# Security Notes

## Past credential exposure in git history

An earlier version of `data/dart_api_client.py` contained a DART OpenAPI
key as a hardcoded fallback default. The current `main` branch (commit
`48cafe6` onward) removes it, but **the literal key value is still
recoverable from the git history**.

If that key was ever a real key (not a throwaway sample),
treat it as compromised and rotate it:

1. Sign in to <https://opendart.fss.or.kr/> with the account that issued the key.
2. Revoke the existing key.
3. Issue a new key and put it in `.env` under `DART_API_KEY`.
4. Confirm the app starts and `agents/korean_financial_react_agent.py`
   can fetch a corp_code.

The OpenDART key has no billing impact, but it is rate-limited per key and
abuse from a leaked key counts against your quota.

History rewriting (e.g. `git filter-repo`) was *not* performed because the
repo has external clones / forks where rewriting would create divergent
history that other contributors would silently miss. The rotate-the-key
approach is the standard mitigation for already-public credentials.

## Reporting

If you find another exposed credential or a security issue in the running
service, please open a private security advisory on GitHub rather than a
public issue.
