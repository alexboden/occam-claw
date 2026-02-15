"""BedrockBackend + OllamaBackend with CompletionTrace.

Both backends reimplement the tool loop (rather than reusing LLM.complete())
so we can capture the full trace: which tools were called, with what args,
in what order, plus latency.
"""

import base64
import json
import os
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field

import boto3

from llm import TOOLS
from eval.mock_tools import mock_executor


# ---------------------------------------------------------------------------
# Trace dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ToolCall:
    name: str
    args: dict
    id: str


@dataclass
class Turn:
    tool_calls: list[ToolCall] = field(default_factory=list)
    text: str = ""


@dataclass
class CompletionTrace:
    turns: list[Turn] = field(default_factory=list)
    final_text: str = ""
    latency_ms: float = 0.0
    error: str | None = None


# ---------------------------------------------------------------------------
# Fixed system prompt (pinned time for reproducibility)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are Occam, a concise personal assistant. "
    "The current date and time is Saturday, February 15, 2026 10:00 AM EST. "
    "The user's timezone is America/Toronto (EST/EDT). Use this for all calendar events unless specified otherwise. "
    "You have access to the user's Google Calendar. Be brief. "
    "When the user asks you to do something and you have a tool for it, use the tool. "
    "Do not ask for confirmation unless the request is ambiguous. "
    "Use Signal formatting: *italic*, **bold**, ~strikethrough~, `monospace`."
)

MAX_TURNS = 10


# ---------------------------------------------------------------------------
# BedrockBackend
# ---------------------------------------------------------------------------

class BedrockBackend:
    def __init__(self, model: str = "us.anthropic.claude-sonnet-4-20250514-v1:0", aws_region: str = "us-east-1"):
        self.model = model
        self.name = "bedrock"
        token = os.environ.get("BEDROCK_TOKEN")
        if token:
            os.environ["AWS_BEARER_TOKEN_BEDROCK"] = token
        self.client = boto3.client("bedrock-runtime", region_name=aws_region)

    def run(self, prompt: str, image_b64: str | None = None) -> CompletionTrace:
        trace = CompletionTrace()
        content: list[dict] = []
        if image_b64:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
            })
        content.append({"type": "text", "text": prompt})
        messages = [{"role": "user", "content": content}]

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "system": SYSTEM_PROMPT,
            "messages": messages,
            "tools": TOOLS,
        }

        start = time.monotonic()
        try:
            for _ in range(MAX_TURNS):
                response = self._invoke(body)
                turn = Turn()

                for block in response.get("content", []):
                    if block.get("type") == "text":
                        turn.text += block["text"]
                    elif block.get("type") == "tool_use":
                        turn.tool_calls.append(ToolCall(
                            name=block["name"],
                            args=block.get("input", {}),
                            id=block["id"],
                        ))

                trace.turns.append(turn)

                if response.get("stop_reason") != "tool_use":
                    break

                # Execute mock tools and continue
                tool_results = []
                for tc in turn.tool_calls:
                    result = mock_executor(tc.name, tc.args)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": result,
                    })
                messages.append({"role": "assistant", "content": response["content"]})
                messages.append({"role": "user", "content": tool_results})
                body["messages"] = messages

        except Exception as e:
            trace.error = str(e)

        trace.latency_ms = (time.monotonic() - start) * 1000
        trace.final_text = trace.turns[-1].text if trace.turns else ""
        return trace

    def _invoke(self, body: dict) -> dict:
        response = self.client.invoke_model(
            modelId=self.model,
            body=json.dumps(body),
        )
        return json.loads(response["body"].read())


# ---------------------------------------------------------------------------
# OllamaBackend
# ---------------------------------------------------------------------------

def _anthropic_to_openai_tools(anthropic_tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool schemas to OpenAI function-calling format."""
    openai_tools = []
    for tool in anthropic_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return openai_tools


class OllamaBackend:
    def __init__(self, model: str = "llama3.1:8b", base_url: str = "http://localhost:11434"):
        self.model = model
        self.name = "ollama"
        self.base_url = base_url.rstrip("/")
        self.openai_tools = _anthropic_to_openai_tools(TOOLS)

    def run(self, prompt: str, image_b64: str | None = None) -> CompletionTrace:
        trace = CompletionTrace()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]

        user_msg: dict = {"role": "user", "content": prompt}
        if image_b64:
            user_msg["images"] = [image_b64]
        messages.append(user_msg)

        start = time.monotonic()
        try:
            for _ in range(MAX_TURNS):
                response = self._chat(messages)
                msg = response.get("message", {})
                turn = Turn()
                turn.text = msg.get("content", "")

                tool_calls_raw = msg.get("tool_calls", [])
                for i, tc in enumerate(tool_calls_raw):
                    fn = tc.get("function", {})
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    turn.tool_calls.append(ToolCall(
                        name=fn.get("name", ""),
                        args=args,
                        id=f"call_{i}",
                    ))

                trace.turns.append(turn)

                if not turn.tool_calls:
                    break

                # Add assistant message to history
                messages.append(msg)

                # Execute mock tools and add results
                for tc in turn.tool_calls:
                    result = mock_executor(tc.name, tc.args)
                    messages.append({
                        "role": "tool",
                        "content": result,
                    })

        except Exception as e:
            trace.error = str(e)

        trace.latency_ms = (time.monotonic() - start) * 1000
        trace.final_text = trace.turns[-1].text if trace.turns else ""
        return trace

    def _chat(self, messages: list[dict]) -> dict:
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "tools": self.openai_tools,
            "stream": False,
        }).encode()

        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

BACKENDS = {
    "bedrock": BedrockBackend,
    "ollama": OllamaBackend,
}
