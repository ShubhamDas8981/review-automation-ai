import pytest

from app.utils.phone import digits


@pytest.mark.parametrize(
    "raw",
    ["+91 89819-64505", "+918981964505", "91-8981964505", "(+91) 89819 64505", "918981964505"],
)
def test_digits_normalizes_formats(raw):
    assert digits(raw) == "918981964505"


def test_digits_handles_none_and_empty():
    assert digits(None) == ""
    assert digits("") == ""
