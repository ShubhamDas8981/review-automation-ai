import json


def format_ticket_message(ticket: dict) -> str:
    return (
        "We're sorry about your experience. We've logged your complaint "
        "as a support ticket. Here is a copy:\n\n"
        + json.dumps(ticket, indent=2, ensure_ascii=False)
    )
