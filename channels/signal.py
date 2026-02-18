import asyncio
import json
import logging
import uuid

import aiohttp

from channels import Attachment, Message
import store

log = logging.getLogger(__name__)

POLL_INTERVAL = 1  # seconds between polls


async def _send(
    api_url: str, from_number: str, to_number: str, text: str,
    quote_timestamp: int | None = None, quote_author: str | None = None, quote_message: str | None = None,
) -> int | None:
    """Send a Signal message via the REST API. Returns the sent message timestamp."""
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
    async with aiohttp.ClientSession() as session:
        resp = await session.post(f"{api_url}/v2/send", json=payload)
        if resp.status != 201:
            log.error("Signal send failed: %s %s", resp.status, await resp.text())
            return None
        result = await resp.json()
        return result.get("timestamp")


def _extract_message(data: dict, owner_number: str) -> tuple[str, str, int | None, list[dict]] | None:
    """Extract (sender, text, quote_timestamp, attachments) from a Signal payload.

    Only processes Note to Self messages. Returns quote timestamp if replying to a message.
    attachments is a list of dicts with 'id' and 'contentType' keys.
    """
    envelope = data.get("envelope", {})

    sync = envelope.get("syncMessage", {}).get("sentMessage")
    if not sync:
        return None

    # Allow messages with attachments but no text
    text = sync.get("message", "")
    if not text and not sync.get("attachments"):
        return None

    # Ignore group messages
    if sync.get("groupInfo") or sync.get("groupId"):
        return None

    dest = sync.get("destinationNumber", "")
    if dest != owner_number:
        return None

    quote_ts = None
    quote = sync.get("quote")
    if quote:
        quote_ts = quote.get("id")

    attachments = sync.get("attachments", [])

    return owner_number, text, quote_ts, attachments


async def _react(api_url: str, number: str, recipient: str, target_author: str, timestamp: int, emoji: str) -> None:
    """Send a reaction to a Signal message."""
    payload = {
        "reaction": emoji,
        "recipient": recipient,
        "target_author": target_author,
        "timestamp": timestamp,
    }
    async with aiohttp.ClientSession() as session:
        resp = await session.post(f"{api_url}/v1/reactions/{number}", json=payload)
        if resp.status not in (200, 201, 204):
            log.error("Signal react failed: %s %s", resp.status, await resp.text())


async def _remove_react(api_url: str, number: str, recipient: str, target_author: str, timestamp: int, emoji: str) -> None:
    """Remove a reaction from a Signal message."""
    payload = {
        "reaction": emoji,
        "recipient": recipient,
        "target_author": target_author,
        "timestamp": timestamp,
    }
    async with aiohttp.ClientSession() as session:
        resp = await session.delete(f"{api_url}/v1/reactions/{number}", json=payload)
        if resp.status not in (200, 201, 204):
            log.error("Signal remove react failed: %s %s", resp.status, await resp.text())


async def _download_attachment(api_url: str, attachment_id: str) -> bytes | None:
    """Download an attachment from signal-cli-rest-api."""
    async with aiohttp.ClientSession() as session:
        resp = await session.get(f"{api_url}/v1/attachments/{attachment_id}")
        if resp.status == 200:
            return await resp.read()
        log.error("Failed to download attachment %s: %s", attachment_id, resp.status)
        return None


async def listen(number: str, api_url: str, on_message):
    """Poll signal-cli-rest-api for incoming messages and dispatch them."""
    sent_timestamps: set[int] = set()

    log.info("Signal polling started for %s at %s (every %ss)", number, api_url, POLL_INTERVAL)

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                resp = await session.get(f"{api_url}/v1/receive/{number}", timeout=aiohttp.ClientTimeout(total=30))
                if resp.status != 200:
                    log.warning("Signal poll returned %s, retrying...", resp.status)
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                messages = json.loads(await resp.text())
                for data in messages:
                    msg_ts = data.get("envelope", {}).get("timestamp")
                    if msg_ts in sent_timestamps:
                        sent_timestamps.discard(msg_ts)
                        continue

                    result = _extract_message(data, number)
                    if not result:
                        continue

                    sender, text, quote_ts, raw_attachments = result

                    # Download image attachments
                    attachments = []
                    for att in raw_attachments:
                        content_type = att.get("contentType", "")
                        att_id = att.get("id")
                        if att_id and content_type.startswith("image/"):
                            image_data = await _download_attachment(api_url, att_id)
                            if image_data:
                                attachments.append(Attachment(data=image_data, media_type=content_type))

                    # Determine thread
                    if quote_ts:
                        thread_id = store.get_thread_for_timestamp(quote_ts)
                    else:
                        thread_id = None

                    if not thread_id:
                        thread_id = uuid.uuid4().hex[:12]

                    log.info("Signal [%s] from %s: %s", thread_id, sender, text[:50])

                    if msg_ts:
                        store.map_timestamp(msg_ts, thread_id)

                    # React with hourglass to acknowledge receipt
                    if msg_ts:
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

                    async def _handle(msg, handler=on_message):
                        try:
                            await handler(msg)
                        except Exception:
                            log.exception("Error in message handler for [%s]", msg.thread_id)

                    asyncio.create_task(_handle(Message(
                        channel="signal",
                        sender=sender,
                        text=text,
                        thread_id=thread_id,
                        reply=reply,
                        quote_timestamp=quote_ts,
                        attachments=attachments,
                    )))

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                log.warning("Signal poll error: %s. Retrying in 5s...", e)
                await asyncio.sleep(5)
                continue

            await asyncio.sleep(POLL_INTERVAL)
