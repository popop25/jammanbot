from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from .config import Settings


@dataclass(frozen=True)
class CodexResult:
    text: str
    raw_stdout: str
    raw_stderr: str


class CodexBridge:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run(self, prompt: str) -> CodexResult:
        cmd = [self.settings.codex_command, *self.settings.codex_args]
        completed = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=self.settings.codex_timeout_seconds,
            cwd=self.settings.codex_workdir,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            stdout = completed.stdout.strip()
            detail = stderr or stdout or f"exit code {completed.returncode}"
            raise RuntimeError(f"Codex run failed: {detail[-1200:]}")

        text = self._extract_final_text(completed.stdout)
        return CodexResult(
            text=text,
            raw_stdout=completed.stdout,
            raw_stderr=completed.stderr,
        )

    @staticmethod
    def _extract_final_text(stdout: str) -> str:
        agent_messages: list[str] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "item.completed":
                continue
            item = event.get("item") or {}
            if item.get("type") in {"agent_message", "message"}:
                text = item.get("text") or item.get("content")
                if isinstance(text, str) and text.strip():
                    agent_messages.append(text.strip())

        if agent_messages:
            return agent_messages[-1]

        fallback = stdout.strip()
        if fallback:
            return fallback
        return "요약 결과가 비어 있어요. 잠시 뒤 다시 불러주세요."

