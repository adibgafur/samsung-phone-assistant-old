"""Step 2 - RAG chatbot: retrieve from the DB, then let Groq answer from that context only."""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.llm import GroqLLM
from app.rag import retrieve

SYSTEM_PROMPT = """You are a helpful Samsung smartphone expert.
Answer ONLY using the CONTEXT provided (specs scraped from GSMArena).
- If the context does not contain the answer, say you don't have that information.
- Never invent specs or prices. Quote numbers exactly as given.
- For comparisons, use a short side-by-side list and finish with a one-sentence takeaway.
- Be concise."""


@dataclass
class ChatResult:
    answer: str
    sources: list[str]


class Chatbot:
    def __init__(self, llm: GroqLLM | None = None):
        self.llm = llm or GroqLLM()

    def ask(
        self,
        question: str,
        session: Session,
        history: list[dict] | None = None,
        llm: GroqLLM | None = None,
    ) -> ChatResult:
        active_llm = llm or self.llm
        retrieved = retrieve(question, session)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages += (history or [])[-6:]  # short conversational memory
        messages.append(
            {"role": "user", "content": f"CONTEXT:\n{retrieved.context}\n\nQUESTION: {question}"}
        )
        answer = active_llm.chat(messages)
        return ChatResult(answer=answer, sources=retrieved.phones)
