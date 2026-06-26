#!/usr/bin/env bash
set -euo pipefail

ROOT="${JAMMANBOT_ROOT:-$(pwd)}"
cd "$ROOT"

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env. Fill SLACK_BOT_TOKEN and SLACK_APP_TOKEN before running."
fi

mkdir -p data logs
echo "Installed 잠만봇 at $ROOT"

