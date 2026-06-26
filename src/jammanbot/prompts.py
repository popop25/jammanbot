from __future__ import annotations

from .db import StoredMessage


def _clean_text(text: str) -> str:
    return " ".join(text.replace("\n", " ").split())


def format_messages(messages: list[StoredMessage], max_chars: int = 18000) -> str:
    lines: list[str] = []
    total = 0
    for message in messages:
        if message.bot_id:
            continue
        text = _clean_text(message.text)
        if not text:
            continue
        user = f"<@{message.user_id}>" if message.user_id else "unknown"
        line = f"- {message.ts} {user}: {text}"
        total += len(line)
        lines.append(line)
        if total >= max_chars:
            break
    return "\n".join(lines)


def build_summary_prompt(
    messages: list[StoredMessage],
    *,
    mode: str,
    command_text: str,
    scope_label: str,
) -> str:
    formatted = format_messages(messages)
    if not formatted:
        formatted = "(읽을 수 있는 메시지가 없습니다.)"

    if mode == "one_line":
        mode_instruction = "한 문장으로만 답하세요. 너무 딱딱하지 않게 말하세요."
    elif mode == "detailed":
        mode_instruction = (
            "조금 자세히 풀어주세요. 흐름, 중간에 나온 쟁점, 현재 분위기를 구분하세요."
        )
    else:
        mode_instruction = (
            "짧게 요약하세요. 핵심 흐름 3~5개와 현재 분위기 정도면 충분합니다."
        )

    return f"""
너는 Slack 방에 상주하는 '잠만봇'이다.
역할은 바빠서 대화를 못 읽은 사람이 빨리 따라잡도록, 대화 흐름을 자연스럽게 설명하는 것이다.

중요한 규칙:
- 아래 제공된 Slack 메시지만 사용한다.
- 다른 스레드나 채널 내용을 알고 있는 척하지 않는다.
- 업무/잡담을 억지로 구분하지 말고, 실제 대화 분위기에 맞게 설명한다.
- 할 일, 담당자, 결정사항은 사용자가 명확히 요청하지 않았다면 과하게 뽑지 않는다.
- 답변은 한국어로 한다.
- 사용자의 직접 요청 메시지는 요약 대상 대화라기보다 명령으로 취급해도 된다.

요청:
{command_text}

범위:
{scope_label}

응답 방식:
{mode_instruction}

Slack 메시지:
{formatted}
""".strip()


def build_link_prompt(url: str, title: str, text: str, command_text: str) -> str:
    title_block = title or "(제목 없음)"
    body = text or "(본문을 거의 추출하지 못했습니다.)"
    return f"""
너는 Slack 방에 상주하는 '잠만봇'이다.
아래 링크 본문을 읽고, Slack 맥락과 억지로 연결하지 말고 링크 자체만 설명한다.

중요한 규칙:
- 본문에 없는 내용을 추측하지 않는다.
- 광고/메타 문구가 섞였으면 핵심 내용 위주로 정리한다.
- 너무 길게 쓰지 않는다.
- 한국어로 답한다.

사용자 요청:
{command_text}

URL:
{url}

제목:
{title_block}

본문:
{body[:18000]}

응답 형식:
대충 이런 글이에요.
- 핵심 1
- 핵심 2
- 핵심 3

필요하면 마지막에 "읽을 가치"를 한 줄로 덧붙인다.
""".strip()

