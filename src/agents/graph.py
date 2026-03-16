from langgraph.graph import StateGraph, END

from src.agents.state import AnalysisState
from src.agents.nodes import (
    node_process_text,
    node_analyze_sentiment,
    node_generate_insights,
    node_detect_crisis,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


def build_graph():
    """
    Build and compile the LangGraph analysis pipeline.
    Linear flow: process → sentiment → insights → crisis → END
    Each node enriches the shared AnalysisState.
    """
    graph = StateGraph(AnalysisState)

    # Register nodes
    graph.add_node("process_text", node_process_text)
    graph.add_node("analyze_sentiment", node_analyze_sentiment)
    graph.add_node("generate_insights", node_generate_insights)
    graph.add_node("detect_crisis", node_detect_crisis)

    # Wire edges — linear pipeline
    graph.set_entry_point("process_text")
    graph.add_edge("process_text", "analyze_sentiment")
    graph.add_edge("analyze_sentiment", "generate_insights")
    graph.add_edge("generate_insights", "detect_crisis")
    graph.add_edge("detect_crisis", END)

    return graph.compile()


# Single compiled graph — built once, reused across all requests
_compiled_graph = None


def get_compiled_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


async def run_analysis_graph(
    job_id: str,
    brand_name: str,
    raw_posts: list[dict],
) -> AnalysisState:
    """
    Run the full analysis graph on collected posts.
    Returns the final state with all results populated.
    """
    graph = get_compiled_graph()

    initial_state: AnalysisState = {
        "job_id": job_id,
        "brand_name": brand_name,
        "raw_posts": raw_posts,
        # All other fields start empty — nodes fill them in
        "processed_posts": [],
        "total_posts": 0,
        "platform_breakdown": {},
        "analyzed_posts": [],
        "sentiment_distribution": {},
        "weighted_sentiment": {},
        "aspect_results": {},
        "insight_summary": "",
        "key_themes": [],
        "recommendations": [],
        "crisis_score": 0.0,
        "crisis_triggered": False,
        "crisis_details": {},
        "errors": [],
        "current_node": "start",
    }

    logger.info(
        "graph_run_start",
        job_id=job_id,
        brand=brand_name,
        posts=len(raw_posts),
    )

    final_state = await graph.ainvoke(initial_state)

    logger.info(
        "graph_run_complete",
        job_id=job_id,
        sentiment=final_state.get("sentiment_distribution"),
        crisis=final_state.get("crisis_triggered"),
    )

    return final_state
