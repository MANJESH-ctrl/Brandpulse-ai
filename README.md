# BrandPulse AI

**AI-powered brand sentiment intelligence platform.** Give it a brand name, it scrapes Reddit, YouTube, and Hacker News, runs every post through an LLM sentiment pipeline, detects crises, and generates actionable intelligence reports — automatically, end to end.

Live at: `http://3.109.12.0:8000`

---

## What It Does

Type a brand name like `Cursor` or `Perplexity`. BrandPulse collects hundreds of real social media posts, analyzes each one with a large language model, and surfaces:

- **Sentiment breakdown** — positive, negative, neutral with engagement-weighted scoring (a viral post with 10k upvotes counts more than a low-engagement post)
- **Aspect analysis** — separates sentiment by category: product, pricing, service, leadership, ethics, performance
- **Sarcasm detection** — LLM explicitly flags posts like "Oh great, another outage!" as negative, not positive
- **Crisis alerts** — automatic notification when negative sentiment crosses 60%, with an acknowledge workflow
- **AI brand intelligence report** — LLM-generated summary with key themes, concerns, and recommendations
- **Multi-brand comparison** — run 2–5 brands side by side

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, async throughout |
| AI Pipeline | LangGraph (4-node agentic graph) |
| LLMs | Cerebras `qwen-3-235b` (primary) → Groq `llama-3.3-70b` (fallback) → statistical fallback |
| Data Collection | asyncpraw (Reddit), httpx + YouTube Data API v3, Algolia HN API |
| Database | SQLite + SQLAlchemy async (aiosqlite) |
| Frontend | Vanilla JS, Chart.js, IBM Plex Mono retro terminal theme |
| Containerization | Docker multi-stage build, Docker Compose |
| CI/CD | GitHub Actions — 5-job pipeline |
| Registry | AWS ECR |
| Hosting | AWS EC2 (Ubuntu 24, t2.micro) |
| Code Quality | Ruff (lint + format) |
| Testing | pytest + pytest-asyncio, 63 tests, zero external calls |

---

## Architecture

```
User → FastAPI → Background Task
                      ↓
           asyncio.gather() — parallel collection
           ├── RedditCollector    (asyncpraw)
           ├── YouTubeCollector   (httpx + Data API v3)
           └── HackerNewsCollector (Algolia, no keys needed)
                      ↓
              LangGraph Pipeline
              ├── node_process_text     — clean, deduplicate, engagement score
              ├── node_analyze_sentiment — LLM batch sentiment (Cerebras → Groq)
              ├── node_generate_insights — LLM brand intelligence report
              └── node_detect_crisis    — threshold detection + alert creation
                      ↓
                  SQLite (persisted via Docker named volume)
                      ↓
              FastAPI → Frontend polling → Results
```

---

## CI/CD Pipeline

Every `git push` to `main` triggers a 5-job GitHub Actions pipeline:

```
[lint]    ruff format + ruff check — code quality gate
   ↓
[test]    pytest 63 tests — zero external API calls, fully mocked
   ↓
[docker]  multi-stage build → SHA-tagged image → push to AWS ECR
   ↓
[deploy]  SSH to EC2 → pull exact SHA image → docker compose up
   ↓
[verify]  curl /health with 5-attempt retry — confirms app is live
```

PRs only run lint and test — never deploy. Deployment is gated behind a passing test suite. Each image is tagged with both the git SHA (`abc123f`) and `:latest` — every running container is traceable to an exact commit.

---

## LangGraph Pipeline — 4 Nodes

**Node 1 — process_text**
Cleans URLs, HTML, special characters. Deduplicates by fingerprint (first 100 chars). Computes platform-specific engagement scores:
- Reddit: `score × 0.01 + comments × 0.1` (capped at 10)
- YouTube: `views × 0.000001 + likes × 0.0001`
- HN: `points × 0.05 + comments × 0.05`

**Node 2 — analyze_sentiment**
Checks same-day in-memory cache first. If not cached, sends posts to Cerebras in batches of 12 (semaphore of 2 for rate limiting), with exponential backoff retry (3s, 6s, 12s) on 429s. Falls back to Groq if Cerebras fails, falls back to neutral if both fail. Each post gets: `sentiment`, `confidence`, `is_sarcastic`, `aspect`, `intensity`, `brand_relevance`, `reason`.

**Node 3 — generate_insights**
Builds a structured prompt with sentiment data, aspect breakdown, and top 5 negative posts. Calls Cerebras for a brand intelligence report (summary, key themes, concerns, recommendations). Falls back to Groq, then to a statistical summary if both fail.

**Node 4 — detect_crisis**
`crisis_score = negative_percentage / 0.60`. Score ≥ 1.0 triggers a `CrisisAlert` row and fires an alert. Score ≥ 0.67 flags as concern. Identifies the worst-performing aspect as the top concern.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/analyze` | Start analysis job (returns job_id immediately) |
| `GET` | `/api/status/{job_id}` | Poll job progress |
| `GET` | `/api/results/{job_id}` | Full analysis result |
| `GET` | `/api/posts/{job_id}` | Collected posts with sentiment annotations |
| `GET` | `/api/results/{job_id}/posts/sentiment` | Per-platform sentiment breakdown |
| `GET` | `/api/brands` | All analyzed brands with averages |
| `GET` | `/api/brands/{name}` | Analysis history for a brand |
| `GET` | `/api/brands/{name}/trend` | Sentiment trend over time |
| `POST` | `/api/brands/compare` | Compare 2–5 brands side by side |
| `GET` | `/api/alerts` | Crisis alerts (filterable) |
| `PATCH` | `/api/alerts/{id}/acknowledge` | Acknowledge a crisis alert |
| `GET` | `/health` | Health check |

---

## Database Schema

Four tables, async SQLAlchemy:

| Table | Purpose |
|---|---|
| `analysis_jobs` | Every run — id, brand, status, timestamps, error |
| `analysis_results` | Aggregated output — sentiment distribution, aspects, insights, crisis score |
| `collected_posts` | Individual posts with full annotation — sentiment, confidence, sarcasm, aspect, engagement, brand relevance |
| `crisis_alerts` | Fired when negative ≥ 60% — has acknowledge workflow |

---

## Testing

63 tests across 5 files. No external API calls — everything mocked.

```
tests/
├── conftest.py                  # in-memory SQLite, FastAPI test client, fake env vars
├── test_api.py                  # all 11 endpoints — contracts, 404s, 400s, seeds
├── test_collectors.py           # query building, post standardization, 3-tier fallback
├── test_nodes.py                # engagement math, deduplication, crisis thresholds
├── test_sentiment_analyzer.py   # distribution math, brand relevance filter, fallbacks
└── test_config.py               # missing key validation, default values
```

Tests run in CI with fake API keys — no secrets needed in the test job.

---

## Key Design Decisions

**Why LangGraph instead of sequential functions?**
The pipeline is a proper state graph — each node receives and returns the full `AnalysisState` TypedDict. This makes it trivially extensible: add a node, wire it in the graph, done. In a production scenario this could branch based on sentiment score, trigger different analysis paths, or integrate human-in-the-loop steps.

**Why dual LLM strategy?**
Cerebras is fast (sub-second inference on large models) but has rate limits. Groq is the fallback. If both fail, a statistical summary is generated so the pipeline always completes — never a hard failure in front of the user.

**Why engagement-weighted sentiment?**
A post with 15k upvotes saying a product is broken should weigh more than a post with 2 upvotes saying it's fine. Raw sentiment average is misleading. Engagement weighting surfaces what the community actually cares about.

**Why SQLite instead of Postgres?**
For a portfolio project running on a single t2.micro, SQLite with async access is the right call. The database is persisted via a Docker named volume — it survives container restarts and redeployments. The `DATABASE_URL` is environment-variable driven, so switching to Postgres in production is a one-line change.

**Why non-root Docker user?**
Running as root inside a container is a security red flag. The Dockerfile creates a dedicated `appuser` (uid 1001) and drops privileges before the app starts. This is standard practice in any production container setup.

---

## Running Locally

**Prerequisites:** Python 3.12, uv

```bash
# Clone and install
git clone https://github.com/MANJESH-ctrl/Brandpulse-ai.git
cd Brandpulse-ai

uv sync

# Set up environment
cp .env.example .env
# Fill in: GROQ_API_KEY, CEREBRAS_API_KEY, REDDIT_CLIENT_ID,
#          REDDIT_CLIENT_SECRET, YOUTUBE_API_KEY, DATABASE_URL

# Run
uv run uvicorn src.api.main:app --reload
```

Open `http://localhost:8000`

**Run with Docker:**

```bash
docker compose up --build
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | SQLite: `sqlite+aiosqlite:///./brandpulse.db` |
| `GROQ_API_KEY` | Yes | Groq API key — fallback LLM |
| `CEREBRAS_API_KEY` | No | Cerebras API key — primary LLM (faster) |
| `REDDIT_CLIENT_ID` | Yes | Reddit app client ID |
| `REDDIT_CLIENT_SECRET` | Yes | Reddit app client secret |
| `YOUTUBE_API_KEY` | Yes | YouTube Data API v3 key |

---

## Project Structure

```
brandpulse_ai/
├── src/
│   ├── api/
│   │   ├── main.py                 # FastAPI app, lifespan, CORS, routing
│   │   ├── schemas.py              # Pydantic request/response models
│   │   └── routers/
│   │       ├── analysis.py         # POST /api/analyze, pipeline orchestration
│   │       ├── results.py          # GET /api/results
│   │       ├── brands.py           # brand history, trend, comparison
│   │       └── alerts.py           # crisis alert management
│   ├── agents/
│   │   ├── state.py                # AnalysisState TypedDict
│   │   ├── graph.py                # LangGraph compilation
│   │   └── nodes.py                # 4 pipeline nodes
│   ├── analysis/
│   │   ├── sentiment_analyzer.py   # LLM engine, batching, fallback, retry
│   │   └── cache.py                # same-day in-memory cache
│   ├── data/collectors/
│   │   ├── base_collector.py       # ABC, query building, emotional indicators
│   │   ├── reddit_collector.py     # asyncpraw
│   │   ├── youtube_collector.py    # httpx + Data API v3
│   │   └── hackernews_collector.py # Algolia API
│   ├── database/
│   │   ├── models.py               # SQLAlchemy models (4 tables)
│   │   └── session.py              # async engine, session factory
│   └── utils/
│       ├── config.py               # Pydantic Settings (env-driven)
│       └── logger.py               # structlog (JSON in prod, console in dev)
├── frontend/
│   ├── index.html                  # single-page app (5 tabs)
│   └── static/
│       ├── css/retro.css           # IBM Plex Mono terminal theme
│       ├── js/api.js               # API client
│       └── js/app.js               # all UI logic, Chart.js charts
├── tests/                          # 63 tests, zero external calls
├── .github/workflows/ci.yml        # 5-job CI/CD pipeline
├── Dockerfile                      # multi-stage build (builder + runtime)
├── docker-compose.yml              # local dev
├── docker-compose.prod.yml         # EC2 production (pulls from ECR)
└── pyproject.toml                  # dependencies, ruff config, pytest config
```

---

## Author

**Manjesh** — built end to end as a portfolio project demonstrating production AI engineering practices.

[GitHub](https://github.com/MANJESH-ctrl/Brandpulse-ai)
