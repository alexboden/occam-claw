import json
import os
from datetime import datetime, timezone

import boto3


def _system_prompt() -> str:
    now = datetime.now(timezone.utc).astimezone()
    date_str = now.strftime("%A, %B %d, %Y %I:%M %p %Z")
    return (
        f"You are Occam, a concise personal assistant. "
        f"The current date and time is {date_str}. "
        f"The user's timezone is America/Toronto (EST/EDT). Use this for all calendar events unless specified otherwise. "
        f"You have access to the user's Google Calendar. Be brief. "
        f"When the user asks you to do something and you have a tool for it, use the tool. "
        f"Do not ask for confirmation unless the request is ambiguous. "
        f"Use Signal formatting: *italic*, **bold**, ~strikethrough~, `monospace`."
    )

TOOLS = [
    {
        "name": "get_current_datetime",
        "description": "Get the current date and time.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "web_search",
        "description": "Search the web for information.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
                "max_results": {"type": "integer", "description": "Max results to return. Default 5."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_calendar_events",
        "description": "List upcoming calendar events for the next N days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days ahead to look. Default 7.",
                }
            },
        },
    },
    {
        "name": "create_calendar_event",
        "description": "Create a new calendar event.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "start": {"type": "string", "description": "ISO 8601 datetime with offset, e.g. 2026-02-15T14:00:00-05:00"},
                "end": {"type": "string", "description": "ISO 8601 datetime with offset, e.g. 2026-02-15T15:00:00-05:00"},
                "description": {"type": "string"},
                "timezone": {"type": "string", "description": "IANA timezone. Default America/Toronto."},
            },
            "required": ["summary", "start", "end"],
        },
    },
    {
        "name": "update_calendar_event",
        "description": "Update an existing calendar event. Use list_calendar_events first to get the event ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event ID from list_calendar_events."},
                "summary": {"type": "string"},
                "start": {"type": "string", "description": "ISO 8601 datetime with offset."},
                "end": {"type": "string", "description": "ISO 8601 datetime with offset."},
                "description": {"type": "string"},
                "location": {"type": "string"},
            },
            "required": ["event_id"],
        },
    },
]


class LLM:
    def __init__(self, model: str = "us.anthropic.claude-sonnet-4-20250514-v1:0", aws_region: str = "us-east-1"):
        self.model = model
        # Map BEDROCK_TOKEN to the env var boto3 expects for API key auth
        token = os.environ.get("BEDROCK_TOKEN")
        if token:
            os.environ["AWS_BEARER_TOKEN_BEDROCK"] = token
        self.client = boto3.client("bedrock-runtime", region_name=aws_region)

    def complete(self, messages: list[dict], tool_executor=None) -> str:
        """Send messages to Claude via Bedrock invoke_model, handle tool calls in a loop."""
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "system": _system_prompt(),
            "messages": messages,
        }
        if tool_executor:
            body["tools"] = TOOLS

        response = self._invoke(body)

        while response.get("stop_reason") == "tool_use" and tool_executor:
            tool_results = []
            for block in response["content"]:
                if block.get("type") == "tool_use":
                    result = tool_executor(block["name"], block["input"])
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": str(result),
                    })
            messages.append({"role": "assistant", "content": response["content"]})
            messages.append({"role": "user", "content": tool_results})
            body["messages"] = messages
            response = self._invoke(body)

        return "".join(
            b["text"] for b in response.get("content", []) if b.get("type") == "text"
        )

    def _invoke(self, body: dict) -> dict:
        response = self.client.invoke_model(
            modelId=self.model,
            body=json.dumps(body),
        )
        return json.loads(response["body"].read())
