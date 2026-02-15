import asyncio
import sys
from channels import Message


async def _print_reply(text: str):
    print(f"\n{text}\n")


async def interactive(on_message):
    loop = asyncio.get_event_loop()
    is_tty = sys.stdin.isatty()

    if is_tty:
        # Interactive mode
        while True:
            try:
                line = await loop.run_in_executor(None, lambda: input("occam> "))
            except (EOFError, KeyboardInterrupt):
                break
            if line.strip().lower() in ("exit", "quit"):
                break
            if not line.strip():
                continue
            await on_message(Message(
                channel="cli",
                sender="cli",
                text=line.strip(),
                thread_id="cli:local",
                reply=_print_reply,
            ))
    else:
        # Pipe mode: read all stdin, process as one message
        text = await loop.run_in_executor(None, sys.stdin.read)
        if text.strip():
            await on_message(Message(
                channel="cli",
                sender="cli",
                text=text.strip(),
                thread_id="cli:local",
                reply=_print_reply,
            ))
