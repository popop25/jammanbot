#!/usr/bin/env bash
set -euo pipefail

codex exec - --json --ephemeral --skip-git-repo-check <<'PROMPT'
한국어로 한 문장만 답해줘: 잠만봇 준비됐어?
PROMPT

