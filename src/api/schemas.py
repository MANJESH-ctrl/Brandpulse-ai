from pydantic import BaseModel, field_validator
from typing import Any


class AnalyzeRequest(BaseModel):
    brand_name: str
    keywords: str = ""
    platforms: list[str] = ["reddit", "youtube", "hackernews"]
    limit_per_platform: int = 100

    @field_validator("brand_name")
    @classmethod
    def brand_name_must_not_be_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("brand_name cannot be empty")
        return v

    @field_validator("platforms")
    @classmethod
    def platforms_must_be_valid(cls, v: list[str]) -> list[str]:
        valid = {"reddit", "youtube", "hackernews"}
        invalid = set(v) - valid
        if invalid:
            raise ValueError(f"Invalid platforms: {invalid}. Choose from {valid}")
        if not v:
            raise ValueError("At least one platform must be selected")
        return v

    @field_validator("limit_per_platform")
    @classmethod
    def limit_must_be_reasonable(cls, v: int) -> int:
        if not (10 <= v <= 200):
            raise ValueError("limit_per_platform must be between 10 and 200")
        return v


class JobStatusResponse(BaseModel):
    job_id: str
    brand_name: str
    status: str
    progress_message: str | None
    created_at: str
    completed_at: str | None
    error_message: str | None


class AnalyzeResponse(BaseModel):
    job_id: str
    status: str
    message: str
    poll_url: str


class PostsResponse(BaseModel):
    job_id: str
    brand_name: str
    total_posts: int
    platform_breakdown: dict[str, int]
    posts: list[dict[str, Any]]




class AspectData(BaseModel):
    count: int
    positive: float
    negative: float
    neutral: float
    avg_intensity: float


class FullAnalysisResult(BaseModel):
    job_id: str
    brand_name: str
    status: str
    post_count: int
    platform_breakdown: dict[str, Any]
    sentiment_distribution: dict[str, float]
    weighted_sentiment: dict[str, float] | None = None
    aspect_results: dict[str, Any]
    insight_summary: str | None
    crisis_score: float
    crisis_triggered: bool
    created_at: str
    completed_at: str | None
    model_used: str | None = None



class BrandSummary(BaseModel):
    brand_name: str
    total_analyses: int
    latest_analysis_at: str | None
    avg_positive: float
    avg_negative: float
    avg_neutral: float
    latest_crisis_score: float
    total_posts_analyzed: int


class BrandCompareResponse(BaseModel):
    brands: list[str]
    comparison: list[dict[str, Any]]


class CrisisAlertResponse(BaseModel):
    id: int
    brand_name: str
    triggered_at: str
    spike_percentage: float
    current_score: float
    top_concern: str | None
    is_acknowledged: bool


class TrendPoint(BaseModel):
    date: str
    positive: float
    negative: float
    neutral: float
    post_count: int
