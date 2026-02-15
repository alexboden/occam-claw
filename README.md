# Occam-Claw

A minimal personal AI assistant that runs on Signal. Inspired by [Occam's razor](https://en.wikipedia.org/wiki/Occam%27s_razor).

## What it does

Message yourself on Signal and get AI-powered responses. The bot can:

- **Manage your Google Calendar** — list, create, and update events
- **Maintain conversation threads** — reply to a bot message to continue the conversation
- **Search the web** via DuckDuckGo

See [SETUP.md](SETUP.md) for installation and configuration.

## Project structure

```
occam.py           # main entry point, message handler, tool executor
llm.py             # Claude via Bedrock (invoke_model), tool-use loop
store.py           # JSONL conversation persistence + thread mapping
channels/
  signal.py        # signal-cli-rest-api websocket + HTTP
  cli.py           # stdin/stdout for local testing
tools/
  general.py       # web search (DuckDuckGo), current datetime
  calendar.py      # Google Calendar list/create/update
```

## Dependencies

- `boto3` — Claude via AWS Bedrock
- `ddgs` — DuckDuckGo search
- `aiohttp` — Signal websocket + HTTP
- `google-api-python-client` + `google-auth` — Calendar API

## Swapping LLMs

Edit `llm.py`. The `LLM` class exposes one method: `complete(messages, tool_executor) -> str`. 

## Security

- Runs on your Tailscale network — no public ports
- `signal-api` binds to `127.0.0.1` only
- Only responds to your own messages (Note to Self)
- Credentials stored in `data/`
