"""Bedrock backends (Anthropic + Converse) and OllamaBackend with CompletionTrace.

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


def _init_bedrock_client(aws_region: str = "us-east-1"):
    """Shared Bedrock client init with token mapping."""
    token = os.environ.get("BEDROCK_TOKEN")
    if token:
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = token
    return boto3.client("bedrock-runtime", region_name=aws_region)


# ---------------------------------------------------------------------------
# BedrockBackend — Anthropic models (native API via invoke_model)
# ---------------------------------------------------------------------------

class BedrockBackend:
    """For Anthropic models on Bedrock. Uses the native Anthropic message format."""

    def __init__(self, model: str = "us.anthropic.claude-sonnet-4-20250514-v1:0", aws_region: str = "us-east-1"):
        self.model = model
        self.name = "bedrock"
        self.client = _init_bedrock_client(aws_region)

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
# ConverseBackend — Non-Anthropic Bedrock models (Meta, Mistral, Amazon, Cohere)
# Uses the Bedrock Converse API which provides a unified interface.
# ---------------------------------------------------------------------------

def _tools_to_converse_format(anthropic_tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool schemas to Bedrock Converse toolConfig format."""
    converse_tools = []
    for tool in anthropic_tools:
        schema = tool.get("input_schema", {"type": "object", "properties": {}})
        converse_tools.append({
            "toolSpec": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "inputSchema": {"json": schema},
            }
        })
    return converse_tools


class ConverseBackend:
    """For non-Anthropic models on Bedrock (Meta, Mistral, Amazon Nova, Cohere).
    Uses the Bedrock Converse API for a unified interface across providers."""

    def __init__(self, model: str, aws_region: str = "us-east-1"):
        self.model = model
        self.name = "bedrock"
        self.client = _init_bedrock_client(aws_region)
        self._converse_tools = _tools_to_converse_format(TOOLS)
        # Some models don't support vision
        self._supports_vision = any(k in model for k in [
            "nova-pro", "nova-premier", "nova-lite", "nova-2",
            "llama3-2-11b", "llama3-2-90b", "llama4",
            "pixtral",
        ])

    def run(self, prompt: str, image_b64: str | None = None) -> CompletionTrace:
        trace = CompletionTrace()

        user_content = []
        if image_b64 and self._supports_vision:
            user_content.append({
                "image": {
                    "format": "png",
                    "source": {"bytes": base64.b64decode(image_b64)},
                }
            })
        user_content.append({"text": prompt})
        messages = [{"role": "user", "content": user_content}]

        start = time.monotonic()
        try:
            for _ in range(MAX_TURNS):
                response = self._converse(messages)
                output = response.get("output", {})
                msg = output.get("message", {})
                turn = Turn()

                for block in msg.get("content", []):
                    if "text" in block:
                        turn.text += block["text"]
                    elif "toolUse" in block:
                        tu = block["toolUse"]
                        turn.tool_calls.append(ToolCall(
                            name=tu["name"],
                            args=tu.get("input", {}),
                            id=tu["toolUseId"],
                        ))

                trace.turns.append(turn)

                stop = response.get("stopReason", "")
                if stop != "tool_use":
                    break

                # Execute mock tools
                tool_results = []
                for tc in turn.tool_calls:
                    result_str = mock_executor(tc.name, tc.args)
                    # Converse API requires {"json": <object>} — arrays and
                    # primitives must be wrapped in an object.
                    try:
                        result_json = json.loads(result_str)
                    except (json.JSONDecodeError, TypeError):
                        result_json = None
                    if isinstance(result_json, dict):
                        content_block = {"json": result_json}
                    elif isinstance(result_json, list):
                        content_block = {"json": {"results": result_json}}
                    else:
                        content_block = {"text": str(result_str)}
                    tool_results.append({
                        "toolResult": {
                            "toolUseId": tc.id,
                            "content": [content_block],
                        }
                    })
                messages.append({"role": "assistant", "content": msg["content"]})
                messages.append({"role": "user", "content": tool_results})

        except Exception as e:
            trace.error = str(e)

        trace.latency_ms = (time.monotonic() - start) * 1000
        trace.final_text = trace.turns[-1].text if trace.turns else ""
        return trace

    def _converse(self, messages: list[dict]) -> dict:
        kwargs = {
            "modelId": self.model,
            "messages": messages,
            "system": [{"text": SYSTEM_PROMPT}],
            "toolConfig": {"tools": self._converse_tools},
            "inferenceConfig": {"maxTokens": 4096},
        }
        return self.client.converse(**kwargs)


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

                messages.append(msg)

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
# Model routing — pick the right backend class for a Bedrock model ID
# ---------------------------------------------------------------------------

ANTHROPIC_PREFIXES = ("anthropic.", "us.anthropic.", "eu.anthropic.", "ap.anthropic.", "global.anthropic.")


def make_bedrock_backend(model: str, aws_region: str = "us-east-1"):
    """Return the appropriate backend for a Bedrock model ID."""
    if any(model.startswith(p) for p in ANTHROPIC_PREFIXES):
        return BedrockBackend(model=model, aws_region=aws_region)
    return ConverseBackend(model=model, aws_region=aws_region)
