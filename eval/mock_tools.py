"""Canned tool responses for deterministic eval results.

Each tool call returns a fixed response regardless of arguments,
so scoring is purely about the model's tool selection and arg formatting.
"""

MOCK_RESPONSES = {
    "get_current_datetime": "Saturday, February 15, 2026 10:00 AM EST",
    "web_search": [
        {"title": "Result 1", "url": "https://example.com/1", "snippet": "First search result snippet."},
        {"title": "Result 2", "url": "https://example.com/2", "snippet": "Second search result snippet."},
        {"title": "Result 3", "url": "https://example.com/3", "snippet": "Third search result snippet."},
    ],
    "list_calendar_events": [
        {
            "id": "evt_001",
            "summary": "Team standup",
            "start": "2026-02-16T09:00:00-05:00",
            "end": "2026-02-16T09:30:00-05:00",
            "location": "",
            "description": "Daily standup meeting",
        },
        {
            "id": "evt_002",
            "summary": "Lunch with Sarah",
            "start": "2026-02-16T12:00:00-05:00",
            "end": "2026-02-16T13:00:00-05:00",
            "location": "Café Roma",
            "description": "",
        },
        {
            "id": "evt_003",
            "summary": "Dentist appointment",
            "start": "2026-02-17T14:00:00-05:00",
            "end": "2026-02-17T15:00:00-05:00",
            "location": "123 Main St",
            "description": "Regular checkup",
        },
    ],
    "create_calendar_event": {
        "id": "evt_new_001",
        "summary": "New Event",
        "link": "https://calendar.google.com/event?id=evt_new_001",
    },
    "update_calendar_event": {
        "id": "evt_001",
        "summary": "Updated Event",
        "link": "https://calendar.google.com/event?id=evt_001",
    },
}


def mock_executor(tool_name: str, tool_args: dict) -> str:
    """Return a canned response for the given tool call."""
    import json
    response = MOCK_RESPONSES.get(tool_name)
    if response is None:
        return f"Error: unknown tool '{tool_name}'"
    if isinstance(response, (dict, list)):
        return json.dumps(response)
    return str(response)
