# 잠만봇

잠만봇은 Slack 스레드에 쌓인 대화를 대신 읽고, "대충 무슨 얘기였는지" 자연스럽게 설명해주는 로컬 Codex 기반 Slack 봇입니다.

OpenAI API key를 쓰지 않습니다. 대신 봇이 돌아가는 로컬/WSL 환경에 로그인된 `codex` CLI를 호출합니다. 컴퓨터가 꺼지면 잠만봇도 쉽니다.

말투는 업무 비서보다 느긋한 채팅방 친구 쪽을 지향합니다.

## 목표

- 바빠서 못 본 Slack 스레드를 빠르게 따라잡기
- 링크나 긴 글을 Slack 안에서 바로 요약하기
- 업무 비서보다는 채팅방 맥락 통역사처럼 동작하기
- 기본 검색 범위는 현재 스레드로 제한하기

## 기능

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

그냥 `@잠만봇`처럼 부르기만 하면 요약하지 않고 짧게 반응합니다.

자동 링크 요약은 기본적으로 꺼져 있습니다. `.env`에서 `JAMMANBOT_AUTO_LINK_CHANNELS`에 채널 ID를 넣으면 해당 채널에서만 켤 수 있습니다.

링크 요약은 공개 레포 기준으로 안전하게 동작하도록, 기본적으로 localhost/사설망 주소를 열지 않습니다. 내부망 링크까지 직접 요약하고 싶을 때만 `.env`에서 `JAMMANBOT_ALLOW_PRIVATE_LINK_HOSTS=true`로 바꾸세요.

구내식당 메뉴는 현재 분당캠퍼스 `비원` 식당만 봅니다.
메뉴 사이트 인증서 체인이 WSL/Python에서 self-signed로 보이면, 잠만봇은 검증 HTTPS로 먼저 시도한 뒤 인증서 검증 실패일 때만 재시도합니다. `.env`에서 `JAMMANBOT_CAFETERIA_VERIFY_SSL=false`로 두면 처음부터 검증 없이 호출합니다.

## 구조

```text
Slack Socket Mode App
  -> jammanbot Python process
  -> SQLite message store
  -> local codex exec
  -> Slack thread reply
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
- public repo에는 토큰, Slack channel ID, 실제 대화 DB를 올리지 마세요.
- 링크 요약은 외부 URL을 로컬 컴퓨터에서 직접 엽니다. 믿을 수 없는 채널에서는 자동 링크 요약을 켜지 않는 편이 좋습니다.
- 이 봇은 로컬 Codex 세션을 사용하므로 개인 컴퓨터/개인 서버에서 돌리는 전제가 자연스럽습니다.
