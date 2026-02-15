import asyncio
import email
import imaplib
import logging
from email.utils import parseaddr
from typing import Callable, Awaitable

from channels import Message

log = logging.getLogger(__name__)


def _extract_body(msg: email.message.Message) -> str:
    """Extract plain text body from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode("utf-8", errors="replace")
    return ""


async def listen(
    imap_host: str,
    imap_user: str,
    imap_password: str,
    on_message,
    make_reply: Callable[[str, str], Callable[[str], Awaitable[None]]],
    allowed_senders: list[str] | None = None,
    poll_interval: int = 60,
):
    """Poll IMAP for new emails and dispatch them as messages.

    make_reply(label) returns an async reply function that sends via Signal.
    """
    loop = asyncio.get_event_loop()
    log.info("Email polling started for %s (every %ds)", imap_user, poll_interval)

    def _poll():
        while True:
            try:
                conn = imaplib.IMAP4_SSL(imap_host)
                conn.login(imap_user, imap_password)
                conn.select("INBOX")

                _, nums = conn.search(None, "UNSEEN")
                for num in nums[0].split():
                    if not num:
                        continue
                    _, data = conn.fetch(num, "(RFC822)")
                    raw_email = data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    sender_name, sender_addr = parseaddr(msg["From"])
                    if allowed_senders and sender_addr.lower() not in [s.lower() for s in allowed_senders]:
                        log.info("Ignoring email from %s (not in allowed_senders)", sender_addr)
                        continue

                    subject = msg.get("Subject", "(no subject)")
                    body = _extract_body(msg)
                    text = f"**Email from:** {sender_name} <{sender_addr}>\n**Subject:** {subject}\n\n{body}"

                    log.info("Email from %s: %s", sender_addr, subject)

                    thread_id = f"email:{sender_addr}:{subject}"
                    label = f"**Re: {subject}** (from {sender_addr})\n\n"
                    reply_fn = make_reply(label, thread_id)

                    asyncio.run_coroutine_threadsafe(
                        on_message(Message(
                            channel="email",
                            sender=sender_addr,
                            text=text,
                            thread_id=thread_id,
                            reply=reply_fn,
                        )),
                        loop,
                    )

                conn.logout()
            except Exception:
                log.exception("Email poll error")

            import time
            time.sleep(poll_interval)

    await loop.run_in_executor(None, _poll)
