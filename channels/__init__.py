from dataclasses import dataclass, field
from typing import Callable, Awaitable


@dataclass
class Attachment:
    data: bytes         # raw image bytes
    media_type: str     # e.g. "image/jpeg", "image/png"

@dataclass
class Message:
    channel: str        # "signal" | "email" | "cli"
    sender: str         # phone number, email address, or "cli"
    text: str
    thread_id: str      # conversation thread ID
    reply: Callable[[str], Awaitable[None]]
    quote_timestamp: int | None = None  # timestamp of quoted message (for reply chains)
    attachments: list[Attachment] = field(default_factory=list)
