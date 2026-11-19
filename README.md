# Samsung Phone Query & Review System

Scrape GSMArena → store in PostgreSQL → RAG chatbot + multi-agent review writer (Groq LLM) → FastAPI.

```
GSMArena ──scraper──▶ JSON ──ingest──▶ PostgreSQL (phones / specifications / prices)
                                            │
                       ┌────────────────────┴───────────────────┐
                       ▼                                        ▼
               RAG Chatbot (/chat)                 Multi-agent pipeline (/review)
       retrieve specs + rankings → Groq        SpecRetrievalAgent → ReviewWriterAgent (Groq)
                       └────────────────┬───────────────────────┘
                                        ▼
                                  FastAPI (/docs)
```

## Project layout

| Path | Purpose |
|---|---|
| `scraper/gsmarena.py` | Step 1 – requests + BeautifulSoup scraper (search → phone page → all spec tables) |
| `app/models.py`, `app/db.py` | SQLAlchemy schema: `phones`, `specifications` (category/key/value), `prices` |
| `app/parsing.py`, `app/ingest.py` | Parse battery/display/RAM/price into numeric columns; idempotent upsert into DB |
| `app/rag.py` | Retrieval: phone-name matching + catalogue rankings + TF-IDF fallback |
| `app/chatbot.py`, `app/llm.py` | Step 2 – Groq-backed chatbot answering only from retrieved context |
| `app/agents.py` | Step 3 – `SpecRetrievalAgent` → `ReviewWriterAgent` pipeline |
| `app/main.py` | Step 4 – FastAPI endpoints |
| `data/sample_phones.json` | 12-phone offline sample (hand-entered, for demo/tests only – not scraped) |
| `tests/` | pytest suite (uses a fake LLM, no API key needed) |

## Setup (step by step)

```bash
# 1. Environment
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # then put your GROQ_API_KEY in .env

# 2. Database (PostgreSQL via Docker; or set DATABASE_URL=sqlite:///./phones.db and skip this)
docker compose up -d

# 3. Scrape 12 Samsung phones from GSMArena (~2-3 min; polite delays; run from your own network)
python -m scraper.gsmarena --out data/scraped_phones.json

# 4. Load into the database
python -m app.ingest data/scraped_phones.json
#    (no internet / blocked? use the sample: python -m app.ingest data/sample_phones.json)

# 5. Start the Web App & API
uvicorn app.main:app --reload
# Front-end UI: http://127.0.0.1:8000/
# Swagger Docs: http://127.0.0.1:8000/docs

# 6. Run tests
pytest -q
```

## Front-End & API Key Management

The project includes an interactive web interface at `http://127.0.0.1:8000/` featuring:
- **API Key Configuration in UI:** Enter your Groq API key directly in the front-end (via top-right `🔑 API Key` button or startup banner).
  - Tests connectivity against Groq before saving (`/api/verify-key`)
  - Stored securely in `localStorage`
  - Automatically sent with all Chat and Multi-Agent Review requests via `X-API-Key` headers
  - Seamless fallback to `.env` `GROQ_API_KEY` if configured
- **Conversational RAG Chatbot:** Ask questions about specs, camera, battery, and comparisons with one-click quick prompt chips and context source badges.
- **Multi-Agent Review System:** Visualizes `SpecRetrievalAgent` retrieving data and rankings, followed by `ReviewWriterAgent` composing structured markdown reviews.
- **Phone Catalog & Spec Inspector:** Browse, filter, search, and view complete category-by-category GSMArena spec sheets.

## API

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Web Front-End (Interactive UI) |
| GET | `/health` | Status + number of phones in DB |
| GET | `/phones` | Summary list of all phones |
| GET | `/phones/{name}` | Full specs, e.g. `/phones/S24 Ultra` |
| GET | `/api/key-status` | Check if server or client API key is ready |
| POST | `/api/verify-key` | Test Groq API key connectivity (`{"api_key": "gsk_..."}`) |
| POST | `/chat` | `{"question": "...", "session_id": "...", "api_key": "optional"}` → answer + source phones |
| POST | `/review` | `{"phone": "Galaxy S23 Ultra", "api_key": "optional"}` → agent-written review |

```bash
curl -X POST localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"question":"Which Samsung phone has the best battery life?"}'

curl -X POST localhost:8000/review -H 'Content-Type: application/json' \
  -d '{"phone":"Galaxy S23 Ultra"}'
```

## Design notes

- **RAG without a vector DB:** with ~12 phones, exact entity matching is more reliable than embeddings
  (it tells "S23" from "S23 Ultra"). "Best/cheapest/most" questions get precomputed catalogue rankings
  so the LLM never has to compare 12 spec sheets itself. TF-IDF covers questions that name no phone.
- **Grounding:** the system prompt restricts Groq to the retrieved context; unknown facts → "I don't have that".
- **Agents:** two single-purpose agents passed in sequence. Framework-free to keep it simple and debuggable;
  the roles map directly onto CrewAI/AutoGen agents.
- **Scraper etiquette:** delays between requests, back-off on HTTP 429. GSMArena blocks heavy scraping – if blocked, wait and retry.
- **Limitations:** chat history is in-memory (lost on restart); prices are GSMArena launch prices, not live.
