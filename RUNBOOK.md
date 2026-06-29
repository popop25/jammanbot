# 잠만봇 실행/종료 메모

잠만봇은 WSL에서 실행하는 것을 기준으로 합니다. 아래 명령은 레포 루트에서 실행하세요.

```bash
cd ~/projects/jammanbot
```

Windows 경로에 clone해둔 현재 작업본을 그대로 쓸 때는 예를 들어 이런 식입니다.

```bash
cd /mnt/c/Users/Administrator/Documents/Codex/2026-06-26/https-buffett-story-tistory-com-2306/jammanbot
```

## 처음 설치

```bash
PYTHON=python3.12 ./scripts/install-wsl.sh
cp .env.example .env
```

`.env`에 Slack 토큰을 채웁니다.

```bash
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
```

Codex CLI도 WSL 안에서 로그인되어 있어야 합니다.

```bash
codex login
./scripts/smoke-codex.sh
```

## 일반 실행

로그를 바로 보면서 실행하고 싶을 때 씁니다.

```bash
source .venv/bin/activate
python -m jammanbot
```

종료는 실행 중인 터미널에서 `Ctrl+C`입니다.

## tmux로 계속 실행

평소에는 이 방식이 편합니다.

```bash
./scripts/run-wsl-tmux.sh
```

로그/세션 보기:

```bash
tmux attach -t jammanbot
```

attach 상태에서 빠져나오되 봇은 계속 돌리기:

```text
Ctrl+B 누른 뒤 D
```

세션이 떠 있는지 확인:

```bash
tmux ls
```

## 종료

```bash
tmux kill-session -t jammanbot
```

## 재시작

```bash
tmux kill-session -t jammanbot
./scripts/run-wsl-tmux.sh
```

이미 세션이 없다는 메시지가 나와도 괜찮습니다. 그때는 바로 실행 명령만 다시 치면 됩니다.

## 변경 후 확인

```bash
source .venv/bin/activate
python -m unittest discover -s tests
python -m compileall -q src tests
```

Slack manifest는 `slack/app-manifest.yml`을 사용합니다. 앱 이름은 `잠만봇`, bot user display name은 Slack 저장 오류를 피하려고 `JammanBot`으로 둡니다.

## 구내식당 SSL 오류

`CERTIFICATE_VERIFY_FAILED` 또는 `self-signed certificate in certificate chain` 오류가 나면, WSL/Python이 메뉴 사이트 인증서 체인을 신뢰하지 못한 상황입니다. 기본 동작은 검증 HTTPS로 먼저 시도한 뒤 인증서 검증 실패일 때만 한 번 더 재시도합니다.

계속 실패하면 `.env`에 아래 값을 넣고 재시작하세요.

```bash
JAMMANBOT_CAFETERIA_VERIFY_SSL=false
```

적용하려면 tmux 세션을 재시작해야 합니다.
