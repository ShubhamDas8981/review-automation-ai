"""LangGraph workflow:

START -> input_guard -> classify -> (generate_reply | extract_ticket) -> output_guard -> END
              |
              +-- blocked --> END   (no LLM call is made)
"""
import json
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from app.ai import prompts
from app.ai.client import ask_llm
from app.core.logging import get_logger
from app.guardrails.input_guard import check_input
from app.guardrails.output_guard import check_reply, check_ticket
from app.guardrails.spotlight import spotlight, unmark
from app.schemas.ticket import Ticket

log = get_logger(__name__)

VALID_SENTIMENTS = {"positive", "negative", "neutral"}


class ReviewState(TypedDict):
    review: str
    sentiment: str
    reply: str | None
    ticket_json: dict | None
    blocked: bool
    block_stage: str | None     # "input" | "output"
    block_reason: str | None


# ---------------------------
# Guard nodes
# ---------------------------
def input_guard_node(state: ReviewState) -> dict:
    result = check_input(state["review"])
    return {
        "blocked": not result.passed,
        "block_stage": None if result.passed else "input",
        "block_reason": result.reason if not result.passed else None,
    }


def route_after_input(state: ReviewState) -> Literal["classify", "__end__"]:
    return END if state["blocked"] else "classify"


def output_guard_node(state: ReviewState) -> dict:
    if state["sentiment"] == "negative":
        result = check_ticket(state["ticket_json"] or {}, state["review"])
    else:
        result = check_reply(state["reply"] or "")
    return {
        "blocked": not result.passed,
        "block_stage": None if result.passed else "output",
        "block_reason": result.reason if not result.passed else None,
    }


# ---------------------------
# LLM nodes (all customer text is spotlighted)
# ---------------------------
def classify_sentiment(state: ReviewState) -> dict:
    wrapped, boundary = spotlight(state["review"])
    raw = ask_llm(
        prompts.CLASSIFY + prompts.untrusted_notice(boundary), wrapped, node="classify"
    )
    result = raw.lower().strip(" \n\t.\"'`")

    if result not in VALID_SENTIMENTS:
        raise ValueError(f"Invalid sentiment returned: {result[:30]!r}")

    log.info("sentiment classified", extra={"sentiment": result})
    return {"sentiment": result}


def route_by_sentiment(state: ReviewState) -> Literal["generate_reply", "extract_ticket"]:
    return "extract_ticket" if state["sentiment"] == "negative" else "generate_reply"


def generate_reply(state: ReviewState) -> dict:
    wrapped, boundary = spotlight(state["review"])
    system = prompts.REPLY_BASE + prompts.TONE_GUIDE[state["sentiment"]]
    reply = ask_llm(system + prompts.untrusted_notice(boundary), wrapped, node="reply")
    return {"reply": unmark(reply)}


def extract_ticket(state: ReviewState) -> dict:
    wrapped, boundary = spotlight(state["review"])
    schema = json.dumps(Ticket.model_json_schema())
    raw = ask_llm(
        prompts.ticket_prompt(schema, boundary),
        wrapped,
        node="ticket",
        response_format={"type": "json_object"},
    )
    ticket = Ticket.model_validate_json(raw)   # raises on bad JSON/schema -> Celery retry

    data = ticket.model_dump(mode="json")
    data = {k: unmark(v) if isinstance(v, str) else v for k, v in data.items()}
    return {"ticket_json": data}


# ---------------------------
# Graph
# ---------------------------
def build_graph():
    builder = StateGraph(ReviewState)

    builder.add_node("input_guard", input_guard_node)
    builder.add_node("classify", classify_sentiment)
    builder.add_node("generate_reply", generate_reply)
    builder.add_node("extract_ticket", extract_ticket)
    builder.add_node("output_guard", output_guard_node)

    builder.add_edge(START, "input_guard")
    builder.add_conditional_edges(
        "input_guard", route_after_input, {"classify": "classify", END: END}
    )
    builder.add_conditional_edges(
        "classify",
        route_by_sentiment,
        {"generate_reply": "generate_reply", "extract_ticket": "extract_ticket"},
    )
    builder.add_edge("generate_reply", "output_guard")
    builder.add_edge("extract_ticket", "output_guard")
    builder.add_edge("output_guard", END)

    return builder.compile()


graph = build_graph()


def process_review(review: str) -> ReviewState:
    initial: ReviewState = {
        "review": review,
        "sentiment": "",
        "reply": None,
        "ticket_json": None,
        "blocked": False,
        "block_stage": None,
        "block_reason": None,
    }
    return graph.invoke(initial)
