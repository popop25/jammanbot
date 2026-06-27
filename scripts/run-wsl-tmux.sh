#!/usr/bin/env bash
set -euo pipefail

SESSION="${JAMMANBOT_TMUX_SESSION:-jammanbot}"
ROOT="${JAMMANBOT_ROOT:-$(pwd)}"

cd "$ROOT"

if [ ! -d .venv ]; then
  ./scripts/install-wsl.sh
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env. Fill SLACK_BOT_TOKEN and SLACK_APP_TOKEN, then rerun."
  exit 1
fi

mkdir -p data logs

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "tmux session '$SESSION' already exists."
  echo "Attach with: tmux attach -t $SESSION"
  exit 0
fi

tmux new-session -d -s "$SESSION" \
  "cd '$ROOT' && source .venv/bin/activate && python -m jammanbot 2>&1 | tee -a logs/jammanbot.log"

echo "Started 잠만봇 in tmux session '$SESSION'."
echo "Attach with: tmux attach -t $SESSION"
