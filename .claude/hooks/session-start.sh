#!/bin/bash
# Claude Code 클라우드 세션 시작 시 CI·Dockerfile과 같은 의존성(requirements.txt)을 .venv에 설치한다.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}"

PYTHON_VERSION="3.12"

if command -v uv >/dev/null 2>&1; then
  [ -x .venv/bin/python ] || uv venv .venv --python "$PYTHON_VERSION"
  uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt
else
  [ -x .venv/bin/python ] || "python${PYTHON_VERSION}" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt
fi

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export VIRTUAL_ENV=\"$PWD/.venv\""
    echo "export PATH=\"$PWD/.venv/bin:\$PATH\""
  } >> "$CLAUDE_ENV_FILE"
fi
