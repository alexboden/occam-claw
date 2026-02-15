# Occam-Claw

A minimal personal AI assistant that runs on Signal via "Note to Self." Built with Occam's razor — fewest components, simplest architecture.

## What it does

Message yourself on Signal and get AI-powered responses. The bot can:

- **Manage your Google Calendar** — list, create, and update events
- **Maintain conversation threads** — reply to a bot message to continue the conversation
- **Search the web** via DuckDuckGo

## Setup

### Prerequisites

- Docker & Docker Compose
- A Signal account
- An AWS account with Bedrock access (Claude models enabled)
- A Google Cloud project with Calendar API enabled

### 1. Clone and configure

```bash
cp config.example.toml config.toml
# Edit config.toml with your settings
```

### 2. Set secrets

Create a `.env` file:

```
BEDROCK_TOKEN=your-bedrock-api-key
AWS_REGION=us-east-1
```

### 3. Link Signal

```bash
docker compose up signal-api
# Open http://127.0.0.1:8080/v1/qrcodelink?device_name=occam
# Scan QR code with Signal > Settings > Linked Devices
```

Update `config.toml` with your number (include country code):

```toml
[signal]
enabled = true
number = "+1234567890"
```

### 4. Google Calendar

1. Go to [console.cloud.google.com](https://console.cloud.google.com), create a project
2. Enable the **Google Calendar API**
3. Create a **Service Account** (APIs & Services > Credentials)
4. Download the JSON key to `data/google-service-account.json`
5. Share your calendar with the service account email ("Make changes to events")

Update `config.toml`:

```toml
[google]
credentials = "data/google-service-account.json"
calendar_id = "your-email@gmail.com"
```

### 5. Run

```bash
docker compose up -d
```

## Usage

Open **Note to Self** in Signal and type a message. The bot responds with a quote-reply.

- New messages start a fresh conversation (no history)
- Swipe-reply to a bot message to continue that thread

### Examples

```
you: what's on my calendar this week?
you: add a meeting with Alex tomorrow at 3pm for 1 hour
you: search for the latest news on rust programming
```

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

Everything else is Python stdlib.

## Swapping LLMs

Edit `llm.py`. The `LLM` class exposes one method: `complete(messages, tool_executor) -> str`. Replace the body with any provider's SDK.

## Security

- Runs on your Tailscale network — no public ports
- `signal-api` binds to `127.0.0.1` only
- Only responds to your own messages (Note to Self)
- Credentials stored in `data/` (gitignored)
