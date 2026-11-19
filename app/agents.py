"""Step 3 - multi-agent pipeline.

    user request -> SpecRetrievalAgent (DB) -> ReviewWriterAgent (Groq) -> review

Each agent has one job and a typed input/output, and the pipeline passes the
first agent's output to the second. Framework-free on purpose (simple pipeline);
the same two roles map 1:1 onto CrewAI/AutoGen agents if you want to swap later.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.llm import GroqLLM
from app.rag import format_phone, get_phone, leaderboards, load_phones


@dataclass
class SpecReport:
    phone_name: str
    spec_sheet: str
    market_context: str  # how the phone ranks against the rest of the catalogue


class SpecRetrievalAgent:
    """Role: fetch the technical data for one phone from the database."""

    def run(self, phone_query: str, session: Session) -> SpecReport:
        phone = get_phone(session, phone_query)
        if phone is None:
            raise LookupError(f"No phone matching '{phone_query}' in the database")
        return SpecReport(
            phone_name=phone.name,
            spec_sheet=format_phone(phone),
            market_context=leaderboards(load_phones(session)),
        )


REVIEW_PROMPT = """You are a professional smartphone reviewer.
Write a detailed review of the {name} using ONLY the spec sheet and catalogue rankings below.
Do not invent benchmarks, prices or features not present in the data.

Structure (markdown):
## Overview
## Display
## Performance
## Camera
## Battery & Charging
## Pros
## Cons
## Verdict (who should buy it, in 2-3 sentences, mention how it ranks in the catalogue)

SPEC SHEET:
{spec_sheet}

CATALOGUE RANKINGS:
{market_context}"""


class ReviewWriterAgent:
    """Role: turn a spec report into a readable, opinionated product review."""

    def __init__(self, llm: GroqLLM):
        self.llm = llm

    def run(self, report: SpecReport) -> str:
        prompt = REVIEW_PROMPT.format(
            name=report.phone_name,
            spec_sheet=report.spec_sheet,
            market_context=report.market_context,
        )
        return self.llm.chat([{"role": "user", "content": prompt}], temperature=0.5, max_tokens=1400)


@dataclass
class ReviewResult:
    phone: str
    review: str
    steps: list[str]


class ReviewPipeline:
    def __init__(self, llm: GroqLLM | None = None):
        self.llm = llm or GroqLLM()
        self.spec_agent = SpecRetrievalAgent()
        self.writer_agent = ReviewWriterAgent(self.llm)

    def run(self, phone_query: str, session: Session, llm: GroqLLM | None = None) -> ReviewResult:
        report = self.spec_agent.run(phone_query, session)
        writer = ReviewWriterAgent(llm) if llm else self.writer_agent
        review = writer.run(report)
        return ReviewResult(
            phone=report.phone_name,
            review=review,
            steps=["SpecRetrievalAgent: fetched specs from DB", "ReviewWriterAgent: wrote review with Groq"],
        )
