import asyncio
import json
import logging
import uuid

import aiohttp

from channels import Attachment, Message
import store

log = logging.getLogger(__name__)


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
    """Extract (sender, text, quote_timestamp, attachments) from a Signal websocket payload.

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


async def _download_attachment(api_url: str, attachment_id: str) -> bytes | None:
    """Download an attachment from signal-cli-rest-api."""
    async with aiohttp.ClientSession() as session:
        resp = await session.get(f"{api_url}/v1/attachments/{attachment_id}")
        if resp.status == 200:
            return await resp.read()
        log.error("Failed to download attachment %s: %s", attachment_id, resp.status)
        return None


async def listen(number: str, api_url: str, on_message):
    """Connect to signal-cli-rest-api websocket and dispatch incoming messages."""
    # Track timestamps of messages the bot sent so we can ignore them on the websocket
    sent_timestamps: set[int] = set()

    while True:
        try:
            async with aiohttp.ClientSession() as session:
                log.info("Connecting to Signal API at %s", api_url)
                async with session.ws_connect(f"{api_url}/v1/receive/{number}") as ws:
                    log.info("Signal websocket connected")
                    async for raw in ws:
                        if raw.type != aiohttp.WSMsgType.TEXT:
                            continue
                        try:
                            data = json.loads(raw.data)
                        except json.JSONDecodeError:
                            continue

                        log.debug("Signal raw: %s", json.dumps(data)[:200])

                        # Skip messages the bot itself sent
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

                        # Determine thread: continue existing if replying, new if not
                        if quote_ts:
                            thread_id = store.get_thread_for_timestamp(quote_ts)
                        else:
                            thread_id = None

                        if not thread_id:
                            thread_id = uuid.uuid4().hex[:12]

                        log.info("Signal [%s] from %s: %s", thread_id, sender, text[:50])

                        if msg_ts:
                            store.map_timestamp(msg_ts, thread_id)

                        async def reply(resp, _to=sender, _tid=thread_id, _msg_ts=msg_ts, _text=text):
                            sent_ts = await _send(
                                api_url, number, _to, resp,
                                quote_timestamp=_msg_ts, quote_author=_to, quote_message=_text,
                            )
                            if sent_ts:
                                sent_timestamps.add(int(sent_ts))
                                store.map_timestamp(int(sent_ts), _tid)

                        await on_message(Message(
                            channel="signal",
                            sender=sender,
                            text=text,
                            thread_id=thread_id,
                            reply=reply,
                            quote_timestamp=quote_ts,
                            attachments=attachments,
                        ))
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log.warning("Signal websocket disconnected: %s. Reconnecting in 5s...", e)
            await asyncio.sleep(5)
