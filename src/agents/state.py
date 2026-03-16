from typing import Any, TypedDict


class AnalysisState(TypedDict):
    # ── Input ────────────────────────────────────────────────
    job_id: str
    brand_name: str

    # ── Raw data from DB (set by pipeline before graph runs) ─
    raw_posts: list[dict[str, Any]]

    # ── Node 1 output: text processing ───────────────────────
    processed_posts: list[dict[str, Any]]
    total_posts: int
    platform_breakdown: dict[str, int]

    # ── Node 2 output: sentiment analysis ────────────────────
    analyzed_posts: list[dict[str, Any]]
    sentiment_distribution: dict[str, float]   
    weighted_sentiment: dict[str, float]        
    aspect_results: dict[str, Any]             

    # ── Node 3 output: LLM insights ──────────────────────────
    insight_summary: str
    key_themes: list[str]
    recommendations: list[str]

    # ── Node 4 output: crisis detection ──────────────────────
    crisis_score: float          # 0.0 = normal, >1.0 = alert
    crisis_triggered: bool
    crisis_details: dict[str, Any]

    # ── Control flow ─────────────────────────────────────────
    errors: list[str]            # non-fatal errors accumulate here
    current_node: str            # for progress tracking
