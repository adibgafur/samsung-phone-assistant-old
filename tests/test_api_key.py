"""Tests for front-end API Key options, verification, and LLM resolution."""
import pytest
from app import main
from app.llm import GroqLLM, verify_api_key


class EchoLLM:
    def __init__(self, api_key: str = "custom_test_key"):
        self.api_key = api_key

    def chat(self, messages, **kw):
        return f"Echo from key={self.api_key}: " + messages[-1]["content"]


def test_resolve_llm_custom_key():
    # Provided explicitly in request
    llm1 = main.resolve_llm(custom_key="my_custom_groq_key")
    assert llm1 is not None
    assert llm1.api_key == "my_custom_groq_key"

    # Provided in header
    llm2 = main.resolve_llm(header_key="header_groq_key")
    assert llm2 is not None
    assert llm2.api_key == "header_groq_key"

    # Fallback when none provided
    llm3 = main.resolve_llm(custom_key=None, header_key=None)
    assert llm3 is None


def test_key_status_endpoint():
    # When header key is supplied
    res1 = main.key_status(x_api_key="gsk_12345")
    assert res1["has_custom_key"] is True
    assert res1["ready"] is True

    # When no key is supplied and no server key
    res2 = main.key_status(x_api_key=None)
    assert res2["has_custom_key"] is False


def test_verify_api_key_empty():
    res = verify_api_key("")
    assert res["valid"] is False
    assert "empty" in res["error"]


def test_verify_api_key_invalid():
    res = verify_api_key("gsk_invalid_test_key_xyz")
    assert res["valid"] is False
    assert "error" in res


def test_chat_and_review_with_custom_llm(monkeypatch):
    from app.rag import RetrievalResult
    monkeypatch.setattr("app.chatbot.retrieve", lambda q, s: RetrievalResult(context="Mock specs context", phones=["Samsung Galaxy S23"]))

    echo = EchoLLM("frontend_key_999")
    # Verify chatbot accepts custom llm
    res = main.chatbot.ask(
        "What are the camera specs of the Samsung Galaxy S23?",
        session=None,
        history=[],
        llm=echo,
    )
    assert "Echo from key=frontend_key_999" in res.answer
    assert "Samsung Galaxy S23" in res.sources
