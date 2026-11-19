import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import parsing
from app.agents import ReviewPipeline
from app.chatbot import Chatbot
from app.db import Base
from app.ingest import upsert_phone
from app.rag import find_mentioned, load_phones, retrieve

SAMPLE = Path(__file__).parent.parent / "data" / "sample_phones.json"


class FakeLLM:
    """Echoes the prompt so tests can assert on what the model was given."""

    def chat(self, messages, **kw):
        return messages[-1]["content"]


@pytest.fixture()
def Session():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    from app import models  # noqa: F401

    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    with maker() as s:
        for rec in json.loads(SAMPLE.read_text()):
            upsert_phone(s, rec)
        s.commit()
    return maker


def test_parsing():
    specs = {
        "Battery": {"Type": "Li-Ion 3900 mAh, non-removable"},
        "Display": {"Size": "6.1 inches, 90.1 cm2"},
        "Memory": {"Internal": "128GB 8GB RAM, 512GB 12GB RAM"},
        "Misc": {"Price": "$ 799.99 / € 699.00"},
    }
    assert parsing.battery_mah(specs) == 3900
    assert parsing.display_inches(specs) == 6.1
    assert parsing.ram_gb(specs) == 12
    assert parsing.price(specs)[:2] == (799.99, "USD")


def test_ingest_is_idempotent(Session):
    with Session() as s:
        for rec in json.loads(SAMPLE.read_text()):
            upsert_phone(s, rec)
        s.commit()
        assert len(load_phones(s)) == 12


def test_entity_matching_distinguishes_variants(Session):
    with Session() as s:
        phones = load_phones(s)
        assert [p.name for p in find_mentioned("camera of the Galaxy S23?", phones)] == ["Samsung Galaxy S23"]
        assert [p.name for p in find_mentioned("S23 Ultra battery", phones)] == ["Samsung Galaxy S23 Ultra"]
        both = {p.name for p in find_mentioned("S23 vs S23 Ultra", phones)}
        assert both == {"Samsung Galaxy S23", "Samsung Galaxy S23 Ultra"}


def test_retrieval_includes_specs_and_rankings(Session):
    with Session() as s:
        r = retrieve("How does the Galaxy S23 compare to the S22 in performance?", s)
        assert set(r.phones) == {"Samsung Galaxy S23", "Samsung Galaxy S22"}
        assert "Snapdragon 8 Gen 2" in r.context
        r = retrieve("Which Samsung phone has the best battery life?", s)
        assert "Battery capacity ranking" in r.context


def test_chatbot_passes_context_to_llm(Session):
    with Session() as s:
        res = Chatbot(FakeLLM()).ask("What is the screen size of the Galaxy S22?", s)
        assert "6.1 inches" in res.answer and res.sources == ["Samsung Galaxy S22"]


def test_review_pipeline(Session):
    with Session() as s:
        out = ReviewPipeline(FakeLLM()).run("Galaxy Z Flip5", s)
        assert out.phone == "Samsung Galaxy Z Flip5" and "SPEC SHEET" in out.review
        with pytest.raises(LookupError):
            ReviewPipeline(FakeLLM()).run("Nokia 3310", s)


def test_api(Session, monkeypatch):
    from app import main

    def override():
        with Session() as s:
            yield s

    main.app.dependency_overrides[main.get_session] = override
    monkeypatch.setattr(main.chatbot, "llm", FakeLLM())
    monkeypatch.setattr(main.pipeline.writer_agent, "llm", FakeLLM())
    c = TestClient(main.app)
    assert c.get("/health").json()["phones_in_db"] == 12
    assert len(c.get("/phones").json()) == 12
    assert c.get("/phones/S24 Ultra").json()["name"] == "Samsung Galaxy S24 Ultra"
    assert c.get("/phones/iPhone").status_code == 404
    assert c.post("/chat", json={"question": "camera specs of the S23?"}).status_code == 200
    assert c.post("/chat", json={"question": "hi"}).status_code == 422
    assert c.post("/review", json={"phone": "S23 Ultra"}).json()["phone"] == "Samsung Galaxy S23 Ultra"
    assert c.post("/review", json={"phone": "Pixel 9"}).status_code == 404
    main.app.dependency_overrides.clear()
