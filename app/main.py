"""Step 4 - FastAPI service.

Run:  uvicorn app.main:app --reload     then open http://127.0.0.1:8000/docs
"""
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import ReviewPipeline
from app.chatbot import Chatbot
from app.config import GROQ_API_KEY, GROQ_MODEL
from app.db import SessionLocal, init_db
from app.llm import GroqLLM, LLMError, get_available_models, verify_api_key
from app.models import Phone
from app.rag import get_phone, load_phones

llm = GroqLLM()
chatbot = Chatbot(llm)
pipeline = ReviewPipeline(llm)
histories: dict[str, list[dict]] = defaultdict(list)  # in-memory, per session_id

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Samsung Phone Query & Review API", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def get_session():
    with SessionLocal() as session:
        yield session


def resolve_llm(
    custom_key: str | None = None,
    header_key: str | None = None,
    base_url: str | None = None,
    header_url: str | None = None,
    model: str | None = None,
) -> GroqLLM | None:
    key = (custom_key or "").strip() or (header_key or "").strip()
    url = (base_url or "").strip() or (header_url or "").strip()
    if key or url or model:
        return GroqLLM(api_key=key or None, model=model, base_url=url or None)
    return None


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500, examples=["What are the camera specs of the Samsung Galaxy S23?"])
    session_id: str | None = Field(default=None, description="Reuse to keep conversation context")
    api_key: str | None = Field(default=None, description="Optional Groq / LLM API key from front-end")
    base_url: str | None = Field(default=None, description="Optional custom or localhost base URL (e.g. http://localhost:11434/v1)")
    model: str | None = Field(default=None, description="Optional model override")


class ChatResponse(BaseModel):
    answer: str
    sources: list[str]


class ReviewRequest(BaseModel):
    phone: str = Field(min_length=2, max_length=80, examples=["Galaxy S23 Ultra"])
    api_key: str | None = Field(default=None, description="Optional Groq / LLM API key from front-end")
    base_url: str | None = Field(default=None, description="Optional custom or localhost base URL")
    model: str | None = Field(default=None, description="Optional model override")


class ReviewResponse(BaseModel):
    phone: str
    review: str
    agent_steps: list[str]


class VerifyKeyRequest(BaseModel):
    api_key: str | None = Field(default=None, description="API key to test")
    base_url: str | None = Field(default=None, description="Custom or localhost URL to test")
    model: str | None = Field(default=None, description="Model to test")


@app.get("/", include_in_schema=False)
def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Frontend not found. Please place index.html in app/static."}


@app.get("/health")
def health(session: Session = Depends(get_session)):
    count = len(session.scalars(select(Phone.id)).all())
    return {"status": "ok", "phones_in_db": count}


@app.get("/api/key-status")
def key_status(
    x_api_key: str | None = Header(default=None),
    x_base_url: str | None = Header(default=None),
):
    has_header = bool(x_api_key and x_api_key.strip())
    has_local = bool(x_base_url and "localhost" in x_base_url)
    has_server = bool(GROQ_API_KEY and GROQ_API_KEY.strip())
    return {
        "has_server_key": has_server,
        "has_custom_key": has_header,
        "has_localhost_provider": has_local,
        "ready": has_header or has_server or has_local,
        "model": GROQ_MODEL,
    }


class ModelsRequest(BaseModel):
    api_key: str | None = None
    base_url: str | None = None


@app.post("/api/models")
def list_models_endpoint(req: ModelsRequest):
    return {"models": get_available_models(api_key=req.api_key, base_url=req.base_url)}


@app.post("/api/verify-key")
def verify_key_endpoint(req: VerifyKeyRequest):
    return verify_api_key(api_key=req.api_key, model=req.model, base_url=req.base_url)


@app.get("/phones")
def list_phones(session: Session = Depends(get_session)):
    return [
        {
            "name": p.name,
            "announced": p.announced,
            "display_inches": p.display_inches,
            "battery_mah": p.battery_mah,
            "ram_gb": p.ram_gb,
            "price": f"{p.prices[0].amount:g} {p.prices[0].currency}" if p.prices else None,
        }
        for p in load_phones(session)
    ]


@app.get("/phones/{name}")
def phone_specs(name: str, session: Session = Depends(get_session)):
    phone = get_phone(session, name)
    if phone is None:
        raise HTTPException(404, f"No phone matching '{name}'")
    specs: dict[str, dict[str, str]] = {}
    for s in phone.specs:
        specs.setdefault(s.category, {})[s.key] = s.value
    return {"name": phone.name, "specs": specs}


@app.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    session: Session = Depends(get_session),
    x_api_key: str | None = Header(default=None),
    x_base_url: str | None = Header(default=None),
):
    request_llm = resolve_llm(req.api_key, x_api_key, req.base_url, x_base_url, req.model)
    history = histories[req.session_id] if req.session_id else None
    try:
        result = chatbot.ask(req.question, session, history, llm=request_llm)
    except LLMError as exc:
        raise HTTPException(503, str(exc))
    if req.session_id:
        history += [
            {"role": "user", "content": req.question},
            {"role": "assistant", "content": result.answer},
        ]
        del history[:-12]
    return ChatResponse(answer=result.answer, sources=result.sources)


@app.post("/review", response_model=ReviewResponse)
def review(
    req: ReviewRequest,
    session: Session = Depends(get_session),
    x_api_key: str | None = Header(default=None),
    x_base_url: str | None = Header(default=None),
):
    request_llm = resolve_llm(req.api_key, x_api_key, req.base_url, x_base_url, req.model)
    try:
        result = pipeline.run(req.phone, session, llm=request_llm)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except LLMError as exc:
        raise HTTPException(503, str(exc))
    return ReviewResponse(phone=result.phone, review=result.review, agent_steps=result.steps)
