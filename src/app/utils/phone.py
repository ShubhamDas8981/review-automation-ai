import re


def digits(number: str | None) -> str:
    """Keep digits only, so '+91 89819-64505' == '918981964505'."""
    return re.sub(r"\D", "", number or "")
