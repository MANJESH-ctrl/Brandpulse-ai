import enum
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class JobStatus(enum.StrEnum):
    PENDING = "pending"
    COLLECTING = "collecting"
    PROCESSING = "processing"
    ANALYZING = "analyzing"
    DONE = "done"
    FAILED = "failed"


class AnalysisJob(Base):
    """Tracks every background analysis run."""

    __tablename__ = "analysis_jobs"

    id = Column(String, primary_key=True)  # UUID string
    brand_name = Column(String, nullable=False, index=True)
    platforms = Column(JSON, nullable=False)  # ["reddit","youtube","hackernews"]
    keywords = Column(String, nullable=True)
    status = Column(String, default=JobStatus.PENDING)
    progress_message = Column(String, nullable=True)  # "Collecting Reddit posts..."
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    result = relationship("AnalysisResult", back_populates="job", uselist=False)
    posts = relationship("CollectedPost", back_populates="job")


class AnalysisResult(Base):
    """Final computed output of a completed analysis job."""

    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, ForeignKey("analysis_jobs.id"), nullable=False)
    brand_name = Column(String, nullable=False, index=True)
    sentiment_distribution = Column(
        JSON
    )  # {positive: 0.4, negative: 0.3, neutral: 0.3}
    weighted_sentiment = None  # engagement-weighted scores
    aspect_results = Column(JSON)  # {price: {positive: 0.7, count: 45}, ...}
    insight_summary = Column(Text)  # LLM-generated narrative (Groq)
    crisis_score = Column(Float, default=0.0)  # 0.0 = normal, >1.0 = alert
    crisis_triggered = Column(Integer, default=0)  # add this to AnalysisResult
    post_count = Column(Integer, default=0)
    platform_breakdown = Column(JSON)  # per-platform stats
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    model_used = Column(String, nullable=True)

    job = relationship("AnalysisJob", back_populates="result")


class CollectedPost(Base):
    """Individual post collected from any platform."""

    __tablename__ = "collected_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(
        String, nullable=True, index=True
    )  # original post id from collector
    job_id = Column(String, ForeignKey("analysis_jobs.id"), nullable=False, index=True)
    brand_name = Column(String, nullable=False, index=True)
    platform = Column(String, nullable=False)  # reddit / youtube / hackernews
    title = Column(String, nullable=True)
    text = Column(Text, nullable=True)
    cleaned_text = Column(Text, nullable=True)
    sentiment = Column(String, nullable=True)  # positive / negative / neutral
    confidence = Column(Float, nullable=True)
    emotional_intensity = Column(Float, nullable=True)
    engagement_score = Column(Float, nullable=True)
    positive_score = Column(Float, nullable=True)
    negative_score = Column(Float, nullable=True)
    neutral_score = Column(Float, nullable=True)
    platform_meta = Column(
        JSON, nullable=True
    )  # upvotes, views, likes — platform specific
    collected_at = Column(DateTime, default=lambda: datetime.now(UTC))
    is_sarcastic = Column(Integer, nullable=True)  # 0 or 1
    aspect = Column(String, nullable=True)  # product/pricing/service/etc
    brand_relevance = Column(Float, nullable=True)  # 0.0–1.0
    intensity = Column(String, nullable=True)  # mild/moderate/strong
    sentiment_reason = Column(String, nullable=True)  # LLM's 12-word reason

    job = relationship("AnalysisJob", back_populates="posts")


class CrisisAlert(Base):
    """Fired when negative sentiment spikes beyond normal baseline."""

    __tablename__ = "crisis_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    brand_name = Column(String, nullable=False, index=True)
    triggered_at = Column(DateTime, default=lambda: datetime.now(UTC))
    spike_percentage = Column(Float)  # how much above baseline
    baseline_score = Column(Float)  # brand's normal negative %
    current_score = Column(Float)  # this analysis's negative %
    top_concern = Column(String, nullable=True)  # most mentioned negative topic
    is_acknowledged = Column(Integer, default=0)  # 0=unread, 1=acknowledged
