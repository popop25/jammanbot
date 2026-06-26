#!/usr/bin/env bash
set -euo pipefail

ROOT="${JAMMANBOT_ROOT:-$(pwd)}"
PYTHON="${PYTHON:-$(command -v python3.12 || command -v python3)}"
cd "$ROOT"

if [ -x .venv/bin/python ] && .venv/bin/python -m pip --version >/dev/null 2>&1; then
  echo "Reusing existing .venv"
else
  "$PYTHON" -m venv --clear .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env. Fill SLACK_BOT_TOKEN and SLACK_APP_TOKEN before running."
fi

mkdir -p data logs
echo "Installed 잠만봇 at $ROOT"
