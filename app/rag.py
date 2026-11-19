"""Retrieval for RAG: turn a user question into a context block built from the DB.

Strategy (hybrid):
1. Entity match   - find phone names mentioned in the question (handles "S23" vs "S23 Ultra").
2. Leaderboards   - for "best/most/cheapest..." questions, rank the whole catalogue.
3. TF-IDF         - if no phone is named, retrieve the closest phone documents by text.
"""
import re
from dataclasses import dataclass, field

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Phone

SUPERLATIVE_RE = re.compile(
    r"\b(best|most|highest|largest|biggest|longest|cheapest|cheaper|lowest|top|which|rank|"
    r"affordable|expensive|better|worst)\b",
    re.I,
)
MAX_VALUE_CHARS = 220
MAX_PHONES_IN_CONTEXT = 3


@dataclass
class RetrievalResult:
    context: str
    phones: list[str] = field(default_factory=list)  # phones whose full specs are in context


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+ ]", " ", text.lower())).strip()


def load_phones(session: Session) -> list[Phone]:
    stmt = select(Phone).options(selectinload(Phone.specs), selectinload(Phone.prices))
    return list(session.scalars(stmt).all())


def _aliases(phone: Phone) -> list[str]:
    short = norm(phone.name).removeprefix("samsung ").strip()
    aliases = {short}
    if short.startswith("galaxy "):
        aliases.add(short.removeprefix("galaxy "))  # "s23", "z fold5"
    return sorted(aliases)


def find_mentioned(query: str, phones: list[Phone]) -> list[Phone]:
    """Phones named in the query. 'S23 vs S23 Ultra' returns both; 'S23 Ultra' only Ultra."""
    q = norm(query)
    spans = []  # (start, end, phone)
    for phone in phones:
        for alias in _aliases(phone):
            for m in re.finditer(rf"(?<![a-z0-9+]){re.escape(alias)}(?![a-z0-9+])", q):
                spans.append((m.start(), m.end(), phone))
    keep = []
    for s, e, p in spans:
        covered = any(
            (s2 <= s and e <= e2 and (e2 - s2) > (e - s)) for s2, e2, _ in spans
        )
        if not covered and p not in keep:
            keep.append(p)
    return keep


def format_phone(phone: Phone) -> str:
    lines = [f"## {phone.name}"]
    by_cat: dict[str, list[str]] = {}
    for s in phone.specs:
        by_cat.setdefault(s.category, []).append(f"{s.key}: {s.value[:MAX_VALUE_CHARS]}")
    for cat, rows in by_cat.items():
        lines.append(f"[{cat}] " + " | ".join(rows))
    return "\n".join(lines)


def _phone_text(phone: Phone) -> str:
    return phone.name + " " + " ".join(f"{s.key} {s.value}" for s in phone.specs)


def leaderboards(phones: list[Phone]) -> str:
    def price(p: Phone):
        return p.prices[0].amount if p.prices else None

    def board(title, key, reverse, fmt):
        ranked = sorted((p for p in phones if key(p) is not None), key=key, reverse=reverse)
        if not ranked:
            return ""
        return f"{title}: " + "; ".join(f"{i}. {p.name} ({fmt(key(p))})" for i, p in enumerate(ranked, 1))

    parts = [
        board("Battery capacity ranking", lambda p: p.battery_mah, True, lambda v: f"{v} mAh"),
        board("Display size ranking", lambda p: p.display_inches, True, lambda v: f'{v}"'),
        board("RAM ranking (max variant)", lambda p: p.ram_gb, True, lambda v: f"{v} GB"),
        board("Launch price ranking (cheapest first)", price, False, lambda v: f"${v:,.0f}"),
    ]
    return "## Catalogue rankings\n" + "\n".join(x for x in parts if x)


def retrieve(query: str, session: Session) -> RetrievalResult:
    phones = load_phones(session)
    if not phones:
        return RetrievalResult(context="(The database is empty. No phone data available.)")

    mentioned = find_mentioned(query, phones)[:MAX_PHONES_IN_CONTEXT]
    blocks = [format_phone(p) for p in mentioned]
    names = [p.name for p in mentioned]

    if SUPERLATIVE_RE.search(query) or not mentioned:
        blocks.append(leaderboards(phones))

    if not mentioned:  # semantic fallback
        docs = [_phone_text(p) for p in phones]
        vec = TfidfVectorizer(stop_words="english").fit(docs + [query])
        sims = cosine_similarity(vec.transform([query]), vec.transform(docs))[0]
        for idx in sims.argsort()[::-1][:2]:
            if sims[idx] > 0:
                blocks.append(format_phone(phones[idx]))
                names.append(phones[idx].name)

    return RetrievalResult(context="\n\n".join(blocks), phones=names)


def get_phone(session: Session, name: str) -> Phone | None:
    """Best single phone for a free-text name (exact name match preferred)."""
    phones = load_phones(session)
    hits = find_mentioned(name, phones)
    return hits[0] if hits else None
