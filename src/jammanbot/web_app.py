from __future__ import annotations

from datetime import date
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import _bool_env
from .gemini_client import GeminiClient
from .lunchlog_agent import DEFAULT_ROULETTE, LunchLogAgent, cafeteria_options


WEB_DIR = Path(__file__).parent / "web"
STATIC_DIR = WEB_DIR / "static"


class ParseMealRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    menu: dict[str, Any] | None = None


class SummarizePatternRequest(BaseModel):
    records: list[dict[str, Any]] = Field(default_factory=list)


class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    records: list[dict[str, Any]] = Field(default_factory=list)


class RouletteRequest(BaseModel):
    candidates: list[dict[str, Any]] | None = None
    mood: str = ""
    records: list[dict[str, Any]] = Field(default_factory=list)


class AgentMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    profile: dict[str, Any] = Field(default_factory=dict)
    records: list[dict[str, Any]] = Field(default_factory=list)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


def create_app() -> FastAPI:
    load_dotenv()
    agent = LunchLogAgent(
        gemini=GeminiClient(),
        verify_ssl=_bool_env("JAMMANBOT_CAFETERIA_VERIFY_SSL", True),
    )
    app = FastAPI(title="잠만봇 LunchLog Agent")
    app.state.agent = agent

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "gemini": agent.gemini.enabled}

    @app.get("/api/cafeteria/options")
    def get_cafeteria_options() -> dict[str, Any]:
        return {"options": cafeteria_options()}

    @app.get("/api/cafeteria/menu")
    def get_menu(
        target_date: str | None = Query(None, alias="date"),
        meal: str = Query("LN"),
        campus: str = Query("BD"),
        cafeteria: str = Query("21"),
    ) -> dict[str, Any]:
        try:
            return agent.get_menu(
                target_date=target_date or date.today().isoformat(),
                meal_type=meal,
                campus=campus,
                cafeteria_seq=cafeteria,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"menu fetch failed: {exc}") from exc

    @app.post("/api/agent/parse-meal")
    def parse_meal(request: ParseMealRequest) -> dict[str, Any]:
        return agent.parse_meal(text=request.text, menu=request.menu)

    @app.post("/api/agent/summarize-pattern")
    def summarize_pattern(request: SummarizePatternRequest) -> dict[str, Any]:
        return agent.summarize_pattern(records=request.records)

    @app.post("/api/agent/chat")
    def chat(request: ChatRequest) -> dict[str, str]:
        return {"reply": agent.chat(text=request.text, records=request.records)}

    @app.post("/api/agent/message")
    def agent_message(request: AgentMessageRequest) -> dict[str, Any]:
        try:
            return agent.handle_message(
                text=request.text,
                profile=request.profile,
                records=request.records,
                messages=request.messages,
                context=request.context,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"agent message failed: {exc}") from exc

    @app.post("/api/recommend/roulette")
    def roulette(request: RouletteRequest) -> dict[str, Any]:
        return agent.roulette(candidates=request.candidates, mood=request.mood, records=request.records)

    @app.get("/api/recommend/defaults")
    def roulette_defaults() -> dict[str, Any]:
        return {"candidates": DEFAULT_ROULETTE}

    return app


app = create_app()


def main() -> None:
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("jammanbot.web_app:app", host="0.0.0.0", port=port)
