# Setup

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
