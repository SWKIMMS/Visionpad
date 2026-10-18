from pathlib import Path
import asyncio
from contextlib import asynccontextmanager
import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from game_engine import GameEngine
from game_speech import SpeechService, SpeechUnavailable
from speech_queue import SpeechQueue, SpeechQueueFull, SpeechSuperseded


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "game_config.json"
WEB_DIR = BASE_DIR / "web"


with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)


engine = GameEngine(CONFIG)
speech = SpeechService(BASE_DIR)
speech_jobs = SpeechQueue(speech)


@asynccontextmanager
async def lifespan(app):
    yield
    await speech_jobs.close()


app = FastAPI(title="Dotdew Valley", lifespan=lifespan)

app.mount(
    "/static",
    StaticFiles(directory=str(WEB_DIR)),
    name="static"
)


class PointerRequest(BaseModel):
    x: float = Field(ge=0, lt=CONFIG["dotpad"]["width"], allow_inf_nan=False)
    y: float = Field(ge=0, lt=CONFIG["dotpad"]["height"], allow_inf_nan=False)


class CommandRequest(BaseModel):
    command: str


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1600)
    profile: str = Field(default="system", pattern="^(system|shopkeeper)$")
    rate: float = Field(default=1.0, ge=0.8, le=1.5, allow_inf_nan=False)
    priority: str = Field(default="action", pattern="^(hover|action|dialogue|background)$")
    client_id: str | None = Field(default=None, pattern="^[A-Za-z0-9-]{1,80}$")
    sequence: int = Field(default=0, ge=0, le=9007199254740991)


class SpeechCancelRequest(BaseModel):
    client_id: str = Field(pattern="^[A-Za-z0-9-]{1,80}$")
    sequence: int = Field(ge=1, le=9007199254740991)


@app.get("/api/speech/voices")
def speech_voices():
    return speech.catalogue()


@app.post("/api/speech")
async def synthesize_speech(req: SpeechRequest, request: Request):
    if bool(req.client_id) != bool(req.sequence):
        raise HTTPException(status_code=422, detail="client_id and positive sequence must be provided together")
    job = None
    try:
        job = speech_jobs.submit(req.text, req.profile, req.rate, req.priority, req.client_id, req.sequence)
        while not job.future.done():
            done, _ = await asyncio.wait({job.future}, timeout=0.1)
            if not done and await request.is_disconnected():
                speech_jobs.cancel(job)
                return Response(status_code=204)
        return job.future.result()
    except SpeechSuperseded:
        return Response(status_code=204)
    except SpeechQueueFull as error:
        raise HTTPException(status_code=429, detail=str(error)) from error
    except asyncio.CancelledError:
        if job:
            speech_jobs.cancel(job)
        raise
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except SpeechUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/api/speech/cancel", status_code=204)
async def cancel_speech(req: SpeechCancelRequest):
    speech_jobs.supersede(req.client_id, req.sequence)
    return Response(status_code=204)


@app.get("/api/speech/audio/{key}.wav")
def speech_audio(key: str):
    try:
        path = speech.audio_path(key)
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Speech audio not found") from error
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Speech audio not found")
    return FileResponse(path, media_type="audio/wav", headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/")
async def root():
    return FileResponse(str(WEB_DIR / "game.html"))


@app.get("/api/state")
async def get_state():
    return engine.get_state()


@app.post("/api/pointer/move")
async def pointer_move(req: PointerRequest):
    return engine.pointer_move(req.x, req.y)


@app.post("/api/pointer/down")
async def pointer_down(req: PointerRequest):
    return engine.pointer_down(req.x, req.y)


@app.post("/api/pointer/drag")
async def pointer_drag(req: PointerRequest):
    return engine.pointer_drag(req.x, req.y)


@app.post("/api/pointer/up")
async def pointer_up(req: PointerRequest):
    return engine.pointer_up(req.x, req.y)


@app.post("/api/command")
async def command(req: CommandRequest):
    return engine.handle_command(req.command)


@app.post("/api/reset")
async def reset():
    engine.reset()
    return {
        "tts": "New game. Home.",
        "state": engine.get_state()
    }


@app.post("/api/visual-tick")
async def visual_tick():
    return engine.visual_tick()
