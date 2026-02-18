import asyncio
import base64
import logging
import tomllib
from pathlib import Path

from llm import LLM
from channels.cli import interactive
import store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger(__name__)


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.toml"
    if config_path.exists():
        return tomllib.loads(config_path.read_text())
    return {}


def _fmt_time(iso: str) -> str:
    """Format an ISO datetime string into a friendly display like 'Feb 18, 10:00 AM EST'."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    try:
        dt = datetime.fromisoformat(iso).astimezone(ZoneInfo("America/Toronto"))
        return dt.strftime("%b %-d, %-I:%M %p %Z")
    except (ValueError, TypeError):
        return iso


def _format_calendar_action(name: str, args: dict, result) -> str | None:
    """Format a calendar tool call into a human-readable confirmation."""
    if not isinstance(result, dict) or "id" not in result:
        return None

    if name == "create_calendar_event":
        label = "**Event Created**"
    elif name == "update_calendar_event":
        label = "**Event Updated**"
    else:
        return None

    old = result.get("old", {})
    is_update = name == "update_calendar_event" and old

    lines = ["\n\n---", label]

    if is_update:
        old_summary = old.get("summary", "")
        new_summary = args.get("summary", "")
        if new_summary and new_summary != old_summary:
            lines.append(f"*Title:* {old_summary} → {new_summary}")
        else:
            lines.append(f"*Title:* {new_summary or old_summary}")

        old_start = old.get("start", "")
        old_end = old.get("end", "")
        new_start = args.get("start", "")
        new_end = args.get("end", "")
        if new_start and new_start != old_start:
            lines.append(f"*Start:* {_fmt_time(old_start)} → {_fmt_time(new_start)}")
        elif new_start:
            lines.append(f"*Start:* {_fmt_time(new_start)}")
        if new_end and new_end != old_end:
            lines.append(f"*End:* {_fmt_time(old_end)} → {_fmt_time(new_end)}")
        elif new_end:
            lines.append(f"*End:* {_fmt_time(new_end)}")

        for key, label_str in [("description", "Description"), ("location", "Location")]:
            new_val = args.get(key, "")
            old_val = old.get(key, "")
            if new_val and new_val != old_val:
                lines.append(f"*{label_str}:* {old_val} → {new_val}" if old_val else f"*{label_str}:* {new_val}")
    else:
        if args.get("summary"):
            lines.append(f"*Title:* {args['summary']}")
        if args.get("start"):
            lines.append(f"*Start:* {_fmt_time(args['start'])}")
        if args.get("end"):
            lines.append(f"*End:* {_fmt_time(args['end'])}")
        if args.get("description"):
            lines.append(f"*Description:* {args['description']}")
        if args.get("location"):
            lines.append(f"*Location:* {args['location']}")

    if result.get("link"):
        lines.append(f"*Link:* {result['link']}")
    return "\n".join(lines)


def handle_message(llm: LLM, config: dict):
    async def _handler(msg):
        try:
            history = store.load(msg.thread_id)

            # Build user content: text + any image attachments
            if msg.attachments:
                content_blocks = []
                for att in msg.attachments:
                    content_blocks.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": att.media_type,
                            "data": base64.b64encode(att.data).decode(),
                        },
                    })
                content_blocks.append({"type": "text", "text": msg.text or "What is this image?"})
                history.append({"role": "user", "content": content_blocks})
            else:
                history.append({"role": "user", "content": msg.text})
            calendar_confirmations = []

            def tool_executor(name, args):
                from tools import general
                if name == "get_current_datetime":
                    return general.get_current_datetime()
                elif name == "web_search":
                    return general.web_search(args["query"], args.get("max_results", 5))
                elif name == "list_calendar_events":
                    from tools import calendar
                    creds = config.get("google", {}).get("credentials", "data/google-service-account.json")
                    cal_id = config.get("google", {}).get("calendar_id", "primary")
                    return calendar.list_events(creds, cal_id, args.get("days", 7))
                elif name == "create_calendar_event":
                    from tools import calendar
                    creds = config.get("google", {}).get("credentials", "data/google-service-account.json")
                    cal_id = config.get("google", {}).get("calendar_id", "primary")
                    result = calendar.create_event(creds, cal_id, **args)
                    confirmation = _format_calendar_action(name, args, result)
                    if confirmation:
                        calendar_confirmations.append(confirmation)
                    return result
                elif name == "update_calendar_event":
                    from tools import calendar
                    creds = config.get("google", {}).get("credentials", "data/google-service-account.json")
                    cal_id = config.get("google", {}).get("calendar_id", "primary")
                    event_id = args.pop("event_id")
                    result = calendar.update_event(creds, cal_id, event_id, **args)
                    confirmation = _format_calendar_action(name, args, result)
                    if confirmation:
                        calendar_confirmations.append(confirmation)
                    return result
                return {"error": f"Unknown tool: {name}"}

            log.info("[%s] Calling LLM...", msg.thread_id)
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, llm.complete, history, tool_executor)

            if calendar_confirmations:
                response += "".join(calendar_confirmations)

            log.info("[%s] LLM response: %s", msg.thread_id, response[:80])

            store.append(msg.thread_id, "user", msg.text)
            store.append(msg.thread_id, "assistant", response)
            await msg.reply(response)
            log.info("[%s] Reply sent", msg.thread_id)
        except Exception:
            log.exception("[%s] Error handling message", msg.thread_id)

    return _handler


async def main():
    config = load_config()
    llm_config = config.get("llm", {})
    llm = LLM(
        model=llm_config.get("model", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
        aws_region=llm_config.get("aws_region", "us-east-1"),
    )
    handler = handle_message(llm, config)

    tasks = []

    # CLI channel (auto-disabled when not a TTY, e.g. in Docker)
    import sys
    if config.get("cli", {}).get("enabled", True) and sys.stdin.isatty():
        tasks.append(interactive(handler))

    # Signal channel
    if config.get("signal", {}).get("enabled", False):
        from channels.signal import listen
        tasks.append(listen(
            config["signal"]["number"],
            config["signal"].get("api_url", "http://signal-api:8080"),
            handler,
        ))

    # Email channel — incoming emails get responded to via Signal
    if config.get("email", {}).get("enabled", False):
        from channels.email import listen as email_listen
        from channels.signal import _send as signal_send
        import os

        signal_number = config.get("signal", {}).get("number", "")
        signal_api = config.get("signal", {}).get("api_url", "http://signal-api:8080")

        def make_signal_reply(label: str, thread_id: str):
            async def reply(text: str):
                sent_ts = await signal_send(signal_api, signal_number, signal_number, label + text)
                if sent_ts:
                    store.map_timestamp(int(sent_ts), thread_id)
            return reply

        tasks.append(email_listen(
            config["email"]["imap_host"],
            config["email"]["user"],
            os.environ.get("OCCAM_EMAIL_PASSWORD", ""),
            handler,
            make_reply=make_signal_reply,
            allowed_senders=config["email"].get("allowed_senders"),
        ))

    if not tasks:
        print("No channels enabled. Enable at least one in config.toml.")
        return

    await asyncio.gather(*tasks)


def main_cli():
    asyncio.run(main())


if __name__ == "__main__":
    main_cli()
