import pytest

from app.services.wati import extract_messages

INBOUND = {
    "eventType": "message",
    "whatsappMessageId": "wamid.123",
    "waId": "918981964505",
    "text": "hello",
    "type": "text",
    "timestamp": "1700000000",
    "owner": False,
    "statusString": "SENT",
}


def test_inbound_text_message_is_extracted():
    assert extract_messages(INBOUND) == [
        {"id": "wamid.123", "from": "918981964505", "text": "hello", "ts": "1700000000"}
    ]


@pytest.mark.parametrize("event", ["message", "messageReceived", "newContactMessageReceived"])
def test_all_inbound_event_names_are_accepted(event):
    assert len(extract_messages({**INBOUND, "eventType": event})) == 1


def test_snake_case_payload_is_accepted():
    payload = {
        "event_type": "message", "whatsapp_message_id": "wamid.9", "wa_id": "911",
        "text": "hi", "type": "text", "timestamp": "5", "owner": False,
    }
    assert extract_messages(payload)[0]["from"] == "911"


@pytest.mark.parametrize("payload", [
    {**INBOUND, "owner": True},                       # sent by us or an operator
    {**INBOUND, "eventType": "sessionMessageSent"},   # echo of our own reply
    {**INBOUND, "eventType": "sentMessageDELIVERED_v2"},
    {**INBOUND, "eventType": "templateMessageSent"},
    {**INBOUND, "type": "image"},
    {**INBOUND, "text": ""},
    {**INBOUND, "text": None},
    {},
])
def test_non_customer_text_events_are_ignored(payload):
    assert extract_messages(payload) == []
