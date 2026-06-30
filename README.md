# 잠만봇

잠만봇은 구내식당 메뉴 확인, 식사 기록, 음식 메뉴 추천을 돕는 LunchLog Agent입니다. 기존 Slack 요약/링크 요약 기능은 legacy 기능으로 남아 있습니다.

웹앱은 Gemini API key를 서버 환경변수로 받아 동작합니다. 브라우저에는 API key를 노출하지 않습니다. 기록은 로그인 없이 브라우저 `localStorage`에 저장합니다.

말투는 업무 비서보다 느긋한 채팅방 친구 쪽을 지향합니다.

## 목표

- 매일 점심 메뉴 확인 시간을 줄이기
- 먹은 메뉴와 만족도를 빠르게 기록하기
- 최근 식사 패턴을 가볍게 요약하기
- 메뉴가 애매할 때 음식 룰렛으로 선택 부담 줄이기

## 기능

- 웹앱에서 오늘 구내식당 메뉴 보기
- 메뉴 카드에서 먹은 메뉴와 만족도 기록
- 자연어로 식사 기록 입력
- 이번 주 식사 패턴 요약
- 음식 메뉴 룰렛
- legacy Slack 기능:
- `@잠만봇 뭐 얘기했어?`
- `@잠만봇 요약`
- `@잠만봇 못 본 거 요약`
- `@잠만봇 최근 30분만`
- `@잠만봇 1시간 전부터`
- `@잠만봇 오늘 얘기만`
- `@잠만봇 오늘 점심 뭐야?`
- `@잠만봇 어제 점심 메뉴`
- `@잠만봇 26일 점심 메뉴 뭐였어?`
- `@잠만봇 다음주월요일 점심 메뉴 뭐야?`
- `@잠만봇 한줄로`
- `@잠만봇 자세히`
- `@잠만봇 링크 요약 https://example.com/...`
- 링크가 있는 스레드에서 `@잠만봇 이거 요약`
- DM에서 `요약`, `뭐 얘기했어?`, `링크 요약 https://example.com/...`
- `@잠만봇 도움말` 또는 DM에서 `도움말`
- `@잠만봇 오늘 좀 피곤하다` 같은 짧은 잡담

그냥 `@잠만봇`처럼 부르기만 하면 요약하지 않고 짧게 반응합니다.
기능 요청이 아닌 짧은 말은 로컬 Codex로 가볍게 답합니다. 끄고 싶으면 `.env`에서 `JAMMANBOT_ENABLE_CASUAL_CHAT=false`로 두세요.

자동 링크 요약은 기본적으로 꺼져 있습니다. `.env`에서 `JAMMANBOT_AUTO_LINK_CHANNELS`에 채널 ID를 넣으면 해당 채널에서만 켤 수 있습니다.

링크 요약은 공개 레포 기준으로 안전하게 동작하도록, 기본적으로 localhost/사설망 주소를 열지 않습니다. 내부망 링크까지 직접 요약하고 싶을 때만 `.env`에서 `JAMMANBOT_ALLOW_PRIVATE_LINK_HOSTS=true`로 바꾸세요.

구내식당 메뉴는 현재 분당캠퍼스 `비원` 식당만 봅니다.
메뉴 사이트 인증서 체인이 WSL/Python에서 self-signed로 보이면, 잠만봇은 검증 HTTPS로 먼저 시도한 뒤 인증서 검증 실패일 때만 재시도합니다. `.env`에서 `JAMMANBOT_CAFETERIA_VERIFY_SSL=false`로 두면 처음부터 검증 없이 호출합니다.
평일 점심 메뉴를 자동으로 받고 싶으면 `.env`의 `JAMMANBOT_LUNCH_NOTIFY_CHANNELS`에 Slack 채널 ID를 넣으세요. 기본 발송 시각은 `11:10`이고, 메뉴 이미지 파일명이 늦게 올라오는 경우를 대비해 몇 분간 재시도합니다.

## 구조

```text
LunchLog Agent Core
  -> FastAPI web app
  -> localStorage meal records
  -> Gemini API proxy
  -> Slack adapter
```

메시지는 `workspace/team + channel + thread_ts` 단위로 저장됩니다. MVP에서는 다른 스레드 내용을 답변 컨텍스트에 넣지 않습니다.

## WSL 준비

WSL Ubuntu에서 다음 도구가 필요합니다.

- Python 3.12
- `tmux`
- `codex` CLI
- Slack app token과 bot token

Codex 로그인은 WSL 안에서 미리 해두세요.

```bash
codex login
codex exec --ephemeral "안녕. 한 문장으로 답해줘."
```

## 설치

```bash
git clone https://github.com/popop25/jammanbot.git
cd jammanbot
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

`.env`에 Slack 토큰을 채웁니다.

```bash
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
```

Windows 파일시스템(`/mnt/c/...`) 위에서도 동작하지만, WSL에서 계속 돌릴 봇이라면 `~/projects/jammanbot`처럼 WSL 홈 아래에 clone해서 쓰는 편이 더 빠르고 안정적입니다.

## Slack app 만들기

`slack/app-manifest.yml`을 Slack app manifest로 사용하세요.

Slack이 bot user display name에 한글을 거부하는 경우가 있어서, manifest에서는 앱 이름은 `잠만봇`, bot user display name은 `JammanBot`으로 둡니다. Slack 화면의 앱 이름은 `잠만봇`으로 보이게 둘 수 있습니다.

필요한 설정:

- Socket Mode: on
- Event subscriptions: on
- Bot events:
  - `app_mention`
  - `message.channels`
  - `message.groups`
  - `message.im`
- OAuth scopes:
  - `app_mentions:read`
  - `channels:history`
  - `channels:read`
  - `chat:write`
  - `groups:history`
  - `groups:read`
  - `im:history`
  - `users:read`
- App-level token scope:
  - `connections:write`

봇을 원하는 채널에 초대하고 스레드에서 `@잠만봇 요약`이라고 멘션하면 됩니다.
DM에서는 멘션 없이 `요약`, `한줄로`, `링크 요약 https://...`처럼 바로 말하면 됩니다.

## 실행

일반 실행:

```bash
source .venv/bin/activate
python -m jammanbot
```

요청/응답 로그를 직접 보고 싶으면 위 방식으로 실행하는 게 제일 편합니다.

tmux로 계속 실행:

```bash
./scripts/run-wsl-tmux.sh
```

웹앱 실행:

```bash
source .venv/bin/activate
jammanbot-web
```

또는:

```bash
uvicorn jammanbot.web_app:app --host 0.0.0.0 --port 8000
```

브라우저에서 `http://localhost:8000`으로 접속합니다.

## Render 배포

Render는 GitHub 저장소를 연결하면 Python 웹 서버를 빌드하고 public URL로 띄워주는 배포 서비스입니다. 이 프로젝트는 `render.yaml`을 포함하고 있어서 Render에서 Web Service를 만들 때 아래 값으로 실행됩니다.

```text
build: pip install -e .
start: uvicorn jammanbot.web_app:app --host 0.0.0.0 --port $PORT
python: 3.12
```

배포 시 Render Dashboard의 Environment에 아래 값을 추가합니다.

```text
GEMINI_API_KEY=구글에서 발급받은 키
GEMINI_MODEL=gemini-1.5-flash
JAMMANBOT_CAFETERIA_VERIFY_SSL=true
```

Render Free 인스턴스는 일정 시간 요청이 없으면 잠들 수 있습니다. 과제 제출 URL로는 충분하지만, 첫 접속이 몇십 초 느릴 수 있습니다.

WSL의 기본 `python3`가 다른 버전을 가리키면 설치 시 이렇게 지정할 수 있습니다.

```bash
PYTHON=python3.12 ./scripts/install-wsl.sh
```

로그 보기:

```bash
tmux attach -t jammanbot
```

중지:

```bash
tmux kill-session -t jammanbot
```

## 보안 메모

- `.env`와 `~/.codex/auth.json`은 절대 커밋하지 마세요.
- `GEMINI_API_KEY`는 서버 환경변수로만 넣고, HTML/JS에 직접 넣지 마세요.
- public repo에는 토큰, Slack channel ID, 실제 대화 DB를 올리지 마세요.
- 링크 요약은 외부 URL을 로컬 컴퓨터에서 직접 엽니다. 믿을 수 없는 채널에서는 자동 링크 요약을 켜지 않는 편이 좋습니다.
- Slack legacy 봇은 로컬 Codex 세션을 사용할 수 있지만, 웹앱 LunchLog Agent는 Gemini API key 기반으로 동작합니다.
