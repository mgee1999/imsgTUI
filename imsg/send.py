"""Send through Messages.app via AppleScript. The chat guid in chat.db
(`any;-;+1555…` / `any;+;<groupid>`) is exactly the AppleScript `chat id`."""
from __future__ import annotations

import subprocess


class SendError(RuntimeError):
    pass


def _osascript(script: str, *args: str, timeout: float = 20) -> str:
    cmd = ["osascript", "-e", script, *args]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise SendError("Messages.app did not respond (timeout)") from e
    if p.returncode != 0:
        err = (p.stderr or p.stdout).strip()
        raise SendError(err.split("\n")[-1] or f"osascript exit {p.returncode}")
    return p.stdout.strip()


def send_text(chat_guid: str, text: str) -> None:
    if not text.strip():
        raise SendError("empty message")
    _osascript(
        'on run argv\n'
        'tell application "Messages" to send (item 2 of argv) to chat id (item 1 of argv)\n'
        'end run',
        chat_guid, text,
    )


def send_file(chat_guid: str, path: str) -> None:
    _osascript(
        'on run argv\n'
        'set f to POSIX file (item 2 of argv)\n'
        'tell application "Messages" to send f to chat id (item 1 of argv)\n'
        'end run',
        chat_guid, path,
    )


def send_to_handle(handle: str, text: str) -> None:
    """Start a conversation with a raw phone/email (iMessage first, then SMS)."""
    _osascript(
        'on run argv\n'
        'set h to item 1 of argv\n'
        'set t to item 2 of argv\n'
        'tell application "Messages"\n'
        '  try\n'
        '    set svc to 1st account whose service type = iMessage\n'
        '    send t to participant h of svc\n'
        '  on error\n'
        '    set svc to 1st account whose service type = SMS\n'
        '    send t to participant h of svc\n'
        '  end try\n'
        'end tell\n'
        'end run',
        handle, text,
    )
