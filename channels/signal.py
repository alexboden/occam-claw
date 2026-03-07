import asyncio
import json
import logging
import uuid

import aiohttp

from channels import Attachment, Message
import store

log = logging.getLogger(__name__)

_INITIAL_BACKOFF = 5
_MAX_BACKOFF = 60
_STARTUP_DELAY = 15  # seconds to wait for signal-cli daemon

# ---------------------------------------------------------------------------
# Shared HTTP session (lazy, one per event-loop)
# ---------------------------------------------------------------------------
_session: aiohttp.ClientSession | None = None


def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
        )
    return _session


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

async def _send(
    api_url: str, from_number: str, to_number: str, text: str,
    quote_timestamp: int | None = None, quote_author: str | None = None,
    quote_message: str | None = None,
) -> int | None:
    """Send a Signal message. Returns the sent-message timestamp or None."""
    payload = {
        "message": text,
        "number": from_number,
        "recipients": [to_number],
        "notify_self": True,
        "text_mode": "styled",
    }
    if quote_timestamp and quote_author:
        payload["quote_timestamp"] = quote_timestamp
        payload["quote_author"] = quote_author
        payload["quote_message"] = quote_message or ""
    try:
        resp = await _get_session().post(f"{api_url}/v2/send", json=payload)
        if resp.status != 201:
            log.error("Signal send failed: %s %s", resp.status, await resp.text())
            return None
        result = await resp.json()
        return result.get("timestamp")
    except Exception as e:
        log.error("Signal send error: %s", e)
        return None


def _extract_message(data: dict, owner_number: str) -> tuple[str, str, int | None, list[dict]] | None:
    """Parse a Note-to-Self message from a Signal envelope.

    Returns (sender, text, quote_timestamp, attachments) or None.
    """
    envelope = data.get("envelope", {})

    sync = envelope.get("syncMessage", {}).get("sentMessage")
    if not sync:
        return None

    text = sync.get("message", "")
    if not text and not sync.get("attachments"):
        return None

    if sync.get("groupInfo") or sync.get("groupId"):
        return None

    # Note to Self: destination is our own number/uuid, or null (linked device)
    dest = sync.get("destinationNumber") or sync.get("destinationUuid")
    source = envelope.get("sourceNumber") or envelope.get("sourceUuid")
    if dest is not None and dest != owner_number and dest != source:
        return None

    quote_ts = None
    quote = sync.get("quote")
    if quote:
        quote_ts = quote.get("id")

    attachments = sync.get("attachments", [])
    return owner_number, text, quote_ts, attachments


async def _react(api_url: str, number: str, recipient: str,
                 target_author: str, timestamp: int, emoji: str) -> None:
    payload = {
        "reaction": emoji,
        "recipient": recipient,
        "target_author": target_author,
        "timestamp": timestamp,
    }
    try:
        resp = await _get_session().post(
            f"{api_url}/v1/reactions/{number}", json=payload,
        )
        if resp.status not in (200, 201, 204):
            log.error("Signal react failed: %s %s", resp.status, await resp.text())
    except Exception as e:
        log.error("Signal react error: %s", e)


async def _remove_react(api_url: str, number: str, recipient: str,
                        target_author: str, timestamp: int, emoji: str) -> None:
    payload = {
        "reaction": emoji,
        "recipient": recipient,
        "target_author": target_author,
        "timestamp": timestamp,
    }
    try:
        resp = await _get_session().delete(
            f"{api_url}/v1/reactions/{number}", json=payload,
        )
        if resp.status not in (200, 201, 204):
            log.error("Signal remove-react failed: %s %s", resp.status, await resp.text())
    except Exception as e:
        log.error("Signal remove-react error: %s", e)


async def _download_attachment(api_url: str, attachment_id: str) -> bytes | None:
    try:
        resp = await _get_session().get(
            f"{api_url}/v1/attachments/{attachment_id}",
        )
        if resp.status == 200:
            return await resp.read()
        log.error("Attachment download %s failed: %s", attachment_id, resp.status)
    except Exception as e:
        log.error("Attachment download error: %s", e)
    return None


# ---------------------------------------------------------------------------
# WebSocket listener
# ---------------------------------------------------------------------------

async def listen(number: str, api_url: str, on_message) -> None:
    """Connect to signal-cli-rest-api WebSocket and dispatch incoming messages."""
    sent_timestamps: set[int] = set()

    ws_url = api_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_endpoint = f"{ws_url}/v1/receive/{number}"

    log.info("Signal: waiting %ss for daemon startup…", _STARTUP_DELAY)
    await asyncio.sleep(_STARTUP_DELAY)

    backoff = _INITIAL_BACKOFF

    while True:
        ws_session = aiohttp.ClientSession()
        try:
            log.info("Signal WS connecting to %s", ws_endpoint)
            async with ws_session.ws_connect(ws_endpoint, heartbeat=30) as ws:
                log.info("Signal WS connected for %s", number)
                backoff = _INITIAL_BACKOFF  # reset on success

                async for raw in ws:
                    if raw.type == aiohttp.WSMsgType.TEXT:
                        await _on_ws_text(
                            raw.data, number, api_url, on_message,
                            sent_timestamps,
                        )
                    elif raw.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        log.warning("Signal WS closed/error: %s", ws.exception())
                        break

        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
            log.warning("Signal WS failed: %s – retry in %ss", e, backoff)
        except Exception:
            log.exception("Signal WS unexpected error – retry in %ss", backoff)
        finally:
            await ws_session.close()

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, _MAX_BACKOFF)


async def _on_ws_text(
    raw_data: str,
    number: str,
    api_url: str,
    on_message,
    sent_timestamps: set[int],
) -> None:
    """Handle a single TEXT frame from the WebSocket."""
    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError:
        log.warning("Signal WS: bad JSON: %s", raw_data[:200])
        return

    envelope = data.get("envelope", {})
    msg_ts = envelope.get("timestamp")

    if msg_ts in sent_timestamps:
        sent_timestamps.discard(msg_ts)
        return

    result = _extract_message(data, number)
    if not result:
        return

    sender, text, quote_ts, raw_attachments = result

    # Download image attachments
    attachments: list[Attachment] = []
    for att in raw_attachments:
        ct = att.get("contentType", "")
        att_id = att.get("id")
        if att_id and ct.startswith("image/"):
            img = await _download_attachment(api_url, att_id)
            if img:
                attachments.append(Attachment(data=img, media_type=ct))

    # Resolve or create thread
    thread_id = store.get_thread_for_timestamp(quote_ts) if quote_ts else None
    if not thread_id:
        thread_id = uuid.uuid4().hex[:12]

    log.info("Signal [%s] %s: %s", thread_id, sender, text[:60])

    if msg_ts:
        store.map_timestamp(msg_ts, thread_id)
        await _react(api_url, number, sender, sender, msg_ts, "\u231b")

    async def reply(resp, _to=sender, _tid=thread_id, _msg_ts=msg_ts, _text=text):
        sent_ts = await _send(
            api_url, number, _to, resp,
            quote_timestamp=_msg_ts, quote_author=_to, quote_message=_text,
        )
        if sent_ts:
            sent_timestamps.add(int(sent_ts))
            store.map_timestamp(int(sent_ts), _tid)
        if _msg_ts:
            await _remove_react(api_url, number, _to, _to, _msg_ts, "\u231b")

    async def _handle(m, handler=on_message):
        try:
            await handler(m)
        except Exception:
            log.exception("Handler error [%s]", m.thread_id)

    asyncio.create_task(_handle(Message(
        channel="signal",
        sender=sender,
        text=text,
        thread_id=thread_id,
        reply=reply,
        quote_timestamp=quote_ts,
        attachments=attachments,
    )))
